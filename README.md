# CustomerSupport-RAG-Engine



An AI-powered e-commerce customer support platform built with **FastAPI, Ollama, PostgreSQL, pgvector, and Retrieval-Augmented Generation (RAG)**.



The platform combines locally hosted Large Language Models with document-based retrieval to provide contextual answers to customer queries.



## Key Features



\- **Local LLM Integration:** Uses Ollama to run locally hosted language models.

\- **Retrieval-Augmented Generation:** Retrieves relevant information from uploaded documents before generating answers.

\- **Document Ingestion:** Supports document parsing, processing, and indexing.

\- **Document Versioning:** Maintains document versions and active-version retrieval.

\- **Semantic Search:** Uses embeddings and PostgreSQL with pgvector for similarity-based retrieval.

\- **Customer Authentication:** Supports customer registration, login, email verification, and OTP-related workflows.

\- **Admin Management:** Provides administrative APIs and an admin interface.

\- **Product Catalogue:** Supports product creation, updates, product search, and catalogue retrieval.

\- **Chat Support:** Provides conversational customer support through a FastAPI backend.



## Technology Stack



| Category | Technologies |

|---|---|

| Backend | Python, FastAPI |

| LLM Runtime | Ollama |

| Language Model | Qwen |

| Embedding Model | nomic-embed-text |

| Database | PostgreSQL |

| Vector Search | pgvector |

| ORM | SQLAlchemy |

| Database Migrations | Alembic |

| Validation | Pydantic |

| Document Processing | PyPDF, python-docx, openpyxl |

| Testing | Pytest, HTTPX |

| API Documentation | Swagger / OpenAPI |



## Project Structure

```text
indian-ecommerce-support-chatbot/
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
├── .env.example                  # Copy to .env and fill in
├── pytest.ini
├── requirements.txt
└── README.md
```

## Running Scripts

Run scripts from the project root as modules so that the `app` package is importable:

```bash
python -m scripts.database.create_tables
python -m scripts.diagnostics.check_ollama
python -m scripts.maintenance.retry_stuck_documents
```

Run the tests with `pytest`.

## Architecture Overview



1\. Documents are uploaded through the document API.

2\. The ingestion pipeline extracts and processes document content.

3\. Processed content is divided into chunks.

4\. The embedding model converts chunks into vector representations.

5\. Vectors and document metadata are stored in PostgreSQL using pgvector.

6\. A customer submits a question through the chat API.

7\. The retrieval component searches for relevant document chunks.

8\. Retrieved context is passed to the Ollama language model.

9\. The model generates a context-aware response.



## Installation and Setup



### 1. Clone the repository



```bash

git clone https://github.com/29Rajeswari/CustomerSupport-RAG-Engine.git

cd CustomerSupport-RAG-Engine

```



### 2. Create a Python virtual environment



```bash

python -m venv .venv

```



Activate it on Windows PowerShell:



```powershell

.\\.venv\\Scripts\\Activate.ps1

```



### 3. Install dependencies



```bash

python -m pip install -r requirements.txt

```



### 4. Configure environment variables



Create a local `.env` file using the environment variable names required by `app/core/config.py`.



Do not commit `.env` or expose database passwords, API keys, JWT secrets, or email credentials.



### 5. Set up PostgreSQL



Install or start PostgreSQL with pgvector support.



Configure the database connection and enable the required PostgreSQL extensions according to the project's database configuration and migrations.



### 6. Set up Ollama



Install Ollama and download the models configured by the application.



Example:



```bash

ollama pull qwen2.5:1.5b

ollama pull nomic-embed-text

```



Ensure the Ollama service is running before using the chatbot.



### 7. Start the FastAPI backend



```bash

python -m uvicorn app.main:app --reload

```



## API Documentation



After starting the backend, open:



```text

http://127.0.0.1:8000/docs

```



The Swagger interface provides interactive access to the registered API endpoints.



## Running Tests



Run the project tests using:



```bash

python -m pytest tests/ -v

```



## Security



\- Keep environment variables and credentials outside source control.

\- Do not commit `.env` files.

\- Keep database backups and uploaded customer documents out of the public repository.

\- Use appropriate authentication and authorization for protected endpoints.



## Future Enhancements



\- Bulk product catalogue import using CSV.

\- Inventory synchronization with successful order transactions.

\- Improved retrieval evaluation and response quality.

\- Expanded customer-facing frontend.

\- Additional monitoring and deployment automation.



## Repository



GitHub: https://github.com/29Rajeswari/CustomerSupport-RAG-Engine



## License



License to be determined.




