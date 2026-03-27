# rescue_backend

FastAPI backend cho hệ thống điều phối cứu hộ thiên tai. Backend này chạy pipeline 4 stage:

1. Crawl comments từ Facebook post
2. Phân loại comment cầu cứu bằng PhoBERT + PEFT từ Hugging Face Hub
3. Trích xuất thông tin cứu hộ bằng OpenRouter
4. Deduplicate và lưu rescue cases vào PostgreSQL

## Chuẩn bị

1. Tạo file môi trường:

```bash
cp .env.example .env
```

Điền các biến cần thiết trong `.env`.

2. Cài dependencies:

```bash
pip install -r requirements.txt
```

3. Setup database bằng Alembic:

```bash
alembic upgrade head
```

4. Chạy server:

```bash
uvicorn app.main:app --reload --port 8000
```

## Chạy pipeline

Gửi request chạy pipeline cho một Facebook post URL:

```bash
curl -X POST http://localhost:8000/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"post_url": "https://facebook.com/..."}'
```

Nếu dùng prefix API v1:

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"post_url": "https://facebook.com/..."}'
```

Poll trạng thái job:

```bash
curl http://localhost:8000/pipeline/status/{job_id}
```

Xem rescue cases:

```bash
curl http://localhost:8000/cases
```

## Các endpoint chính

- `POST /pipeline/run`
- `GET /pipeline/status/{job_id}`
- `GET /pipeline/jobs`
- `GET /cases`
- `PATCH /cases/{case_id}`
- `GET /dashboard`
- `GET /posts`
- `GET /presets`
- `GET /dispatch-teams`

## Ghi chú triển khai

- `ClassifierService` được warmup một lần khi startup.
- Tất cả blocking operations như scraper GraphQL/requests và model inference đều được bọc qua executor.
- `raw_comment` luôn giữ nguyên đầy đủ, không truncate.
- Response schemas bám theo frontend contract tại `D:\Ki2Nam4\DSS\AHP-RESCUE\src\shared\types\domain.ts`.
