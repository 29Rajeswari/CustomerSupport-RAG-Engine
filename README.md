🛒 CustomerSupport-RAG-Engine

An AI-powered e-commerce customer support platform built with FastAPI, Ollama, PostgreSQL, pgvector, and Retrieval-Augmented Generation (RAG).

The platform combines locally hosted Large Language Models with document-based retrieval to give contextual answers to customer queries, with a complete e-commerce backend (orders, shipments, returns, refunds) and a built-in RAG evaluation framework that measures retrieval and answer quality.

Architecture

📑 Table of Contents
Key Features
Technology Stack
Architecture Overview
RAG Evaluation
Project Structure
Installation and Setup
Running Scripts
API Documentation
Running Tests
Security
Future Enhancements
Repository
License
✨ Key Features
Local LLM Integration: Uses Ollama to run locally hosted language models (Qwen by default; other Ollama models such as Llama, Phi, or DeepSeek can be configured by the admin/developer).
Retrieval-Augmented Generation: Retrieves relevant information from uploaded documents before generating answers.
Document Ingestion: Parses, processes, chunks, and indexes PDF, DOCX, and XLSX documents.
Document Versioning: Maintains document versions with version history and active-version retrieval.
Semantic Search: Uses embeddings and PostgreSQL with pgvector for similarity-based retrieval.
RAG Evaluation Framework: Measures retrieval quality (Precision, Recall, MRR, nDCG, Hit rate) and generation quality (faithfulness, relevance, correctness) on a question dataset.
Customer Authentication: OTP-based registration (request, verify, complete), login, profile, and forgot-password reset with OTP verification.
Order Management: Customers place, cancel, and track orders; admins create shipments and update shipment status.
Returns & Refunds: Customers raise return requests; admins approve, reject, inspect, and complete returns, then create and process (or fail) refunds.
Admin Management: Admin login, an admin web interface, and APIs to view customers, orders, chats, and activity logs.
Product Catalogue: Product creation, updates, customer-facing listing and detail, and bulk upload through CSV.
Chat Support: Conversational customer support with chat history through a FastAPI backend.
🧰 Technology Stack
Category	Technologies
Backend	Python, FastAPI
LLM Runtime	Ollama
Language Model	Qwen (default, e.g. qwen2.5:1.5b); other Ollama models are configurable
Embedding Model	nomic-embed-text
Database	PostgreSQL
Vector Search	pgvector
ORM	SQLAlchemy
Validation	Pydantic
Document Processing	PyPDF, python-docx, openpyxl
Evaluation	Custom retrieval metrics and automatic relevance judge
Testing	Pytest, HTTPX
API Documentation	Swagger / OpenAPI
🏗 Architecture Overview

RAG flow

Ingestion (admin)

Documents are uploaded through the document API.
The ingestion pipeline extracts and processes document content.
Processed content is divided into chunks.
The embedding model converts chunks into vector representations.
Vectors and document metadata are stored in PostgreSQL using pgvector, tied to a document version.

Question answering (customer)

A customer submits a question through the chat API.
The retrieval component searches for relevant chunks from the active document versions.
Retrieved context is passed to the Ollama language model.
The model generates a context-aware response, which is saved in the chat history.
📊 RAG Evaluation

The project includes an evaluation framework in the evaluation/ folder that tests the RAG pipeline in two phases: retrieval (did we find the right chunks?) and generation (is the final answer good?).

Phase 1: Retrieval evaluation

Run on 25 questions, retrieving the top 5 chunks, with macro-averaged metrics.

Metric	Score	What it measures
Precision@5	0.2080	Share of the 5 retrieved chunks that are relevant
Recall@5	1.0000	Share of the relevant chunks that were retrieved
MRR@5	0.8533	How high the first relevant chunk is ranked
nDCG@5	0.8600	Ranking quality, rewarding relevant chunks near the top
Hit@5	0.8800	Share of questions with at least one relevant chunk in the top 5
Successful / Failed questions	22 / 3	Questions where retrieval worked vs. did not

Precision@5 is naturally low when only one or two chunks are truly relevant to each question, because the other retrieved chunks cannot count as relevant. MRR and nDCG above 0.85 show that relevant chunks are usually ranked at or near the top.

