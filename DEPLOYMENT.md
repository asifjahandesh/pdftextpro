# PDFText Pro — Cloud Deployment Guide

## Architecture
- **Frontend**: Next.js on **Vercel** (`frontend/`)
- **API & Worker**: FastAPI + Celery on **Railway** (`backend/`)
- **PostgreSQL**: **Neon**
- **Redis**: **Upstash**
- **Object Storage**: **Cloudflare R2**

## 1. Neon (PostgreSQL)
1. Create a Neon project and database `pdftext_pro`.
2. Copy the pooled/direct connection string:
   `DATABASE_URL=postgresql+psycopg://<user>:<password>@<neon-host>/pdftext_pro?sslmode=require`

## 2. Upstash (Redis)
1. Create an Upstash Redis database.
2. Copy the TLS Redis URL:
   `REDIS_URL=rediss://default:<password>@<upstash-host>:6379`

## 3. Cloudflare R2
1. Create an R2 bucket (e.g. `pdftext-pro-uploads`).
2. Create an API token with Object Read & Write permissions.
3. Set `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET`.

## 4. Railway (Backend API + Celery Worker)
1. Create two services from `backend/` using `backend/Dockerfile`:
   - **API service**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
   - **Worker service**: `celery -A app.worker.celery worker --loglevel=info --concurrency=2`
2. Set environment variables on both services:
   - `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `CORS_ORIGINS=https://<your-vercel-domain>`
   - `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`

## 5. Vercel (Frontend)
1. Import the GitHub repository with Root Directory `frontend`.
2. Set `NEXT_PUBLIC_API_URL=https://<your-railway-api-domain>`.
3. Deploy.
