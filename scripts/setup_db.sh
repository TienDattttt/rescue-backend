#!/bin/bash
set -e

if [ -f "/.dockerenv" ]; then
  echo "🐳 Đang chạy setup DB trong Docker container"
  export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://rescue_user:rescue_pass@db:5432/rescue_db}"
else
  echo "💻 Đang chạy setup DB trên host"
  export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://rescue_user:rescue_pass@localhost:5432/rescue_db}"
fi

echo "🔎 Kiểm tra môi trường trước khi migrate"
python scripts/verify_setup.py

echo "🗃️ Chạy Alembic migrations"
alembic upgrade head

echo "✅ Database sẵn sàng"
