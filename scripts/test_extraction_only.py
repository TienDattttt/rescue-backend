"""
Test stage 3 với 3 comment mẫu.
Chạy trong container:
  docker compose exec backend python scripts/test_extraction_only.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()
logging.basicConfig(level=logging.INFO, force=True)

from app.services.extractor_service import ExtractorService


def main() -> None:
    test_comments = [
        {
            "id": "1",
            "text": "Nhà tôi bị ngập đến ngực, có 2 người già và 1 em bé. Địa chỉ 123 đường Lê Lợi, phường 1. Cần thuyền gấp! SĐT 0901234567",
        },
        {
            "id": "2",
            "text": "Mắc kẹt trên mái nhà, 5 người lớn, nước đang dâng. Xóm 3, thôn Bình An. Đã chờ 6 tiếng",
        },
        {
            "id": "3",
            "text": "Cần cứu trợ thực phẩm, không ngập nhưng không ra được",
        },
    ]

    svc = ExtractorService(api_key=os.getenv("GEMINI_API_KEY", ""))
    results = svc.extract_batch(test_comments)

    for index, result in enumerate(results, start=1):
        print(f"=== COMMENT {index} ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("  locationDescription:", result.get("locationDescription"))
        print("  wardCommune:", result.get("wardCommune"))
        print("  district:", result.get("district"))
        print("  province:", result.get("province"))


if __name__ == "__main__":
    main()