from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / '.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore',
    )

    DATABASE_URL: str
    OPENROUTER_API_KEY: str = ''
    HF_MODEL_ID: str = 'dat201204/phobert-vi-caucu-classifier'
    CLASSIFIER_THRESHOLD: float = 0.4
    CLASSIFIER_DEVICE: str = 'cpu'
    OPENROUTER_MODEL: str = 'meta-llama/llama-3.3-70b-instruct:free'
    CORS_ORIGINS: list[str] = ['http://localhost:5173']

    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith('['):
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in raw.split(',') if item.strip()]
        raise TypeError('CORS_ORIGINS must be a comma-separated string or a JSON array.')


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
