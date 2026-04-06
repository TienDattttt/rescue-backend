from __future__ import annotations

import os
import sys
import traceback

try:
    from app.core.config import get_settings

    settings = get_settings()
    print(f"[STARTUP] DATABASE_URL set: {bool(settings.DATABASE_URL)}", flush=True)
    print(f"[STARTUP] GEMINI_API_KEY set: {bool(settings.GEMINI_API_KEY)}", flush=True)
    print(f"[STARTUP] PHOBERT_SERVICE_URL: {os.getenv('PHOBERT_SERVICE_URL', '')}", flush=True)
except Exception as e:
    print(f"[STARTUP ERROR] Config load failed: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_v1_router
from app.core.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title='Rescue Backend')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
logger.info(f"CORS allowed origins: {settings.CORS_ORIGINS}")


@app.on_event('startup')
async def startup_check() -> None:
    logger.info('Checking database connectivity...')
    try:
        async with engine.connect() as connection:
            await connection.execute(text('SELECT 1'))
        logger.info('Database connectivity check succeeded')
    except Exception:
        logger.exception('Database connectivity check failed')
        raise

    logger.info('rescue_backend ready')


app.include_router(api_v1_router, prefix='/api/v1')
app.include_router(api_v1_router)