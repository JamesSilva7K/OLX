"""
OLPG API INTELLIGENCE & DOCUMENTATION ENGINE v2.0
Advanced Neural-Pattern Documentation Parser & Gateway Auto-Configurator.
Recognizes: ElitePay, C7, MercadoPago, Stripe, PagSeguro, EfiPay, Pix Manual,
plus universal cURL, OpenAPI/Swagger and Freeform Technical Docs with Real-Time Connectivity Testing.
"""
import re, json, time, urllib.parse
from typing import Dict, List, Any, Optional, Tuple

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# ─── GATEWAY INSTRUCTION KNOWLEDGE BASE ──────────────────────────────────────
GATEWAY_INTELLIGENCE: Dict[str, Dict] = {
    "elitepay": {
        "name": "ElitePay",
        "logo": "EP",
        "color": "#10B981",
        "doc_keywords": [
            "elitepay", "elite pay", "elitepaybr", "api.elitepaybr.com",
            "x-client-id", "x-client-secret", "ci:", "cs:", "bep20", "usdt"
        ],
        "detection_patterns": [
            r"api\.elitepaybr\.com",
            r"x-client-id",
            r"x-client-secret",
            r"elitepay(br)?",
            r"X-Elite-Signature",
            r"X-Elite-Timestamp",
        ],
        "field_extractors": {
            "client_id":     r"(?:x-client-id|ci)[\"':\s=]+([A-Za-z0-9_\-\.]{6,})",
            "client_secret": r"(?:x-client-secret|cs)[\"':\s=]+([A-Za-z0-9_\-\.]{6,})",
            "base_url":      r"(https?://api\.elitepaybr\.com[^\s\"']*)",
        },
        "field_validators": {
            "client_id":     r"^[A-Za-z0-9_\-\.]{6,}$",
            "client_secret": r"^[A-Za-z0-9_\-\.]{6,}$",
        },
        "endpoints": {
            "balance":        "/api/v1/balance",
            "deposit":        "/api/v1/deposit",
            "withdraw_pix":   "/api/v1/withdraw",
            "crypto_quote":   "/api/v1/crypto/quote",
            "crypto_withdraw": "/api/v1/crypto/withdraw",
            "check_status":   "/api/transactions/check",
            "webhook":        "/api/webhook/elitepay",
        },
        "auth_headers": {
            "id_header":     "x-client-id",
            "secret_header": "x-client-secret",
        },
        "setup_instructions": [
            "1. Acesse o painel ElitePay em https://api.elitepaybr.com na aba Credenciais",
            "2. Copie seu Client ID (x-client-id) e Client Secret (x-client-secret)",
            "3. A Base URL oficial e https://api.elitepaybr.com",
            "4. Deposito Pix: POST /api/v1/deposit (gera QR Code e Copia e Cola instantaneo)",
            "5. Saques: Suporta Saque Pix (/api/v1/withdraw) e Saque Crypto USDT BEP20 (/api/v1/crypto/withdraw)",
            "6. Webhook: Notificacoes com assinatura segura HMAC-SHA256 em /api/webhook/elitepay",
        ],
        "warnings": {
            "missing_secret": "Client Secret nao encontrado — necessario para autenticar chamadas de deposito e saques.",
        }
    },
    "c7": {
        "name": "Carteira do 7 (C7)",
        "logo": "C7",
        "color": "#7C3AED",
        "doc_keywords": ["carteirado7", "carteira do 7", "c7_live_", "c7_test_", "api.carteirado7.com", "acquirer_code"],
        "detection_patterns": [
            r"c7_(live|test)_[a-f0-9]{40,}",
            r"api\.carteirado7\.com",
            r"X-C7-Signature",
            r"X-C7-Timestamp",
            r"X-C7-Nonce",
        ],
        "field_extractors": {
            "api_key":        r"(c7_(live|test)_[a-f0-9]{48,})",
            "api_secret":     r"(?:secret|api_secret)[\"'\s:=]+([a-f0-9]{60,})",
            "internal_token": r"(?:internal.token|bearer.token)[\"'\s:=]+([A-Za-z0-9]{25,45})",
            "base_url":       r"(https://api\.carteirado7\.com[/\w]*)",
            "acquirer_code":  r"(?:acquirer.code|acquirer_code)[\"'\s:=]+([A-Za-z0-9]{3,20})",
        },
        "field_validators": {
            "api_key":    r"^c7_(live|test)_[a-f0-9]{48,}$",
            "api_secret": r"^[a-f0-9]{60,}$",
        },
        "setup_instructions": [
            "1. Acesse o painel C7 em carteirado7.com e va em Configuracoes > API",
            "2. Copie a API Key (c7_live_...) e o API Secret (hex longo)",
            "3. O Token Interno e o Bearer Token do seu painel",
            "4. A Base URL padrao e https://api.carteirado7.com/v2",
        ],
        "warnings": {
            "test_mode": "c7_test_ detectado — estas credenciais sao de SANDBOX, nao processam pagamentos reais.",
            "missing_secret": "API Secret nao encontrado — necessario para assinar requisicoes HMAC-SHA256.",
        }
    },
    "mercadopago": {
        "name": "Mercado Pago",
        "logo": "MP",
        "color": "#009EE3",
        "doc_keywords": ["mercadopago", "mercado pago", "APP_USR", "mp.com.br", "sdk.mercadopago"],
        "detection_patterns": [
            r"(APP_USR|TEST)-[0-9]{10,}-[a-zA-Z0-9\-]+",
            r"mercadopago\.com",
            r"api\.mercadopago\.com",
        ],
        "field_extractors": {
            "access_token": r"((APP_USR|TEST)-[0-9]{10,}-[a-zA-Z0-9\-_]{20,})",
            "public_key":   r"((APP_USR|TEST)-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
        },
        "field_validators": {
            "access_token": r"^(APP_USR|TEST)-[0-9]+-[A-Za-z0-9\-_]+$",
            "public_key":   r"^(APP_USR|TEST)-[a-f0-9\-]{30,}$",
        },
        "setup_instructions": [
            "1. Acesse mercadopago.com.br/developers e crie uma aplicacao",
            "2. Em Credenciais > Producao, copie o Access Token (APP_USR-...)",
        ],
        "warnings": {
            "test_mode": "TEST- detectado — modo sandbox ativo. Troque por APP_USR- para producao.",
        }
    },
    "stripe": {
        "name": "Stripe",
        "logo": "ST",
        "color": "#635BFF",
        "doc_keywords": ["stripe", "sk_live_", "sk_test_", "pk_live_", "stripe.com", "whsec_"],
        "detection_patterns": [
            r"(sk|pk)_(live|test)_[A-Za-z0-9]{24,}",
            r"stripe\.com",
            r"api\.stripe\.com",
            r"whsec_[A-Za-z0-9]{24,}",
        ],
        "field_extractors": {
            "secret_key":       r"(sk_(live|test)_[A-Za-z0-9]{24,})",
            "publishable_key":  r"(pk_(live|test)_[A-Za-z0-9]{24,})",
            "webhook_secret":   r"(whsec_[A-Za-z0-9]{24,})",
        },
        "field_validators": {
            "secret_key":      r"^sk_(live|test)_[A-Za-z0-9]{24,}$",
            "publishable_key": r"^pk_(live|test)_[A-Za-z0-9]{24,}$",
            "webhook_secret":  r"^whsec_[A-Za-z0-9]{24,}$",
        },
        "setup_instructions": [
            "1. Acesse dashboard.stripe.com > Developers > API Keys",
            "2. Copie a Secret Key (sk_live_...)",
        ],
        "warnings": {
            "test_mode": "sk_test_ ou pk_test_ detectado — modo de testes. Use sk_live_ para producao.",
        }
    },
    "pagseguro": {
        "name": "PagSeguro",
        "logo": "PS",
        "color": "#00B272",
        "doc_keywords": ["pagseguro", "pagbank", "uol", "pagseguro.uol.com.br"],
        "detection_patterns": [
            r"pagseguro\.uol\.com\.br",
            r"sandbox\.pagseguro",
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{32}",
        ],
        "field_extractors": {
            "token": r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{32})",
            "email": r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
        },
        "field_validators": {
            "token": r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{32}$",
            "email": r"^[^@]+@[^@]+\.[^@]+$",
        },
        "setup_instructions": [
            "1. Acesse pagseguro.uol.com.br > Preferencias > Integracoes",
            "2. Gere um Token de seguranca para sua conta",
        ],
        "warnings": {
            "test_mode": "sandbox detectado — use o token de producao.",
        }
    },
    "efipay": {
        "name": "Efi Pay (Gerencianet)",
        "logo": "EFI",
        "color": "#1A5EFF",
        "doc_keywords": ["efipay", "gerencianet", "efi", "client_id", "client_secret", "pix.api.efipay.com.br"],
        "detection_patterns": [
            r"Client_Id_[A-Za-z0-9]{20,}",
            r"Client_Secret_[A-Za-z0-9]{20,}",
            r"efipay\.com\.br",
            r"pix\.api\.efipay",
        ],
        "field_extractors": {
            "client_id":     r"(Client_Id_[A-Za-z0-9]{20,})",
            "client_secret": r"(Client_Secret_[A-Za-z0-9]{20,})",
            "pix_key":       r"(?:chavePix|chave_pix|pix_key)[\"'\s:=]+([^\s\"']+)",
        },
        "field_validators": {
            "client_id":     r"^Client_Id_[A-Za-z0-9]{20,}$",
            "client_secret": r"^Client_Secret_[A-Za-z0-9]{20,}$",
        },
        "setup_instructions": [
            "1. Acesse efipay.com.br > Minha Conta > API",
            "2. Crie uma aplicacao e copie Client_Id e Client_Secret",
        ],
        "warnings": {
            "sandbox": "sandbox ativo — desative para processar pagamentos reais.",
        }
    },
    "pix_manual": {
        "name": "Pix Manual (Chave Direta)",
        "logo": "PIX",
        "color": "#32BCAD",
        "doc_keywords": ["chave pix", "pix", "bacen", "qrcode", "chave aleatoria"],
        "detection_patterns": [
            r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
            r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
            r"\+55\s?\(?\d{2}\)?\s?\d{4,5}-?\d{4}",
            r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}",
        ],
        "field_extractors": {
            "pix_key":  r"([a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\+55[\s\d\(\)\-]{10,14}|[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
            "pix_name": r"(?:nome|name|recebedor)[\"'\s:=]+([A-Za-z\s]{3,50})",
            "pix_city": r"(?:cidade|city)[\"'\s:=]+([A-Za-z\s]{2,30})",
        },
        "field_validators": {},
        "setup_instructions": [
            "1. Use qualquer chave Pix cadastrada no seu banco: CPF, CNPJ, e-mail, telefone ou chave aleatoria",
            "2. O QR Code sera gerado com padrao oficial BACEN BR Code 2.0 (EMV com CRC-16)",
        ],
        "warnings": {}
    },
    "custom": {
        "name": "API Personalizada",
        "logo": "API",
        "color": "#6B7280",
        "doc_keywords": [],
        "detection_patterns": [],
        "field_extractors": {
            "api_key":  r"(?:api[_-]?key|token|bearer|authorization)[\"'\s:=]+([A-Za-z0-9_\-\.]{16,})",
            "base_url": r"(https?://[^\s\"']+)",
        },
        "field_validators": {},
        "setup_instructions": [
            "1. Cole a documentacao tecnica ou o comando cURL no campo acima para deteccao automatica",
            "2. O sistema reconhece endpoints, headers de autenticacao e formato do payload",
        ],
        "warnings": {}
    }
}


