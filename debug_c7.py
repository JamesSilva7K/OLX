"""Debug: verifica quais credenciais C7 estão sendo usadas e faz uma chamada real."""
import os, sys, json, requests
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from app import _get_live_c7_keys, get_c7_auth_headers

keys = _get_live_c7_keys()
print("=== CHAVES CARREGADAS ===")
print(f"api_key    : {keys.get('api_key','')[:35]}..." if keys.get('api_key') else "api_key    : !! VAZIA !!")
print(f"api_secret : {keys.get('api_secret','')[:15]}..." if keys.get('api_secret') else "api_secret : !! VAZIA !!")
print(f"base_url   : {keys.get('base_url')}")

print("\n=== TESTE REAL - POST /account/balance ===")
body = "{}"
hdrs = get_c7_auth_headers(body)
print("Headers enviados:")
for k, v in hdrs.items():
    print(f"  {k}: {v[:60] if len(v) > 60 else v}")

base_url = keys.get("base_url", "https://api.carteirado7.com/v2")
try:
    res = requests.post(f"{base_url}/account/balance", data=body, headers=hdrs, timeout=10)
    print(f"\nStatus: {res.status_code}")
    print(f"Resposta: {res.text[:500]}")
except Exception as e:
    print(f"\nErro de conexao: {e}")
