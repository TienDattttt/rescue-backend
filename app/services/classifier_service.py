from __future__ import annotations

import logging
import re
import threading
import unicodedata
from functools import lru_cache
from typing import Any

import torch
try:
    from peft import AutoPeftModelForSequenceClassification, PeftModel
except ImportError:  # pragma: no cover
    from peft import PeftModel
    AutoPeftModelForSequenceClassification = None
from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding

try:
    from underthesea import word_tokenize
except ImportError:  # pragma: no cover
    word_tokenize = None

from app.core.config import get_settings

# NOTE: ClassifierService local chỉ dùng cho Gradio demo và script test local.
# Production pipeline của rescue_backend gọi PhoBERT service qua HTTP trong stage2_classifier.py
# -> cấu hình bằng PHOBERT_SERVICE_URL trong .env.
logger = logging.getLogger(__name__)

ZERO_WIDTH_PATTERN = re.compile(r'[\u200b\u200c\u200d\ufeff]')
WHITESPACE_PATTERN = re.compile(r'\s+')
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+', re.IGNORECASE)
PHONE_PATTERN = re.compile(r'(?:\+?84|0)(?:\d[ .-]?){8,10}\d')
SAFE_HINTS = ('da duoc cuu', 'da an toan', 'cam on', 'duoc cuu hom qua')
RESCUE_TERMS = ('cuu', 'sos', 'ai cuu', 'can cuu', 'can giup', 'cuu ho', 'khan cap')
TRAP_TERMS = ('ket', 'mac ket', 'khong thoat', 'thoat khong duoc', 'co lap')
FLOOD_TERMS = ('ngap', 'nuoc len', 'nuoc dang', 'ngap toi', 'ngap sau', 'toi mai', 'toi nguc')
REQUEST_TERMS = ('can ca no', 'can xuong', 'can thuyen', 'can cuu ho')
VULNERABLE_TERMS = ('nguoi gia', 'tre em', 'em be', 'mot minh', 'ba bau')
ID2LABEL = {0: 'khong_cau_cuu', 1: 'cau_cuu'}
LABEL2ID = {'khong_cau_cuu': 0, 'cau_cuu': 1}


class BatchCommentDataset(torch.utils.data.Dataset):
    def __init__(self, texts: list[str], tokenizer: Any, max_length: int) -> None:
        self.encodings = tokenizer(texts, truncation=True, max_length=max_length, padding=False)

    def __len__(self) -> int:
        return len(next(iter(self.encodings.values()))) if self.encodings else 0

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return {key: torch.tensor(value[index], dtype=torch.long) for key, value in self.encodings.items()}