# ─── DEEP PARSERS: CURL, OPENAPI, TECHNICAL DOCS ─────────────────────────────

def parse_curl_command(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Parses a cURL snippet and extracts method, full URL, base URL, endpoint path,
    all request headers (with special attention to auth headers), and body JSON.
    """
    if "curl" not in raw_text.lower():
        return None

    # Normaliza quebras de linha com barra invertida
    clean = re.sub(r"\\\s*\n", " ", raw_text)

    # 1. Metodo HTTP
    method_match = re.search(r"(?:-X|--request)\s+([A-Z]{3,7})", clean)
    method = method_match.group(1) if method_match else ("POST" if ("-d" in clean or "--data" in clean) else "GET")

    # 2. URL
    url_match = re.search(r"['\"]?(https?://[^\s'\"]+)['\"]?", clean)
    if not url_match:
        return None
    full_url = url_match.group(1).rstrip("'\"")
    parsed_url = urllib.parse.urlparse(full_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    endpoint_path = parsed_url.path or "/"

    # 3. Headers
    header_matches = re.findall(r"(?:-H|--header)\s+['\"]([^'\"]+)['\"]", clean)
    headers = {}
    auth_headers = {}
    for h in header_matches:
        if ":" in h:
            k, v = h.split(":", 1)
            k = k.strip()
            v = v.strip()
            headers[k] = v
            k_lower = k.lower()
            if any(term in k_lower for term in ["auth", "token", "key", "secret", "client", "ci", "cs"]):
                auth_headers[k] = v

    # 4. Body Data
    body_raw = None
    data_match = re.search(r"(?:-d|--data|--data-raw)\s+['\"](\{.*?\})['\"]", clean, re.DOTALL)
    if data_match:
        body_raw = data_match.group(1)
    body_json = None
    if body_raw:
        try:
            body_json = json.loads(body_raw)
        except Exception:
            pass

    return {
        "is_curl": True,
        "method": method,
        "full_url": full_url,
        "base_url": base_url,
        "endpoint": endpoint_path,
        "headers": headers,
        "auth_headers": auth_headers,
        "body_json": body_json,
    }


def parse_openapi_spec(raw_text: str) -> Optional[Dict[str, Any]]:
    """Tenta parsear OpenAPI / Swagger / Postman JSON e extrair servidores e rotas."""
    try:
        data = json.loads(raw_text)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    # Verifica se parece OpenAPI / Swagger
    is_openapi = "openapi" in data or "swagger" in data or "paths" in data
    if not is_openapi:
        return None

    servers = data.get("servers", [])
    base_url = servers[0].get("url") if servers and isinstance(servers[0], dict) else ""
    if not base_url and "host" in data:
        schemes = data.get("schemes", ["https"])
        base_url = f"{schemes[0]}://{data['host']}"

    paths = data.get("paths", {})
    detected_endpoints = {}
    for p, methods in paths.items():
        p_lower = p.lower()
        if any(term in p_lower for term in ["deposit", "pix", "charge", "payment"]):
            detected_endpoints["deposit"] = p
        elif any(term in p_lower for term in ["withdraw", "saque", "transfer"]):
            detected_endpoints["withdraw"] = p
        elif any(term in p_lower for term in ["balance", "saldo"]):
            detected_endpoints["balance"] = p
        elif any(term in p_lower for term in ["check", "status", "verify"]):
            detected_endpoints["check"] = p

    # Auth
    sec_defs = data.get("components", {}).get("securitySchemes", {}) or data.get("securityDefinitions", {})
    auth_type = "bearer"
    auth_header = "Authorization"
    for name, s in sec_defs.items():
        if s.get("type") == "apiKey":
            auth_header = s.get("name", "x-api-key")
            auth_type = "api_key"

    return {
        "is_openapi": True,
        "title": data.get("info", {}).get("title", "API Detectada"),
        "base_url": base_url,
        "endpoints": detected_endpoints,
        "auth_header": auth_header,
        "auth_type": auth_type,
    }


def parse_technical_doc(text: str) -> Dict[str, Any]:
    """
    Parser semantico inteligente para documentacoes tecnicas e manuais em texto livre.
    Extrai: URLs de API, endpoints de Pix/Deposito/Saque, cabeçalhos de autenticação e tokens.
    """
    result = {
        "base_urls": [],
        "endpoints": {},
        "auth_headers": {},
        "tokens": {},
        "has_pix_deposit": False,
        "has_pix_withdraw": False,
        "has_crypto": False,
        "has_webhook_hmac": False,
        "detected_service_name": "",
    }

    # 1. Base URLs
    url_matches = re.findall(r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?::\d+)?", text)
    filtered_urls = [u for u in url_matches if not any(ign in u.lower() for ign in ["google", "github", "render", "microsoft", "cloudflare", "schema.org", "w3.org"])]
    result["base_urls"] = list(dict.fromkeys(filtered_urls))

    # 2. Endpoints
    endpoint_matches = re.findall(r"(?:POST|GET|PUT|DELETE)\s+([/a-zA-Z0-9_\-\.]+)", text)
    endpoint_matches += re.findall(r"['\"](/api/[a-zA-Z0-9_\-\./]+)['\"]", text)
    endpoint_matches += re.findall(r"['\"](/v1/[a-zA-Z0-9_\-\./]+)['\"]", text)

    for ep in set(endpoint_matches):
        ep_lower = ep.lower()
        if any(term in ep_lower for term in ["deposit", "deposito", "pix/create", "create-pix", "charge"]):
            result["endpoints"]["deposit"] = ep
            result["has_pix_deposit"] = True
        elif any(term in ep_lower for term in ["withdraw", "saque"]):
            result["endpoints"]["withdraw"] = ep
            result["has_pix_withdraw"] = True
        elif any(term in ep_lower for term in ["balance", "saldo"]):
            result["endpoints"]["balance"] = ep
        elif any(term in ep_lower for term in ["check", "status", "transaction"]):
            result["endpoints"]["check_status"] = ep
        elif any(term in ep_lower for term in ["crypto", "usdt", "bep20"]):
            result["has_crypto"] = True

    # 3. Auth Headers
    header_patterns = [
        (r"(x-client-id)[\"':\s=]+([^\s\"']+)", "x-client-id"),
        (r"(x-client-secret)[\"':\s=]+([^\s\"']+)", "x-client-secret"),
        (r"(x-api-key)[\"':\s=]+([^\s\"']+)", "x-api-key"),
        (r"(Authorization)[\"':\s=]+(Bearer\s+[^\s\"']+)", "Authorization"),
        (r"(ci)[\"':\s=]+([^\s\"']+)", "x-client-id"),
        (r"(cs)[\"':\s=]+([^\s\"']+)", "x-client-secret"),
    ]
    for pat, h_name in header_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(2).strip().strip("'\"")
            result["auth_headers"][h_name] = val
            result["tokens"][h_name] = val

    # 4. Webhook HMAC
    if any(k in text.lower() for k in ["x-elite-signature", "x-c7-signature", "hmac", "sha256", "timingsafeequal"]):
        result["has_webhook_hmac"] = True

    # 5. Service name
    if "elitepay" in text.lower() or "elite pay" in text.lower() or "api.elitepaybr.com" in text.lower():
        result["detected_service_name"] = "ElitePay"
    elif "carteirado7" in text.lower() or "c7" in text.lower():
        result["detected_service_name"] = "Carteira do 7"
    elif "mercadopago" in text.lower():
        result["detected_service_name"] = "Mercado Pago"

    return result


def test_gateway_connectivity(base_url: str, headers: Dict[str, str] = None, endpoint: str = "") -> Dict[str, Any]:
    """
    Executes a real-time HTTP connectivity test with precise millisecond latency measurement,
    SSL handshake verification, and intelligent response parsing.
    """
    if not _REQUESTS_OK:
        return {"ok": False, "error": "Modulo requests nao disponivel para testes de conexao."}

    base = base_url.strip().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = "https://" + base

    test_path = endpoint.strip() if endpoint else ""
    if test_path and not test_path.startswith("/"):
        test_path = "/" + test_path

    target_url = f"{base}{test_path}" if test_path else base
    req_headers = {
        "User-Agent": "OLPG-Gateway-Intelligence-Validator/2026",
        "Accept": "application/json, text/plain, */*"
    }
    if headers:
        for k, v in headers.items():
            if v and str(v).strip():
                req_headers[k] = str(v).strip()

    t_start = time.perf_counter()
    try:
        # Tenta GET com timeout de 8 segundos
        resp = requests.get(target_url, headers=req_headers, timeout=8, verify=True)
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        status_code = resp.status_code
        ssl_valid = True
        body_text = resp.text[:400]

        # Avaliação de estabilidade
        stability = "ALTA" if latency_ms < 350 else ("MEDIA" if latency_ms < 800 else "BAIXA")

        # Mensagem contextual
        if status_code in (200, 201):
            msg = f"Conexao estabelecida com sucesso! API online e respondendo ({latency_ms}ms)."
            ok = True
        elif status_code in (401, 403):
            msg = f"Servidor online ({latency_ms}ms), porem requer credenciais validas (HTTP {status_code})."
            ok = True  # O servidor está online
        elif status_code == 404:
            msg = f"Servidor online ({latency_ms}ms), mas o endpoint especifico retornou 404. Verifique a rota."
            ok = True
        elif status_code == 429:
            msg = f"Rate limited pela API (HTTP 429). Aguarde alguns instantes."
            ok = False
        else:
            msg = f"Servidor respondeu com codigo HTTP {status_code} em {latency_ms}ms."
            ok = status_code < 500

        return {
            "ok": ok,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "stability": stability,
            "ssl_valid": ssl_valid,
            "target_url": target_url,
            "message": msg,
            "body_preview": body_text,
        }

    except requests.exceptions.SSLError as ssl_err:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        return {
            "ok": False,
            "status_code": 0,
            "latency_ms": latency_ms,
            "stability": "INSEGURO",
            "ssl_valid": False,
            "target_url": target_url,
            "message": f"Falha no certificado SSL: {ssl_err}",
            "body_preview": "",
        }
    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "status_code": 408,
            "latency_ms": 8000,
            "stability": "TIMEOUT",
            "ssl_valid": True,
            "target_url": target_url,
            "message": "Tempo limite de resposta esgotado (timeout > 8s). O servidor da API pode estar instavel.",
            "body_preview": "",
        }
    except Exception as e:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        return {
            "ok": False,
            "status_code": 0,
            "latency_ms": latency_ms,
            "stability": "OFFLINE",
            "ssl_valid": False,
            "target_url": target_url,
            "message": f"Erro de conexao: {str(e)}",
            "body_preview": "",
        }


# ─── API INTELLIGENCE ENGINE ─────────────────────────────────────────────────

class APIIntelligenceEngine:
    """
    Multi-layer API credential and documentation intelligence engine.
    Processes:
      - Raw API keys and tokens
      - Multi-line cURL snippets
      - OpenAPI / Swagger JSON specifications
      - Freeform technical documentation / manual text
    Outputs structured gateway detection, field extraction, validation,
    readymade schemas for instant 1-click activation, and instructions.
    """

    def analyze(self, raw_text: str) -> Dict[str, Any]:
        text = self._normalize(raw_text)
        if len(text) < 5:
            return {"ok": False, "error": "Texto muito curto para analise."}

        # 1. Analise de cURL
        curl_spec = parse_curl_command(raw_text)

        # 2. Analise de OpenAPI
        openapi_spec = parse_openapi_spec(raw_text)

        # 3. Analise de Documentacao Tecnica Livre
        doc_spec = parse_technical_doc(raw_text)

        # 4. Pontuacao de gateways conhecidos
        scores = self._score_gateways(text)

        # Bonus para ElitePay se a doc ou cURL referenciar elitepaybr
        if "elitepaybr" in text.lower() or "api.elitepaybr.com" in text.lower() or "x-client-id" in text.lower():
            scores["elitepay"] = max(scores.get("elitepay", 0.0), 0.98)

        best_gw, confidence = max(scores.items(), key=lambda x: x[1]) if scores else ("custom", 0.1)
        if confidence < 0.05:
            best_gw = "custom"
            confidence = 0.20

        # Extração de campos
        fields = self._extract_fields(text, best_gw)

        # Preenche com dados do cURL ou doc se disponiveis
        if curl_spec:
            if "client_id" in fields or best_gw == "elitepay":
                cid = curl_spec["headers"].get("x-client-id") or curl_spec["headers"].get("ci")
                cs = curl_spec["headers"].get("x-client-secret") or curl_spec["headers"].get("cs")
                if cid: fields["client_id"] = cid
                if cs: fields["client_secret"] = cs
            if not fields.get("base_url") and curl_spec.get("base_url"):
                fields["base_url"] = curl_spec["base_url"]

        if doc_spec:
            if not fields.get("client_id") and doc_spec["tokens"].get("x-client-id"):
                fields["client_id"] = doc_spec["tokens"]["x-client-id"]
            if not fields.get("client_secret") and doc_spec["tokens"].get("x-client-secret"):
                fields["client_secret"] = doc_spec["tokens"]["x-client-secret"]
            if not fields.get("base_url") and doc_spec["base_urls"]:
                fields["base_url"] = doc_spec["base_urls"][0]

        validated = self._validate_fields(fields, best_gw)
        issues = self._check_issues(text, best_gw, fields)
        instructions = GATEWAY_INTELLIGENCE.get(best_gw, {}).get("setup_instructions", [])
        meta = {k: GATEWAY_INTELLIGENCE.get(best_gw, {}).get(k) for k in ("name", "logo", "color")}

        # Geracao de schema customizado pronto para ativacao
        ready_schema = {
            "gw_id": best_gw if best_gw != "custom" else f"gw_{int(time.time())}",
            "name": meta.get("name") or doc_spec.get("detected_service_name") or "Gateway Personalizado",
            "logo": meta.get("logo") or "API",
            "color": meta.get("color") or "#10B981",
            "base_url": fields.get("base_url") or (curl_spec.get("base_url") if curl_spec else ""),
            "endpoints": doc_spec.get("endpoints") or (GATEWAY_INTELLIGENCE.get(best_gw, {}).get("endpoints") or {}),
            "auth": {
                "headers": list(doc_spec.get("auth_headers", {}).keys()),
            },
            "fields": [
                {"key": k, "label": k.replace("_", " ").title(), "hint": v[:30] if v else ""}
                for k, v in fields.items()
            ]
        }

        # Runner-up detection
        runners = sorted(
            [(gw, s) for gw, s in scores.items() if gw != best_gw and s > 0.1],
            key=lambda x: x[1], reverse=True
        )[:2]

        return {
            "ok": True,
            "gateway": best_gw,
            "confidence": round(confidence, 2),
            "confidence_pct": f"{round(confidence*100)}%",
            "meta": meta,
            "fields": fields,
            "validated_fields": validated,
            "issues": issues,
            "instructions": instructions,
            "curl_detected": bool(curl_spec),
            "curl_spec": curl_spec,
            "openapi_detected": bool(openapi_spec),
            "doc_spec": doc_spec,
            "ready_schema": ready_schema,
            "runner_up": [{"gateway": gw, "confidence": round(s, 2)} for gw, s in runners],
            "field_count": len([v for v in fields.values() if v]),
            "all_valid": all(v for v in validated.values()) if validated else True,
        }

    def _normalize(self, text: str) -> str:
        text = text.replace("\x00", "").replace("\r\n", "\n")
        return text[:32768]

    def _score_gateways(self, text: str) -> Dict[str, float]:
        text_lower = text.lower()
        scores = {}
        for gw_id, gw in GATEWAY_INTELLIGENCE.items():
            score = 0.0
            for kw in gw.get("doc_keywords", []):
                if kw.lower() in text_lower:
                    score += 0.20
            for pat in gw.get("detection_patterns", []):
                try:
                    if re.search(pat, text, re.IGNORECASE):
                        score += 0.40
                except re.error:
                    pass
            extracted = self._extract_fields(text, gw_id)
            score += 0.15 * len([v for v in extracted.values() if v])
            scores[gw_id] = min(score, 1.0)
        return scores

    def _extract_fields(self, text: str, gateway: str) -> Dict[str, str]:
        gw = GATEWAY_INTELLIGENCE.get(gateway, {})
        extractors = gw.get("field_extractors", {})
        result = {}
        for field_key, pattern in extractors.items():
            try:
                m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if m:
                    result[field_key] = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
            except re.error:
                pass
        return result

    def _validate_fields(self, fields: Dict[str, str], gateway: str) -> Dict[str, bool]:
        gw = GATEWAY_INTELLIGENCE.get(gateway, {})
        validators = gw.get("field_validators", {})
        result = {}
        for field_key, value in fields.items():
            if field_key in validators and value:
                try:
                    result[field_key] = bool(re.match(validators[field_key], value.strip()))
                except re.error:
                    result[field_key] = True
        return result

    def _check_issues(self, text: str, gateway: str, fields: Dict[str, str]) -> List[str]:
        issues = []
        text_lower = text.lower()
        gw = GATEWAY_INTELLIGENCE.get(gateway, {})
        warnings = gw.get("warnings", {})

        if any(k in text_lower for k in ["test_", "sk_test", "pk_test", "sandbox"]):
            w = warnings.get("test_mode", "Modo de testes detectado — use credenciais de producao.")
            issues.append(f"ATENCAO: {w}")

        required_by_gw = {
            "elitepay":    ["client_id", "client_secret"],
            "c7":          ["api_key", "api_secret"],
            "mercadopago": ["access_token"],
            "stripe":      ["secret_key"],
            "pagseguro":   ["token", "email"],
            "efipay":      ["client_id", "client_secret"],
            "pix_manual":  ["pix_key"],
        }
        for req in required_by_gw.get(gateway, []):
            if not fields.get(req):
                issues.append(f"Campo obrigatorio nao encontrado: '{req}'")

        return issues


# Instância global
_engine = APIIntelligenceEngine()

def analyze_api_text(raw_text: str) -> Dict[str, Any]:
    return _engine.analyze(raw_text)

def test_connectivity(base_url: str, headers: Dict[str, str] = None, endpoint: str = "") -> Dict[str, Any]:
    return test_gateway_connectivity(base_url, headers, endpoint)

def get_gateway_schema(gateway_id: str) -> Dict:
    return GATEWAY_INTELLIGENCE.get(gateway_id, GATEWAY_INTELLIGENCE["custom"])

def list_supported_gateways() -> List[Dict]:
    return [
        {
            "id": gw_id,
            "name": gw.get("name", gw_id),
            "logo": gw.get("logo", "?"),
            "color": gw.get("color", "#888"),
            "field_count": len(gw.get("field_extractors", {})),
        }
        for gw_id, gw in GATEWAY_INTELLIGENCE.items()
    ]
