
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_customer
from app.db.models import ActivityLog, ChatLog, Customer
from app.db.session import get_db
from app.services.answer_service import answer_customer_question


router = APIRouter(prefix="/chat", tags=["Chat"])


# ---------------------------------------------------------
# CHAT REQUEST
# ---------------------------------------------------------

class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The customer's question",
    )

    product_id: str | None = Field(
        default=None,
        max_length=100,
        description="Optional product ID",
    )


# ---------------------------------------------------------
# CHAT RESPONSE
# ---------------------------------------------------------

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]


# ---------------------------------------------------------
# CHAT HISTORY RESPONSE
# ---------------------------------------------------------

class ChatHistoryItem(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[dict]
    created_at: datetime | None


class ChatHistoryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    chats: list[ChatHistoryItem]


# ---------------------------------------------------------
# CUSTOMER CHAT ENDPOINT
# POST /chat
# ---------------------------------------------------------

@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    try:
        result = answer_customer_question(
            db=db,
            question=request.question,
            product_id=request.product_id,
        )

        chat_log = ChatLog(
            customer_id=current_customer.id,
            question=request.question,
            answer=result["answer"],
            source_details=json.dumps(
                result.get("sources", []),
                default=str,
            ),
        )

        activity = ActivityLog(
            customer_id=current_customer.id,
            action="chat_question_submitted",
            details="Customer submitted a chatbot question.",
        )

        db.add(chat_log)
        db.add(activity)
        db.commit()

        return result

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to process your question right now.",
        ) from exc


# ---------------------------------------------------------
# CUSTOMER CHAT HISTORY
# GET /chat/history
# ---------------------------------------------------------

@router.get("/history", response_model=ChatHistoryResponse)
def get_chat_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    try:
        # Count only this customer's conversations
        total = (
            db.query(ChatLog)
            .filter(ChatLog.customer_id == current_customer.id)
            .count()
        )

        # Retrieve this customer's conversations
        chat_records = (
            db.query(ChatLog)
            .filter(ChatLog.customer_id == current_customer.id)
            .order_by(
                ChatLog.created_at.desc(),
                ChatLog.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        chats = []

        for record in chat_records:
            try:
                sources = (
                    json.loads(record.source_details)
                    if record.source_details
                    else []
                )

                if not isinstance(sources, list):
                    sources = []

            except (json.JSONDecodeError, TypeError):
                sources = []

            chats.append(
                ChatHistoryItem(
                    id=record.id,
                    question=record.question,
                    answer=record.answer,
                    sources=sources,
                    created_at=record.created_at,
                )
            )

        return ChatHistoryResponse(
            total=total,
            limit=limit,
            offset=offset,
            chats=chats,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve chat history.",
        ) from exc
