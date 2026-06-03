# Enterprise-Grade RAG Platform

A SaaS-style Retrieval Augmented Generation platform with authentication, role-based admin controls, document ingestion, chunking strategies, local vector search, citation-backed Q&A, feedback, evaluation metrics, usage analytics, audit logs, and security controls.

## Features

- User login, admin login, and role-based access control
- Admin dashboard with analytics, logs, reports, and system status
- Document upload and ingestion
- Chunking strategy selection: fixed, recursive, semantic-lite
- Local vector database using TF-IDF cosine search
- RAG Q&A with citations
- Feedback system for answer quality
- RAGAS-style evaluation metrics: relevance, faithfulness, hallucination rate, latency, cost estimate, feedback score
- Security: prompt injection defense, API key protection via environment variables, input validation, rate limiting, sensitive data masking, audit logs
- Deployment-ready structure with frontend, backend, database, vector store, environment variables, and documentation

## Tech Stack

- Frontend: React + Vite
- Backend: FastAPI
- Database: SQLite for local demo, easy to replace with PostgreSQL
- Vector DB: local TF-IDF index, easy to replace with ChromaDB, Pinecone, or Weaviate
- RAG Framework: custom lightweight RAG pipeline
- Evaluation: RAGAS-style custom rubric

## Demo Accounts

```text
Admin
email: admin@rag.com
password: admin123

User
email: user@rag.com
password: user123
```

## Run Locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Architecture

```text
React Frontend
  -> FastAPI Backend
  -> SQLite Database
  -> Document Ingestion
  -> Chunking Engine
  -> Local Vector Index
  -> RAG Answer Generator
  -> Citations + Evaluation + Feedback
  -> Analytics Dashboard + Audit Logs
```

## Resume Line

Built an enterprise-grade RAG SaaS platform with role-based authentication, admin dashboard, document ingestion, chunking strategy selection, vector retrieval, citation-backed Q&A, feedback collection, RAGAS-style evaluation, usage analytics, and security controls including prompt injection defense, rate limiting, sensitive data masking, audit logs, and API key protection.
