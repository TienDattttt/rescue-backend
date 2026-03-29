import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

payload = {
    'model': 'nvidia/nemotron-3-super-120b-a12b:free',
    'max_tokens': 500,
    'messages': [
        {
            'role': 'system',
            'content': 'Trả về JSON array. Không giải thích.',
        },
        {
            'role': 'user',
            'content': '''Phân tích 1 bình luận. Trả về JSON array 1 object.

[1] Nhà tôi bị ngập, có người già. SĐT 0901234567

Trả về:
[{"locationDescription": "...", "numPeople": null, "vulnerableGroups": [], "waitingHours": null, "severity": "HIGH", "accessibility": "MODERATE", "phone": "0901234567", "lat": null, "lng": null}]''',
        },
    ],
}

resp = requests.post(
    'https://openrouter.ai/api/v1/chat/completions',
    headers={
        'Authorization': f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        'Content-Type': 'application/json',
    },
    json=payload,
    timeout=60,
)

print(f'Status: {resp.status_code}')
print(f'Response:\n{json.dumps(resp.json(), indent=2, ensure_ascii=False)}')