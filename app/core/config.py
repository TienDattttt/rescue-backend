from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    GEMINI_API_KEY: str = ''
    HF_MODEL_ID: str = 'dat201204/phobert-vi-caucu-classifier'
    CLASSIFIER_THRESHOLD: float = 0.4
    CLASSIFIER_DEVICE: str = 'cpu'
    OPENROUTER_MODEL: str = 'meta-llama/llama-3.3-70b-instruct:free'
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ['http://localhost:5173']

    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def normalize_database_url(cls, value: Any) -> str:
        if value is None:
            raise TypeError('DATABASE_URL is required.')

        url = str(value).strip()
        if not url:
            raise ValueError('DATABASE_URL is required.')

        if url.startswith('postgresql+asyncpg://'):
            return url
        if url.startswith('postgresql+psycopg2://'):
            return 'postgresql+asyncpg://' + url[len('postgresql+psycopg2://'):]
        if url.startswith('postgresql://'):
            return 'postgresql+asyncpg://' + url[len('postgresql://'):]
        if url.startswith('postgres://'):
            return 'postgresql+asyncpg://' + url[len('postgres://'):]
        return url

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