Phase 2: Generation evaluation

Run on 13 questions (100% completed). An automatic judge scores each answer from 1 to 5 on four criteria.

Metric	Average score	Percentage	What it measures
Faithfulness	2.46 / 5	49.2%	Does the answer stay true to the retrieved context?
Answer relevance	4.08 / 5	81.5%	Does the answer address the question asked?
Context relevance	2.92 / 5	58.5%	Is the retrieved context useful for the question?
Answer correctness	2.62 / 5	52.3%	Is the answer factually correct against the expected answer?
Findings
Retrieval is strong: relevant chunks are almost always found (Recall@5 of 1.0) and ranked well (MRR 0.85, nDCG 0.86).
Answers are on topic: answer relevance is about 82%.
Generation is the main area to improve: faithfulness and correctness are around 50%. This evaluation used a small local model (qwen2.5:1.5b), so trying a larger model, tightening the prompt, or reducing noisy context are the next steps.
The framework makes each change measurable: re-run the evaluation after a change and compare the scores.
Run the evaluation

Run these from the project root as modules. Running the files directly (python evaluation\compare_top_k.py) fails with ModuleNotFoundError: No module named 'app'.

bash
# Phase 1: retrieval metrics (top-k)
python -m evaluation.compare_top_k

# Phase 2: generation metrics (LLM-judged)
python -m evaluation.run_generation_evaluation

Reports are saved in evaluation/evaluation_results/:

File	Contents
rag_evaluation_report.json	Retrieval metrics per question and combined
generation_evaluation_report.json	Generation scores per question and summary
generation_judge_cache.json	Cached judge scores so unchanged answers are not re-judged

Ollama must be running, and the evaluation database must be available.

📁 Project Structure
CustomerSupport-RAG-Engine/
├── app/                          # FastAPI application
│   ├── api/
│   │   ├── api_router.py         # Combines all route modules
│   │   └── routes/               # admin_, auth_, chat_, customer_, document_,
│   │                             # document_history_, product_ routes
│   ├── config/                   # settings.py (environment-based Settings)
│   ├── core/                     # security.py, dependencies.py
│   ├── db/                       # session.py (engine and get_db)
│   ├── models/                   # SQLAlchemy models: base, document, chat, customer,
│   │                             # auth, activity_log, order, shipment, product, return_request
│   ├── schemas/                  # Pydantic request/response schemas
│   ├── services/                 # Business logic (answers, documents, email, OTP, orders, products)
│   ├── ingestion/                # Parsers, processor, document versioning
│   ├── retrieval/                # Vector search
│   ├── llm/                      # Ollama client
│   ├── integrations/             # External integrations (reserved)
│   ├── utils/                    # text_normalizer.py
│   ├── static/                   # Admin UI
│   └── main.py                   # Application entry point
│
├── evaluation/                   # RAG evaluation framework
│   ├── rag_evaluation_dataset.py # Evaluation questions and expected answers
│   ├── automatic_relevance_judge.py
│   ├── compare_top_k.py          # Phase 1: retrieval metrics
│   ├── run_generation_evaluation.py  # Phase 2: generation metrics
│   └── evaluation_results/       # JSON reports and judge cache
│
├── scripts/                      # Operational scripts (run from project root)
│   ├── database/                 # create_tables, backup_database, verify_backup, export_table_inventory
│   ├── migrations/               # migrate_* schema migrations
│   ├── maintenance/              # backfill_*, inspect_version_history, retry_stuck_documents
│   └── diagnostics/              # check_* health and consistency checks
│
├── tests/                        # Pytest suite
│   ├── api/  ingestion/  llm/  retrieval/  services/  versioning/
│   └── fixtures/                 # Small files used by tests
│
├── data/
│   └── samples/                  # Sample products.csv and sample policy documents
│
├── storage/                      # Runtime data (git-ignored)
│   ├── uploads/                  # Uploaded documents
│   ├── backups/                  # database/ dumps and code/ snapshots
│   └── diagnostics/              # Saved diagnostic output
│
├── docs/                         # Architecture and flow diagrams
├── .env.example                  # Copy to .env and fill in
├── pytest.ini
├── requirements.txt
└── README.md
🚀 Installation and Setup
1. Clone the repository
bash
git clone https://github.com/29Rajeswari/CustomerSupport-RAG-Engine.git
cd CustomerSupport-RAG-Engine
2. Create a Python virtual environment
bash
python -m venv .venv

