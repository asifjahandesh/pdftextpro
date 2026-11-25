# PDFText Pro - Large PDF text extraction starter

A starter scaffold for extracting text from large PDFs (1000+ pages) in Bangla, English, Hindi, Arabic and Spanish.

## Stack
- Next.js frontend (minimal upload/progress/result UI)
- FastAPI backend
- PostgreSQL
- Redis + Celery background worker
- PyMuPDF for digital PDF extraction
- Tesseract OCR for scanned pages

## Architecture notes
This is a starter project, not a production-hardened deployment. Processing is page-batched, checkpointed and stored in PostgreSQL. Upload original PDFs to a storage directory. Use a worker for OCR rather than running extraction inside the HTTP request.

## Quick start (Docker)
1. Install Docker Desktop.
2. Copy `.env.example` to `.env`.
3. Run `docker compose up --build`.
4. Backend: http://localhost:8000
5. Frontend: http://localhost:3000

The worker uses Tesseract language packs: `ben`, `eng`, `hin`, `ara`, `spa`.

## Limitations / next hardening steps
- Add authentication, rate limits, upload limits, malware scanning and retention policy.
- Use object storage instead of local volume for multi-host deployments.
- Add PDF page rendering DPI controls, OCR quality checks and page-level retry.
- Set worker concurrency based on server RAM/CPU.
- For very large files, use resumable upload and avoid loading full file into RAM.
