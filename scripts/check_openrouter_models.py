import os

import requests
from dotenv import load_dotenv

load_dotenv()

resp = requests.get(
    'https://openrouter.ai/api/v1/models',
    headers={'Authorization': f"Bearer {os.getenv('OPENROUTER_API_KEY')}"},
    timeout=30,
)
resp.raise_for_status()
models = resp.json()['data']

free_models = [
    m for m in models
    if str(m.get('pricing', {}).get('prompt', '1')) == '0'
    and 'text' in str(m.get('architecture', {}).get('modality', ''))
]

print(f"Tìm thấy {len(free_models)} free text models:\n")
for m in sorted(free_models, key=lambda x: x['id']):
    ctx = m.get('context_length', 0)
    print(f"  {m['id']}  (ctx: {ctx})")