Activate it on Windows PowerShell:

powershell
.\.venv\Scripts\Activate.ps1

On macOS/Linux:

bash
source .venv/bin/activate
3. Install dependencies
bash
python -m pip install -r requirements.txt
4. Configure environment variables

Create a local .env file (start from .env.example) using the variable names defined in app/config/settings.py.

Do not commit .env or expose database passwords, API keys, JWT secrets, or email credentials.

5. Set up PostgreSQL

Install or start PostgreSQL with pgvector support. Configure the database connection and enable the required extensions according to the project's database configuration, then create the tables:

bash
python -m scripts.database.create_tables
6. Set up Ollama

Install Ollama and download the models configured by the application:

bash
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text

Ensure the Ollama service is running before using the chatbot.

Using a different LLM: pull another model (for example Llama, Phi, or DeepSeek) and set its name in your .env. This is a server-side admin/developer setting; customers cannot change the model. The embedding model is separate: if you change it, re-embed all documents.

7. Start the FastAPI backend
bash
python -m uvicorn app.main:app --reload
🛠 Running Scripts

Run scripts from the project root as modules so that the app package is importable:

bash
python -m scripts.database.create_tables
python -m scripts.diagnostics.check_ollama
python -m scripts.maintenance.retry_stuck_documents
📚 API Documentation

After starting the backend, open:

http://127.0.0.1:8000/docs

The Swagger interface provides interactive access to all registered endpoints.

Area	Endpoints	Description
Authentication	POST /auth/register/request-otp, /auth/register/verify-otp, /auth/register/complete, /auth/login, /auth/forgot-password/request-otp, /auth/forgot-password/verify-otp, /auth/forgot-password/reset; GET /auth/me	OTP-based registration, login, password reset, profile
Chat	POST /chat, GET /chat/history	RAG-powered answers and chat history
Customer	GET /customer/profile, /customer/orders, /customer/chats, /customer/activity, /customer/returns, /customer/returns/{return_number}, /customer/refunds, /customer/orders/{order_id}/tracking; POST /customer/orders, /customer/orders/{order_id}/cancel, /customer/orders/{order_id}/returns	Orders, tracking, cancellation, returns, refunds, activity
Products	GET /products, /products/{product_id}; POST /admin/products, /admin/products/upload-csv; GET /admin/products; PATCH /admin/products/{product_id}	Customer catalogue and admin product management (with CSV upload)
Documents	POST /documents/upload, GET /documents/history, GET /documents/{document_id}/history	Upload knowledge documents and view version history
Administrator	POST /admin/login; GET /admin/customers, /admin/orders, /admin/chats, /admin/activity, /admin/shipments, /admin/returns; shipment, return, and refund management endpoints	Admin dashboard data, shipments, returns, refunds
Health	GET /health	Service health check
Returns & refunds workflow
Customer: POST /customer/orders/{order_id}/returns
        ↓
Admin: approve (or reject) → inspect → complete
        ↓
Admin: create refund → process (or fail)
        ↓
Customer: GET /customer/returns, /customer/refunds
🧪 Running Tests
bash
python -m pytest tests/ -v
🔐 Security
Keep environment variables and credentials outside source control.
Do not commit .env files.
Keep database backups and uploaded customer documents out of the public repository.
Use appropriate authentication and authorization for protected endpoints.
Customer accounts are verified with email OTP, and admin endpoints use a separate admin login.
🔮 Future Enhancements
Improve generation quality (faithfulness and correctness) with larger models, prompt tuning, and cleaner retrieved context.
Expand the evaluation dataset and add retrieval re-ranking experiments.
Inventory synchronization with successful order transactions.
Expanded customer-facing frontend.
Additional monitoring and deployment automation.
📦 Repository

GitHub: https://github.com/29Rajeswari/CustomerSupport-RAG-Engine

📄 License

License to be determined.
