from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.services.classifier_service import get_classifier_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, get_classifier_service)
    logger.info('Classifier warmup completed in %.2fs', time.perf_counter() - started)
    logger.info('🚀 rescue_backend ready')
    yield


settings = get_settings()
app = FastAPI(title='Rescue Backend', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(api_v1_router, prefix='/api/v1')
app.include_router(api_v1_router)
