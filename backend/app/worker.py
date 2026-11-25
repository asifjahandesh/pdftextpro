import gc
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import fitz
import pytesseract
from celery import Celery
from dotenv import load_dotenv
from PIL import Image
from sqlalchemy import func, select

from .db import SessionLocal
from .models import Document, DocumentPage, ProcessingJob
from .storage import download_for_processing

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery = Celery("pdftext", broker=REDIS_URL, backend=REDIS_URL)

# Configure Tesseract executable and tessdata directory for native Windows
_DEFAULT_WIN_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if _TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
elif os.name == "nt" and os.path.exists(_DEFAULT_WIN_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = _DEFAULT_WIN_TESSERACT

_LOCAL_TESSDATA = Path(__file__).resolve().parents[1] / "tessdata"
if not os.getenv("TESSDATA_PREFIX") and _LOCAL_TESSDATA.is_dir():
    os.environ["TESSDATA_PREFIX"] = str(_LOCAL_TESSDATA)

LANG_MAP = {
    "bangla": "ben",
    "bengali": "ben",
    "ben": "ben",
    "english": "eng",
    "eng": "eng",
    "hindi": "hin",
    "hin": "hin",
    "arabic": "ara",
    "ara": "ara",
    "spanish": "spa",
    "spa": "spa",
}
OCR_LANGS = "ben+eng+hin+ara+spa"
MIN_DIGITAL_TEXT_LEN = 30


def resolve_ocr_lang(language: str | None) -> str:
    """Resolve user-selected language or 'auto' into a Tesseract lang string."""
    if not language or language.strip().lower() == "auto":
        return OCR_LANGS
    parts = [p.strip().lower() for p in re.split(r"[+,\s]+", language) if p.strip()]
    mapped = [LANG_MAP[p] for p in parts if p in LANG_MAP]
    return "+".join(dict.fromkeys(mapped)) if mapped else OCR_LANGS


def page_text(page: fitz.Page, lang: str) -> tuple[str, str]:
    """Extract digital text if sufficient; otherwise fall back to Tesseract OCR."""
    txt = page.get_text("text").strip()
    if len(txt) >= MIN_DIGITAL_TEXT_LEN:
        return txt, "text"
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    try:
        ocr_txt = pytesseract.image_to_string(img, lang=lang or OCR_LANGS).strip()
        return ocr_txt, "ocr"
    finally:
        img.close()
        del pix, img


def _upsert_page(
    db,
    doc_id: uuid.UUID,
    page_number: int,
    text: str,
    method: str,
    status: str,
) -> None:
    existing = db.execute(
        select(DocumentPage).where(
            DocumentPage.document_id == doc_id,
            DocumentPage.page_number == page_number,
        )
    ).scalar_one_or_none()
    if existing:
        existing.text = text
        existing.method = method
        existing.status = status
    else:
        db.add(
            DocumentPage(
                document_id=doc_id,
                page_number=page_number,
                text=text,
                method=method,
                status=status,
            )
        )


def _finalize_document(db, doc: Document, job: ProcessingJob) -> None:
    done_count = db.scalar(
        select(func.count()).where(
            DocumentPage.document_id == doc.id,
            DocumentPage.status == "done",
        )
    ) or 0
    failed_count = db.scalar(
        select(func.count()).where(
            DocumentPage.document_id == doc.id,
            DocumentPage.status == "failed",
        )
    ) or 0

    # Stream page texts in chunks to keep memory bounded on 10,000+ page documents
    rows = db.execute(
        select(DocumentPage.text)
        .where(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number)
    ).yield_per(500)
    doc.extracted_text = "\n\n".join((row[0] or "") for row in rows)
    doc.completed_pages = done_count

    if failed_count > 0:
        doc.status = "completed_with_errors"
        doc.error = f"{failed_count} page(s) failed"
        job.status = "completed_with_errors"
        job.error = doc.error
    else:
        doc.status = "completed"
        doc.error = ""
        job.status = "completed"
        job.error = ""
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


@celery.task(bind=True)
def process_document(self, doc_id: str) -> None:
    db = SessionLocal()
    job = None
    try:
        doc_uuid = uuid.UUID(str(doc_id))
        doc = db.get(Document, doc_uuid)
        if not doc:
            return

        batch = int(os.getenv("BATCH_SIZE", "20"))
        job = ProcessingJob(
            document_id=doc.id,
            celery_task_id=self.request.id,
            status="processing",
            checkpoint_page=doc.completed_pages,
            batch_size=batch,
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        doc.status = "processing"
        doc.error = ""
        db.commit()

        lang = resolve_ocr_lang(doc.language)
        local_pdf_path, is_temp_pdf = download_for_processing(doc.file_path)
        with fitz.open(local_pdf_path) as pdf:
            total = len(pdf)
            doc.total_pages = total
            db.commit()

            for start in range(0, total, batch):
                end = min(start + batch, total)
                done_in_batch = set(
                    db.scalars(
                        select(DocumentPage.page_number).where(
                            DocumentPage.document_id == doc.id,
                            DocumentPage.page_number.between(start + 1, end),
                            DocumentPage.status == "done",
                        )
                    ).all()
                )
                if len(done_in_batch) == (end - start):
                    continue

                for idx in range(start, end):
                    page_num = idx + 1
                    if page_num in done_in_batch:
                        continue
                    try:
                        txt, method = page_text(pdf[idx], lang)
                        _upsert_page(db, doc.id, page_num, txt, method, "done")
                    except Exception as page_err:
                        _upsert_page(db, doc.id, page_num, f"[ERROR] {page_err}", "error", "failed")

                done_total = db.scalar(
                    select(func.count()).where(
                        DocumentPage.document_id == doc.id,
                        DocumentPage.status == "done",
                    )
                ) or 0
                doc.completed_pages = done_total
                job.checkpoint_page = end
                db.commit()
                gc.collect()

        if is_temp_pdf:
            Path(local_pdf_path).unlink(missing_ok=True)
        _finalize_document(db, doc, job)
    except Exception as e:
        db.rollback()
        try:
            doc_uuid = uuid.UUID(str(doc_id))
            doc = db.get(Document, doc_uuid)
            if doc:
                doc.status = "failed"
                doc.error = str(e)
            if job is not None:
                job.status = "failed"
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()


@celery.task(bind=True)
def retry_failed_pages(self, doc_id: str) -> None:
    """Re-process only pages with status == 'failed' for a document."""
    db = SessionLocal()
    job = None
    try:
        doc_uuid = uuid.UUID(str(doc_id))
        doc = db.get(Document, doc_uuid)
        if not doc:
            return

        failed_pages = (
            db.query(DocumentPage)
            .filter(
                DocumentPage.document_id == doc.id,
                DocumentPage.status == "failed",
            )
            .order_by(DocumentPage.page_number)
            .all()
        )
        if not failed_pages:
            return

        batch = int(os.getenv("BATCH_SIZE", "20"))
        job = ProcessingJob(
            document_id=doc.id,
            celery_task_id=self.request.id,
            status="processing",
            checkpoint_page=doc.completed_pages,
            batch_size=batch,
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        doc.status = "processing"
        db.commit()

        lang = resolve_ocr_lang(doc.language)
        local_pdf_path, is_temp_pdf = download_for_processing(doc.file_path)
        with fitz.open(local_pdf_path) as pdf:
            for i, page_row in enumerate(failed_pages, start=1):
                try:
                    txt, method = page_text(pdf[page_row.page_number - 1], lang)
                    page_row.text = txt
                    page_row.method = method
                    page_row.status = "done"
                except Exception as page_err:
                    page_row.text = f"[ERROR] {page_err}"
                    page_row.status = "failed"
                if i % batch == 0:
                    db.commit()
                    gc.collect()

        if is_temp_pdf:
            Path(local_pdf_path).unlink(missing_ok=True)
        _finalize_document(db, doc, job)
    except Exception as e:
        db.rollback()
        try:
            doc_uuid = uuid.UUID(str(doc_id))
            doc = db.get(Document, doc_uuid)
            if doc:
                doc.status = "failed"
                doc.error = str(e)
            if job is not None:
                job.status = "failed"
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
