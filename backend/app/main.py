import hashlib
import logging
import os
import re
import time
import uuid
from pathlib import Path

import fitz
import redis
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import (
    create_access_token,
    get_current_user,
    get_owned_document,
    hash_password,
    verify_password,
)
from .db import get_db
from .models import Document, DocumentPage, User
from .storage import delete_stored_file, upload_to_r2_if_enabled
from .worker import (
    process_document,
    retry_failed_pages,
    run_process_document,
    run_retry_failed_pages,
)

PROCESSING_MODE = os.getenv("PROCESSING_MODE", "celery").strip().lower()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./data/uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "120"))
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "300"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ALLOWED_MIME_TYPES = {"application/pdf", "application/octet-stream", ""}

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

logger = logging.getLogger("pdftext.api")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI(title="PDFText Pro API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class AuthRequest(BaseModel):
    email: str
    password: str


@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    minute_bucket = int(time.time() // 60)
    rl_key = f"rl:{client_ip}:{minute_bucket}"
    try:
        count = redis_client.incr(rl_key)
        if count == 1:
            redis_client.expire(rl_key, 60)
        if count > RATE_LIMIT_PER_MIN:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded."})
    except redis.RedisError:
        pass

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.post("/auth/register", status_code=201)
def register(payload: AuthRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email is required.")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Email already registered.")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": str(user.id), "email": user.email}


@app.post("/auth/login")
def login(payload: AuthRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    fail_key = f"login_fail:{client_ip}:{email}"
    try:
        fails = int(redis_client.get(fail_key) or 0)
        if fails >= MAX_LOGIN_ATTEMPTS:
            raise HTTPException(429, "Too many failed login attempts. Try again later.")
    except redis.RedisError:
        pass

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        try:
            cnt = redis_client.incr(fail_key)
            if cnt == 1:
                redis_client.expire(fail_key, LOGIN_LOCKOUT_SECONDS)
        except redis.RedisError:
            pass
        raise HTTPException(401, "Invalid email or password.")

    try:
        redis_client.delete(fail_key)
    except redis.RedisError:
        pass
    token = create_access_token(str(user.id))
    return {"access_token": token, "token_type": "bearer"}


@app.get("/documents")
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "documents": [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "file_size": doc.file_size,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "status": doc.status,
                "total_pages": doc.total_pages,
                "completed_pages": doc.completed_pages,
                "progress": (doc.completed_pages / doc.total_pages * 100 if doc.total_pages else 0),
                "language": doc.language,
                "error": doc.error,
            }
            for doc in docs
        ]
    }


@app.post("/documents")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = "auto",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    safe_name = Path(file.filename or "").name
    if not safe_name or not safe_name.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file.")
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Unsupported MIME type: {content_type}")

    doc_id = uuid.uuid4()
    dest = (UPLOAD_DIR / f"{doc_id}.pdf").resolve()
    if dest.parent != UPLOAD_DIR:
        raise HTTPException(400, "Invalid storage path.")
    path = str(dest)
    size = 0
    sha256 = hashlib.sha256()
    try:
        with open(dest, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_MB * 1024 * 1024:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"File exceeds {MAX_MB} MB limit.")
                sha256.update(chunk)
                out.write(chunk)
        with open(dest, "rb") as chk:
            if chk.read(5) != b"%PDF-":
                dest.unlink(missing_ok=True)
                raise HTTPException(400, "Invalid PDF signature.")
        try:
            with fitz.open(dest) as pdf_check:
                if len(pdf_check) < 1:
                    raise ValueError("PDF has no pages.")
        except Exception:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, "Malformed or unreadable PDF file.")

        checksum = sha256.hexdigest()
        existing = db.execute(
            select(Document).where(
                Document.user_id == current_user.id,
                Document.file_checksum == checksum,
            )
        ).scalar_one_or_none()
        if existing:
            dest.unlink(missing_ok=True)
            return {
                "id": str(existing.id),
                "status": existing.status,
                "duplicate": True,
            }
        path = upload_to_r2_if_enabled(dest, f"{doc_id}.pdf")
        doc = Document(
            id=doc_id,
            user_id=current_user.id,
            filename=safe_name[:255],
            file_path=path,
            file_size=size,
            file_checksum=checksum,
            language=language,
            status="queued",
        )
        db.add(doc)
        db.commit()
        if PROCESSING_MODE == "inline":
            background_tasks.add_task(run_process_document, str(doc_id), "inline")
        else:
            process_document.delay(str(doc_id))
        return {"id": str(doc_id), "status": "queued"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        dest.unlink(missing_ok=True)
        logger.exception("Upload failed: %s", e)
        raise HTTPException(500, "Internal server error.")


@app.get("/documents/{doc_id}")
def get_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_owned_document(doc_id, current_user, db)
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "file_size": doc.file_size,
        "file_checksum": doc.file_checksum,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "status": doc.status,
        "total_pages": doc.total_pages,
        "completed_pages": doc.completed_pages,
        "progress": (doc.completed_pages / doc.total_pages * 100 if doc.total_pages else 0),
        "language": doc.language,
        "error": doc.error,
    }


@app.get("/documents/{doc_id}/text")
def get_text(
    doc_id: uuid.UUID,
    page: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_owned_document(doc_id, current_user, db)
    if page is not None:
        p = db.execute(
            select(DocumentPage).where(
                DocumentPage.document_id == doc.id,
                DocumentPage.page_number == page,
            )
        ).scalar_one_or_none()
        if not p:
            raise HTTPException(404, "Page text not available")
        return {"page": page, "text": p.text}
    pages = (
        db.query(DocumentPage)
        .filter_by(document_id=doc.id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    return {"pages": [{"page": p.page_number, "text": p.text} for p in pages]}


@app.get("/documents/{doc_id}/download")
def download_text(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_owned_document(doc_id, current_user, db)
    pages = (
        db.query(DocumentPage)
        .filter_by(document_id=doc.id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    content = "\n\n".join(f"--- Page {p.page_number} ---\n{p.text}" for p in pages)
    raw_name = doc.filename.rsplit(".", 1)[0] + ".txt"
    safe_dl_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f'attachment; filename="{safe_dl_name}"'},
    )


@app.post("/documents/{doc_id}/resume")
def resume_document(
    doc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_owned_document(doc_id, current_user, db)
    if doc.status == "processing":
        raise HTTPException(409, "Document is already processing.")
    doc.status = "queued"
    db.commit()
    if PROCESSING_MODE == "inline":
        background_tasks.add_task(run_process_document, str(doc.id), "inline")
    else:
        try:
            process_document.delay(str(doc.id))
        except Exception as e:
            raise HTTPException(503, f"Worker queue unavailable: {e}")
    return {"id": str(doc.id), "status": "queued"}


@app.delete("/documents/{doc_id}")
def delete_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_owned_document(doc_id, current_user, db)
    file_path = doc.file_path
    db.delete(doc)
    db.commit()
    delete_stored_file(file_path)
    return {"id": str(doc.id), "deleted": True}


@app.post("/documents/{doc_id}/retry-failed")
def retry_failed(
    doc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_owned_document(doc_id, current_user, db)
    if doc.status == "processing":
        raise HTTPException(409, "Document is already processing.")
    if PROCESSING_MODE == "inline":
        background_tasks.add_task(run_retry_failed_pages, str(doc.id), "inline")
    else:
        try:
            retry_failed_pages.delay(str(doc.id))
        except Exception as e:
            raise HTTPException(503, f"Worker queue unavailable: {e}")
    return {"id": str(doc.id), "status": "retrying_failed_pages"}
