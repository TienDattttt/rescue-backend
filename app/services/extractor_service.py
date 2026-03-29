from __future__ import annotations

import json
import logging
import random
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import google.generativeai as genai

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_VULNERABLE_GROUPS = ["trẻ em", "em bé", "người già", "phụ nữ mang thai"]
VALID_SEVERITY = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_ACCESSIBILITY = {"EASY", "MODERATE", "HARD"}
PHONE_PATTERN = re.compile(r"\d+")
BATCH_SIZE = 5
DELAY_BETWEEN_BATCHES = 6
DELAY_AFTER_429 = 65
MAX_RETRIES = 3
RESULTS_DIR = Path('/app/results')


class ExtractorService:
    SYSTEM_INSTRUCTION = """
Bạn là chuyên gia phân tích tin nhắn cầu cứu thiên tai tại Việt Nam.
Chỉ trả về JSON hợp lệ, không giải thích thêm.
Nếu không tìm thấy thông tin: null cho số/chuỗi, [] cho mảng.
""".strip()

    def __init__(self, api_key: str):
        self.api_key = api_key
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name='gemini-2.5-flash-lite',
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )

    def _build_prompt(self, comments: list[dict[str, Any]]) -> str:
        numbered = "\n".join(f"[{index + 1}] {comment['text']}" for index, comment in enumerate(comments))
        count = len(comments)
        return f"""Phân tích {count} bình luận cầu cứu thiên tai Việt Nam.
Trả về JSON array đúng {count} object theo thứ tự. Chỉ JSON, không giải thích.

{numbered}

Mỗi object gồm:
{{
  "locationDescription": "Trích NGUYÊN VĂN địa chỉ/vị trí cụ thể nhất từ bình luận.
    VD: '45 đường Trần Hưng Đạo phường 5', 'xóm 3 thôn Bình An xã Hòa Phú',
    'gần cầu Rồng quận Sơn Trà', 'hẻm 12 đường Lê Lợi'.
    Nếu không có địa chỉ cụ thể → null",
  "wardCommune": "phường/xã/thị trấn cụ thể nếu được đề cập, null nếu không",
  "district": "quận/huyện/thị xã cụ thể nếu được đề cập, null nếu không",
  "province": "tỉnh/thành phố cụ thể nếu được đề cập, null nếu không",
  "numPeople": tổng số người cần cứu (integer), null nếu không rõ,
  "vulnerableGroups": chỉ các giá trị có trong
    ["trẻ em", "em bé", "người già", "phụ nữ mang thai"],
  "waitingHours": số giờ đã chờ (float), null nếu không đề cập,
  "severity": "CRITICAL" nếu nguy hiểm tính mạng ngay (đang chìm/mắc kẹt/thương nặng)
              "HIGH" nếu nguy hiểm, cần cứu trong vài giờ
              "MEDIUM" nếu cần hỗ trợ nhưng chưa nguy hiểm ngay
              "LOW" nếu chỉ cần hàng hóa/thực phẩm/thuốc,
  "accessibility": "HARD" nếu vùng sâu/sạt lở/cô lập hoàn toàn
                   "MODERATE" nếu nước chảy xiết/đường hẹp khó vào
                   "EASY" nếu thuyền/xe vào được tương đối dễ,
  "phone": chỉ chữ số của SĐT đầu tiên (VD "0901 234 567"→"0901234567"),
           null nếu không có,
  "lat": latitude nếu có tọa độ GPS/link maps rõ ràng, null nếu không,
  "lng": longitude tương tự
}}

Với địa chỉ hành chính Việt Nam:
- wardCommune: chỉ lấy tên phường/xã/thị trấn
  VD: "phường 5", "xã Hòa Phú", "thị trấn Cai Lậy"
- district: chỉ lấy tên quận/huyện
  VD: "quận 7", "huyện Cai Lậy", "TP Thủ Đức"
- province: chỉ lấy tên tỉnh/thành phố
  VD: "TP.HCM", "tỉnh Quảng Nam", "Đà Nẵng"
- locationDescription: vẫn giữ NGUYÊN VĂN đầy đủ nhất có thể
  (bao gồm số nhà, tên đường, xóm, ấp nếu có)

Ví dụ input: "nhà tôi ở 45 đường Lê Lợi phường 5 quận 3 TPHCM"
Ví dụ output:
  locationDescription: "45 đường Lê Lợi phường 5 quận 3 TPHCM"
  wardCommune: "phường 5"
  district: "quận 3"
  province: "TP.HCM"
"""

    def _checkpoint_path(self, job_id: str) -> Path:
        safe_job_id = re.sub(r'[^A-Za-z0-9_.-]+', '_', job_id or 'default')
        return RESULTS_DIR / f'stage3_checkpoint_{safe_job_id}.json'

    def _parse_response(self, raw: str, expected: int) -> list[dict[str, Any]]:
        if not raw or not raw.strip():
            return [self._null_defaults() for _ in range(expected)]

        cleaned = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return [self._null_defaults() for _ in range(expected)]

        try:
            parsed = json.loads(match.group())
        except json.JSONDecodeError:
            try:
                repaired = match.group().rstrip().rstrip(',') + ']'
                parsed = json.loads(repaired)
                logger.warning('JSON repaired thành công')
            except Exception:
                return [self._null_defaults() for _ in range(expected)]

        if not isinstance(parsed, list):
            return [self._null_defaults() for _ in range(expected)]

        while len(parsed) < expected:
            parsed.append(self._null_defaults())
        return [self._sanitize_item(item if isinstance(item, dict) else self._null_defaults()) for item in parsed[:expected]]

    def _null_defaults(self) -> dict[str, Any]:
        return {
            'locationDescription': None,
            'wardCommune': None,
            'district': None,
            'province': None,
            'numPeople': None,
            'vulnerableGroups': [],
            'waitingHours': None,
            'severity': 'MEDIUM',
            'accessibility': 'MODERATE',
            'phone': None,
            'lat': None,
            'lng': None,
        }

    def _call_gemini(self, prompt: str) -> str:
        for attempt in range(MAX_RETRIES):
            try:
                response = self.model.generate_content(self.SYSTEM_INSTRUCTION + '\n\n' + prompt)
                text = getattr(response, 'text', '')
                logger.info('Gemini response length: %s', len(text) if text else 0)
                logger.info('Gemini response: %s', text)
                return text or ''
            except Exception as exc:
                err_str = str(exc)
                if '429' in err_str or 'RESOURCE_EXHAUSTED' in err_str:
                    logger.warning('429 rate limit, chờ %ss...', DELAY_AFTER_429)
                    time.sleep(DELAY_AFTER_429)
                else:
                    logger.warning('Gemini lỗi attempt %s: %s', attempt + 1, exc)
                    time.sleep(5)
        return ''

    def save_checkpoint(self, job_id: str, results: list[dict[str, Any]], next_index: int) -> None:
        checkpoint_path = self._checkpoint_path(job_id)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps({'next_index': next_index, 'results': results}, ensure_ascii=False),
            encoding='utf-8',
        )

    def load_checkpoint(self, job_id: str) -> tuple[list[dict[str, Any]], int]:
        checkpoint_path = self._checkpoint_path(job_id)
        if checkpoint_path.exists():
            data = json.loads(checkpoint_path.read_text(encoding='utf-8'))
            logger.info('Resume job %s từ index %s', job_id, data.get('next_index'))
            return list(data.get('results') or []), int(data.get('next_index') or 0)
        return [], 0

    def clear_checkpoint(self, job_id: str) -> None:
        checkpoint_path = self._checkpoint_path(job_id)
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    def extract_batch(self, comments: list[dict[str, Any]], job_id: str = 'default') -> list[dict[str, Any]]:
        if not comments:
            return []

        results, start_index = self.load_checkpoint(job_id)
        batches = [comments[index : index + BATCH_SIZE] for index in range(0, len(comments), BATCH_SIZE)]

        for index, batch in enumerate(batches):
            batch_start = index * BATCH_SIZE
            if batch_start < start_index:
                continue

            if index > 0:
                time.sleep(DELAY_BETWEEN_BATCHES + random.uniform(0, 2))

            prompt = self._build_prompt(batch)
            raw = self._call_gemini(prompt)
            batch_result = self._parse_response(raw, len(batch))
            results.extend(batch_result)
            self.save_checkpoint(job_id, results, batch_start + len(batch))
            logger.info('Extraction: %s/%s comments', min(batch_start + len(batch), len(comments)), len(comments))

        self.clear_checkpoint(job_id)
        return results

    def _sanitize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        vulnerable = [group for group in item.get('vulnerableGroups') or [] if group in ALLOWED_VULNERABLE_GROUPS]
        severity = str(item.get('severity') or 'MEDIUM').upper()
        if severity not in VALID_SEVERITY:
            severity = 'MEDIUM'
        accessibility = str(item.get('accessibility') or 'MODERATE').upper()
        if accessibility not in VALID_ACCESSIBILITY:
            accessibility = 'MODERATE'

        phone = item.get('phone')
        if phone is not None:
            digits = ''.join(PHONE_PATTERN.findall(str(phone)))
            phone = digits or None

        lat = self._coerce_float(item.get('lat'))
        lng = self._coerce_float(item.get('lng'))
        if lat is None or lng is None or not (8 <= lat <= 24 and 102 <= lng <= 110):
            lat = None
            lng = None

        return {
            'locationDescription': self._normalize_optional_string(item.get('locationDescription')),
            'wardCommune': self._normalize_optional_string(item.get('wardCommune')),
            'district': self._normalize_optional_string(item.get('district')),
            'province': self._normalize_optional_string(item.get('province')),
            'numPeople': self._coerce_int(item.get('numPeople')),
            'vulnerableGroups': vulnerable,
            'waitingHours': self._coerce_float(item.get('waitingHours')),
            'severity': severity,
            'accessibility': accessibility,
            'phone': phone,
            'lat': lat,
            'lng': lng,
        }

    def _normalize_optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _coerce_int(self, value: Any) -> int | None:
        if value in (None, ''):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _coerce_float(self, value: Any) -> float | None:
        if value in (None, ''):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


@lru_cache(maxsize=1)
def get_extractor_service() -> ExtractorService:
    settings = get_settings()
    return ExtractorService(api_key=settings.GEMINI_API_KEY)