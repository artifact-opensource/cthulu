"""
Check whether an LLM endpoint is configured and reachable.
"""
import os
import json
import requests

endpoint = os.environ.get('LLM_ENDPOINT')
key = os.environ.get('LLM_API_KEY')

out = {'configured': bool(endpoint), 'reachable': False, 'error': None}
if not endpoint:
    print(json.dumps(out))
    raise SystemExit(0)

try:
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    resp = requests.post(endpoint, json={'prompt': 'ping'}, headers=headers, timeout=5)
    resp.raise_for_status()
    out['reachable'] = True
except Exception as e:
    out['error'] = str(e)

print(json.dumps(out, indent=2))