class ClassifierService:
    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self, model_id: str, threshold: float, device: str) -> None:
        self.model_id = model_id
        self.threshold = float(threshold)
        self.max_length = 256
        self.device = self._resolve_device(device)
        self._predict_lock = threading.RLock()

        self.tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=False)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token or self.tokenizer.sep_token or self.tokenizer.unk_token

        self.model, self.model_load_mode = self._load_model(model_id)
        self.model.to(self.device)
        self.model.eval()
        logger.info('Classifier loaded from %s with mode=%s on device=%s', model_id, self.model_load_mode, self.device)

    def _resolve_device(self, device: str) -> torch.device:
        normalized = (device or 'cpu').lower()
        if normalized == 'cuda':
            if not torch.cuda.is_available():
                raise RuntimeError('CLASSIFIER_DEVICE=cuda nhưng CUDA không khả dụng.')
            return torch.device('cuda')
        if normalized == 'auto':
            return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        return torch.device('cpu')

    def _load_model(self, model_id: str) -> tuple[Any, str]:
        try:
            base_model = AutoModelForSequenceClassification.from_pretrained(
                'vinai/phobert-base',
                num_labels=2,
                id2label=ID2LABEL,
                label2id=LABEL2ID,
            )
            model = PeftModel.from_pretrained(base_model, model_id)
            return model, 'base+peft'
        except Exception as exc:
            logger.warning('Base+PEFT load failed for %s, falling back: %s', model_id, exc)

        if AutoPeftModelForSequenceClassification is not None:
            try:
                model = AutoPeftModelForSequenceClassification.from_pretrained(model_id)
                return model, 'auto-peft'
            except Exception as exc:
                logger.warning('AutoPeft load failed for %s, falling back to plain transformers: %s', model_id, exc)

        model = AutoModelForSequenceClassification.from_pretrained(model_id)
        return model, 'transformers'

    def normalize_whitespace(self, text: str) -> str:
        normalized = unicodedata.normalize('NFC', text or '')
        normalized = ZERO_WIDTH_PATTERN.sub(' ', normalized)
        return WHITESPACE_PATTERN.sub(' ', normalized).strip()

    def normalize_for_rules(self, text: str) -> str:
        normalized = self.normalize_whitespace(text).lower()
        normalized = unicodedata.normalize('NFKD', normalized)
        ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
        return WHITESPACE_PATTERN.sub(' ', ascii_text).strip()

    def preprocess_for_model(self, text: str) -> str:
        normalized = self.normalize_whitespace(text)
        if not normalized:
            return ''
        if word_tokenize is None:
            return normalized
        return self.normalize_whitespace(word_tokenize(normalized, format='text'))

    def is_effectively_empty(self, text: str) -> bool:
        if not text or not text.strip():
            return True
        without_urls = URL_PATTERN.sub(' ', text)
        without_symbols = re.sub(r'[\W_]+', '', without_urls, flags=re.UNICODE)
        return not without_symbols.strip()

    def should_override_to_emergency(self, text: str, prob_cau_cuu: float) -> bool:
        lowered = self.normalize_for_rules(text)
        if any(token in lowered for token in SAFE_HINTS):
            return False

        has_rescue = any(token in lowered for token in RESCUE_TERMS)
        has_trap = any(token in lowered for token in TRAP_TERMS)
        has_flood = any(token in lowered for token in FLOOD_TERMS)
        has_request = any(token in lowered for token in REQUEST_TERMS)
        has_vulnerable = any(token in lowered for token in VULNERABLE_TERMS)
        has_phone = bool(PHONE_PATTERN.search(lowered))

        strong_pattern = (
            has_request
            or (has_rescue and has_trap)
            or (has_rescue and has_flood)
            or (has_trap and has_flood)
            or (has_phone and (has_rescue or has_flood or has_trap))
            or (has_vulnerable and (has_rescue or has_flood or has_trap))
        )
        return strong_pattern and prob_cau_cuu >= 0.20

    def _predict_probabilities(self, texts: list[str], batch_size: int) -> list[float]:
        dataset = BatchCommentDataset(texts, self.tokenizer, self.max_length)
        collator = DataCollatorWithPadding(
            tokenizer=self.tokenizer,
            pad_to_multiple_of=8 if self.device.type == 'cuda' else None,
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=False, collate_fn=collator)

        probabilities: list[float] = []
        processed = 0
        with self._predict_lock, torch.no_grad():
            for batch in loader:
                batch = {key: value.to(self.device) for key, value in batch.items()}
                logits = self.model(**batch).logits
                probs = torch.softmax(logits, dim=-1)[:, 1].detach().cpu().tolist()
                probabilities.extend(float(value) for value in probs)
                processed += len(probs)
                if processed % 100 == 0 or processed == len(texts):
                    logger.info('Classifier processed %s/%s inferable comments', processed, len(texts))
        return probabilities

    def predict_batch(self, texts: list[str], batch_size: int = 32) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        prepared_texts: list[str] = []
        prepared_indices: list[int] = []

        for index, text in enumerate(texts):
            if self.is_effectively_empty(text):
                results.append({'label': 'khong_cau_cuu', 'confidence': 0.0, 'is_sos': False})
                continue

            prepared = self.preprocess_for_model(text)
            if not prepared:
                results.append({'label': 'khong_cau_cuu', 'confidence': 0.0, 'is_sos': False})
                continue

            results.append({'label': 'khong_cau_cuu', 'confidence': 0.0, 'is_sos': False})
            prepared_indices.append(index)
            prepared_texts.append(prepared)

        if prepared_texts:
            probabilities = self._predict_probabilities(prepared_texts, batch_size=batch_size)
            for result_index, prob_cau_cuu in zip(prepared_indices, probabilities):
                original_text = texts[result_index]
                is_sos = prob_cau_cuu >= self.threshold or self.should_override_to_emergency(original_text, prob_cau_cuu)
                label = 'cau_cuu' if is_sos else 'khong_cau_cuu'
                confidence = prob_cau_cuu if is_sos else 1.0 - prob_cau_cuu
                results[result_index] = {
                    'label': label,
                    'confidence': round(float(confidence), 4),
                    'is_sos': bool(is_sos),
                }

        return results


@lru_cache(maxsize=1)
def get_classifier_service() -> ClassifierService:
    settings = get_settings()
    return ClassifierService(
        model_id=settings.HF_MODEL_ID,
        threshold=settings.CLASSIFIER_THRESHOLD,
        device=settings.CLASSIFIER_DEVICE,
    )