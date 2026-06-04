from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from io import BytesIO

from .config import settings
from .database import Base, engine, get_db
from .models import AuditLog, Chunk, Document, Feedback, QueryLog, User
from .rag import answer_question, chunk_text
from .security import (
    audit,
    create_token,
    get_current_user,
    hash_password,
    rate_limit,
    require_admin,
    validate_question,
    verify_password,
)


app = FastAPI(title="Enterprise RAG Platform", dependencies=[Depends(rate_limit)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.frontend_origins.split(",") if origin.strip()],
    allow_origin_regex=settings.frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    email: str
    password: str


class AskRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    query_id: int
    score: int
    comment: str = ""


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserCreateRequest(BaseModel):
    email: str
    name: str
    role: str
    password: str


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    if not db.query(User).filter(User.email == "admin@rag.com").first():
        db.add(User(email="admin@rag.com", name="Admin", role="admin", password_hash=hash_password("admin123")))
        db.add(User(email="user@rag.com", name="Demo User", role="user", password_hash=hash_password("user123")))
        db.commit()


@app.get("/health")
def health():
    return {"status": "ok", "vector_db": "local-tfidf", "database": "sqlite"}


@app.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    audit(db, user.id, "login", f"{user.email} logged in")
    return {"token": create_token(user), "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}}


@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@app.post("/auth/change-password")
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    audit(db, user.id, "change_password", f"{user.email} changed password")
    return {"status": "password_changed"}


@app.post("/admin/users")
def create_user(payload: UserCreateRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if payload.role not in {"admin", "user", "viewer"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    user = User(email=payload.email, name=payload.name, role=payload.role, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    audit(db, admin.id, "create_user", f"Created user {payload.email}")
    return {"id": user.id, "email": user.email, "role": user.role}


@app.get("/admin/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.query(User).order_by(User.created_at.desc()).all()


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    chunking_strategy: str = Form("recursive"),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if chunking_strategy not in {"fixed", "recursive", "semantic"}:
        raise HTTPException(status_code=400, detail="Unsupported chunking strategy")
    raw = await file.read()
    if len(raw) > 10_000_000:
        raise HTTPException(status_code=400, detail="File too large (limit is 10MB)")
    if file.filename and file.filename.lower().endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(raw))
            if reader.is_encrypted:
                raise HTTPException(status_code=400, detail="Encrypted PDFs are not supported")
            
            extracted_pages = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    extracted_pages.append(page_text)
            text = "\n".join(extracted_pages)
            
            if not text.strip() and len(reader.pages) > 0:
                raise HTTPException(
                    status_code=400,
                    detail="This PDF appears to be scanned or image-only. Text extraction is not supported without OCR."
                )
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=400, detail=f"Could not read text from this PDF: {str(e)}")
    else:
        text = raw.decode("utf-8", errors="ignore")
    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in this file")

    document = Document(filename=file.filename or "document.txt", owner_id=user.id, chunking_strategy=chunking_strategy)
    db.add(document)
    db.commit()
    db.refresh(document)

    chunks = chunk_text(text, chunking_strategy)
    for index, content in enumerate(chunks, start=1):
        db.add(Chunk(document_id=document.id, content=content, chunk_index=index, citation=f"{document.filename} - chunk {index}"))
    db.commit()
    audit(db, user.id, "upload_document", f"Uploaded {document.filename} with {len(chunks)} chunks")
    return {"document_id": document.id, "filename": document.filename, "chunks": len(chunks), "strategy": chunking_strategy}


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    filename = document.filename
    db.delete(document)
    db.commit()
    audit(db, user.id, "delete_document", f"Deleted document {filename}")
    return {"status": "deleted", "document_id": document_id}


@app.get("/documents")
def documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Document).order_by(Document.created_at.desc()).all()


@app.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    filename = document.filename
    db.delete(document)
    db.commit()
    audit(db, user.id, "delete_document", f"Deleted document {filename}")
    return {"status": "deleted", "document_id": document_id}


@app.post("/rag/ask")
def ask(payload: AskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    question = validate_question(payload.question)
    result = answer_question(db, user, question)
    audit(db, user.id, "rag_question", question)
    return result


@app.post("/feedback")
def feedback(payload: FeedbackRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.score not in {-1, 1}:
        raise HTTPException(status_code=400, detail="Score must be -1 or 1")
    db.add(Feedback(query_id=payload.query_id, score=payload.score, comment=payload.comment))
    db.commit()
    audit(db, user.id, "feedback", f"Feedback {payload.score} for query {payload.query_id}")
    return {"status": "saved"}


@app.get("/admin/analytics")
def analytics(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    query_count = db.query(QueryLog).count()
    feedback_score = db.query(func.avg(Feedback.score)).scalar() or 0
    avg_latency = db.query(func.avg(QueryLog.latency_ms)).scalar() or 0
    total_cost = db.query(func.sum(QueryLog.cost_usd)).scalar() or 0
    avg_relevance = db.query(func.avg(QueryLog.relevance)).scalar() or 0
    avg_faithfulness = db.query(func.avg(QueryLog.faithfulness)).scalar() or 0
    hallucination = db.query(func.avg(QueryLog.hallucination_rate)).scalar() or 0
    return {
        "users": db.query(User).count(),
        "documents": db.query(Document).count(),
        "chunks": db.query(Chunk).count(),
        "questions": query_count,
        "avg_latency_ms": round(avg_latency, 2),
        "cost_usd": round(total_cost, 6),
        "accuracy": round(avg_relevance * avg_faithfulness, 3),
        "relevance": round(avg_relevance, 3),
        "faithfulness": round(avg_faithfulness, 3),
        "hallucination_rate": round(hallucination, 3),
        "feedback_score": round(feedback_score, 3),
    }


@app.get("/admin/logs")
def logs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()


@app.get("/admin/feedback")
def feedback_rows(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (
        db.query(Feedback, QueryLog, User)
        .join(QueryLog, Feedback.query_id == QueryLog.id)
        .join(User, QueryLog.user_id == User.id)
        .order_by(Feedback.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": feedback.id,
            "query_id": feedback.query_id,
            "score": feedback.score,
            "label": "Good" if feedback.score == 1 else "Wrong",
            "comment": feedback.comment,
            "question": query.question,
            "user_email": user.email,
            "created_at": feedback.created_at,
        }
        for feedback, query, user in rows
    ]


@app.get("/admin/evaluations")
def evaluations(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = (
        db.query(QueryLog, User)
        .join(User, QueryLog.user_id == User.id)
        .order_by(QueryLog.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": query.id,
            "question": query.question,
            "user_email": user.email,
            "latency_ms": query.latency_ms,
            "cost_usd": query.cost_usd,
            "relevance": query.relevance,
            "faithfulness": query.faithfulness,
            "hallucination_rate": query.hallucination_rate,
            "created_at": query.created_at,
        }
        for query, user in rows
    ]
