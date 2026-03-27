from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from typing import Any

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
ALLOWED_VULNERABLE_GROUPS = ['trẻ em', 'em bé', 'người già', 'phụ nữ mang thai']
VALID_SEVERITY = {'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'}
VALID_ACCESSIBILITY = {'EASY', 'MODERATE', 'HARD'}
JSON_BLOCK_PATTERN = re.compile(r'```(?:json)?\s*(.*?)```', re.DOTALL | re.IGNORECASE)
PHONE_PATTERN = re.compile(r'\d+')


class ExtractorService:
    SYSTEM_PROMPT = (
        'Bạn là chuyên gia phân tích tin nhắn cầu cứu trong thiên tai tại Việt Nam.\n'
        'Nhiệm vụ: trích xuất thông tin cứu hộ từ bình luận Facebook.\n'
        'Luôn trả về JSON hợp lệ, không giải thích thêm.\n'
        'Nếu không tìm thấy thông tin, dùng null cho số/chuỗi, [] cho mảng.'
    )

    def __init__(self, api_key: str, default_model: str) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.session = requests.Session()

    def extract_batch(self, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not comments:
            return []
        if len(comments) > 10:
            results: list[dict[str, Any]] = []
            for start in range(0, len(comments), 10):
                results.extend(self.extract_batch(comments[start : start + 10]))
            return results

        payload = self._build_payload(comments)
        try:
            response = self._try_models_in_order(payload)
            parsed = self._parse_response_array(response, expected_count=len(comments))
            if parsed is None:
                raise ValueError('Batch response is not valid JSON array')
            return [self._sanitize_item(item) for item in parsed]
        except Exception as exc:
            logger.warning('Batch extraction failed, falling back to single-comment mode: %s', exc)
            fallback_results: list[dict[str, Any]] = []
            for comment in comments:
                try:
                    single_payload = self._build_payload([comment])
                    response = self._try_models_in_order(single_payload)
                    parsed = self._parse_response_array(response, expected_count=1)
                    if not parsed:
                        raise ValueError('Single extraction returned empty payload')
                    fallback_results.append(self._sanitize_item(parsed[0]))
                except Exception as inner_exc:
                    logger.warning('Single-comment extraction failed for comment=%s: %s', comment.get('id'), inner_exc)
                    fallback_results.append(self._null_result())
            return fallback_results

    def _build_payload(self, comments: list[dict[str, Any]]) -> dict[str, Any]:
        lines = [
            f'Phân tích {len(comments)} bình luận cầu cứu sau. Trả về JSON array gồm {len(comments)} object theo đúng thứ tự.',
            '',
        ]
        for index, comment in enumerate(comments, start=1):
            lines.append(f'[{index}] {comment.get("text", "")}')
        lines.extend(
            [
                '',
                'Trả về array JSON:',
                '[',
                '{',
                '  "locationDescription": "địa chỉ/vị trí cụ thể được nhắc đến, hoặc null",',
                '  "numPeople": số người cần cứu (integer) hoặc null,',
                '  "vulnerableGroups": ["trẻ em","em bé","người già","phụ nữ mang thai"] — chỉ nhóm nào thực sự được đề cập,',
                '  "waitingHours": số giờ đã chờ (number) hoặc null,',
                '  "severity": một trong "CRITICAL"|"HIGH"|"MEDIUM"|"LOW",',
                '  "accessibility": một trong "EASY"|"MODERATE"|"HARD",',
                '  "phone": "số điện thoại đầu tiên tìm thấy, chỉ chữ số" hoặc null,',
                '  "lat": tọa độ latitude nếu có GPS link/tọa độ rõ ràng, ngược lại null,',
                '  "lng": tọa độ longitude nếu có GPS link/tọa độ rõ ràng, ngược lại null',
                '}',
                ']',
                '',
                'Quy tắc severity:',
                '- CRITICAL: nguy hiểm tính mạng ngay (đang chìm, mắc kẹt, thương nặng)',
                '- HIGH: nguy hiểm, cần cứu trong vài giờ',
                '- MEDIUM: cần hỗ trợ nhưng chưa nguy hiểm ngay',
                '- LOW: cần hàng hóa, thực phẩm, thuốc',
                '',
                'Quy tắc accessibility:',
                '- EASY: đường lớn, thuyền vào dễ',
                '- MODERATE: nước chảy xiết, đường hẹp',
                '- HARD: vùng sâu, sạt lở cô lập',
            ]
        )
        return {
            'messages': [
                {'role': 'system', 'content': self.SYSTEM_PROMPT},
                {'role': 'user', 'content': '\n'.join(lines)},
            ],
            'temperature': 0.1,
            'max_tokens': 1200,
        }

    def _ordered_models(self) -> list[str]:
        models = [
            self.default_model,
            'meta-llama/llama-3.3-70b-instruct:free',
            'google/gemini-2.0-flash-exp:free',
            'mistralai/mistral-7b-instruct:free',
        ]
        ordered: list[str] = []
        for model in models:
            if model and model not in ordered:
                ordered.append(model)
        return ordered

    def _try_models_in_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError('OPENROUTER_API_KEY chưa được cấu hình.')

        last_error: Exception | None = None
        for model_name in self._ordered_models():
            try:
                request_payload = dict(payload)
                request_payload['model'] = model_name
                return self._post_with_retry(request_payload)
            except Exception as exc:
                logger.warning('OpenRouter model %s failed: %s', model_name, exc)
                last_error = exc
        raise RuntimeError(f'Không model OpenRouter nào trả kết quả thành công: {last_error}')

    def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'http://localhost:8000',
            'X-Title': 'rescue_backend',
        }
        attempts = 3
        for attempt in range(1, attempts + 1):
            response = self.session.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
            if response.status_code < 400:
                return response.json()
            if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts:
                time.sleep(2 ** (attempt - 1))
                continue
            raise RuntimeError(f'OpenRouter error {response.status_code}: {response.text}')
        raise RuntimeError('OpenRouter request exhausted retries')

    def _parse_response_array(self, response_json: dict[str, Any], expected_count: int) -> list[dict[str, Any]] | None:
        content = response_json.get('choices', [{}])[0].get('message', {}).get('content', '')
        if not content:
            return None

        candidate = content.strip()
        match = JSON_BLOCK_PATTERN.search(candidate)
        if match:
            candidate = match.group(1).strip()

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find('[')
            end = candidate.rfind(']')
            if start == -1 or end == -1 or end <= start:
                logger.warning('Invalid JSON from extractor: %s', content)
                return None
            try:
                parsed = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                logger.warning('Invalid JSON from extractor: %s', content)
                return None

        if not isinstance(parsed, list) or len(parsed) != expected_count:
            logger.warning(
                'Extractor returned %s objects; expected %s. Raw=%s',
                len(parsed) if isinstance(parsed, list) else 'non-list',
                expected_count,
                content,
            )
            return None
        return [item if isinstance(item, dict) else {} for item in parsed]

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
            'numPeople': self._coerce_int(item.get('numPeople')),
            'vulnerableGroups': vulnerable,
            'waitingHours': self._coerce_float(item.get('waitingHours')),
            'severity': severity,
            'accessibility': accessibility,
            'phone': phone,
            'lat': lat,
            'lng': lng,
        }

    def _null_result(self) -> dict[str, Any]:
        return {
            'locationDescription': None,
            'numPeople': None,
            'vulnerableGroups': [],
            'waitingHours': None,
            'severity': 'MEDIUM',
            'accessibility': 'MODERATE',
            'phone': None,
            'lat': None,
            'lng': None,
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
    return ExtractorService(api_key=settings.OPENROUTER_API_KEY, default_model=settings.OPENROUTER_MODEL)
