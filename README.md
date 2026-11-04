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

CustomerSupport-RAG-Engine/

â”‚

â”œâ”€â”€ app/

â”‚   â”œâ”€â”€ api/

â”‚   â”‚   â”œâ”€â”€ admin.py

â”‚   â”‚   â”œâ”€â”€ auth.py

â”‚   â”‚   â”œâ”€â”€ chat.py

â”‚   â”‚   â”œâ”€â”€ customer.py

â”‚   â”‚   â”œâ”€â”€ documents.py

â”‚   â”‚   â”œâ”€â”€ document_history.py

â”‚   â”‚   â””â”€â”€ products.py

â”‚   â”‚

â”‚   â”œâ”€â”€ core/

â”‚   â”‚   â”œâ”€â”€ config.py

â”‚   â”‚   â”œâ”€â”€ dependencies.py

â”‚   â”‚   â”œâ”€â”€ security.py

â”‚   â”‚   â””â”€â”€ text_normalizer.py

â”‚   â”‚

â”‚   â”œâ”€â”€ db/

â”‚   â”œâ”€â”€ ingestion/

â”‚   â”œâ”€â”€ integrations/

â”‚   â”œâ”€â”€ llm/

â”‚   â”œâ”€â”€ retrieval/

â”‚   â”œâ”€â”€ schemas/

â”‚   â”œâ”€â”€ services/

â”‚   â”œâ”€â”€ static/

â”‚   â””â”€â”€ main.py

â”‚

â”œâ”€â”€ RAG/

â”‚   â”œâ”€â”€ database/

â”‚   â”œâ”€â”€ diagnostics/

â”‚   â”œâ”€â”€ maintenance/

â”‚   â”œâ”€â”€ migrations/

â”‚   â””â”€â”€ verification/

â”‚

â”œâ”€â”€ scripts/

â”‚   â””â”€â”€ database/

â”‚

â”œâ”€â”€ tests/

â”‚   â”œâ”€â”€ api/

â”‚   â”œâ”€â”€ ingestion/

â”‚   â”œâ”€â”€ llm/

â”‚   â”œâ”€â”€ retrieval/

â”‚   â”œâ”€â”€ services/

â”‚   â””â”€â”€ versioning/

â”‚

â”œâ”€â”€ test_data/

â”œâ”€â”€ requirements.txt

â”œâ”€â”€ .gitignore

â””â”€â”€ README.md

```



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




