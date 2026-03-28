#!/bin/bash
set -e

echo "⏳ Chờ PostgreSQL..."
until pg_isready -h db -U rescue_user -d rescue_db 2>/dev/null; do
  echo "   PostgreSQL chưa sẵn sàng — thử lại sau 2s..."
  sleep 2
done
echo "✅ PostgreSQL sẵn sàng"
