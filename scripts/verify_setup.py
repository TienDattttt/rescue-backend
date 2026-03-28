from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

IS_DOCKER = os.path.exists('/.dockerenv')
BASE_DIR = Path(__file__).resolve().parents[1]
EXPECTED_HOST = 'db' if IS_DOCKER else 'localhost'
DEFAULT_URL = (
    'postgresql+asyncpg://rescue_user:rescue_pass@db:5432/rescue_db'
    if IS_DOCKER
    else 'postgresql+asyncpg://rescue_user:rescue_pass@localhost:5432/rescue_db'
)


def main() -> None:
    if IS_DOCKER:
        print('🐳 Đang chạy trong Docker container')
    else:
        print('💻 Đang chạy trên host')

    database_url = os.getenv('DATABASE_URL', DEFAULT_URL)
    parsed = urlparse(database_url)
    db_host = parsed.hostname or ''
    db_port = parsed.port or 5432

    print(f'DATABASE_URL: {database_url}')
    print(f'DB host detected: {db_host}:{db_port}')

    if db_host != EXPECTED_HOST:
        print(f'⚠️ DATABASE_URL host nên là {EXPECTED_HOST} trong môi trường hiện tại')
    else:
        print('✅ DATABASE_URL host khớp môi trường hiện tại')

    required_paths = [
        BASE_DIR / 'alembic.ini',
        BASE_DIR / 'alembic' / 'env.py',
        BASE_DIR / 'app' / 'main.py',
    ]
    for path in required_paths:
        if path.exists():
            print(f'✅ Found: {path.relative_to(BASE_DIR)}')
        else:
            print(f'❌ Missing: {path.relative_to(BASE_DIR)}')

    if IS_DOCKER:
        print('Hướng dẫn: dùng service name db:5432 khi container backend kết nối PostgreSQL.')
    else:
        print('Hướng dẫn: dùng localhost:5432 khi chạy backend trực tiếp trên host.')


if __name__ == '__main__':
    main()
