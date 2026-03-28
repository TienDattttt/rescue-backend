from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.cases import router as cases_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.dispatch import router as dispatch_router
from app.api.v1.pipeline import router as pipeline_router
from app.api.v1.posts import router as posts_router
from app.api.v1.presets import router as presets_router

api_v1_router = APIRouter()
api_v1_router.include_router(pipeline_router, tags=['pipeline'])
api_v1_router.include_router(cases_router, tags=['cases'])
api_v1_router.include_router(dashboard_router, tags=['dashboard'])
api_v1_router.include_router(posts_router, tags=['posts'])
api_v1_router.include_router(presets_router, tags=['presets'])
api_v1_router.include_router(dispatch_router, tags=['dispatch'])
