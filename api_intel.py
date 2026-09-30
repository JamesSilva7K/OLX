"""
OLPG API INTELLIGENCE ENGINE v1.0
Reads raw API docs / credentials text and auto-configures payment gateways.
Supports: C7, MercadoPago, Stripe, PagSeguro, EfiPay, Pix Manual, Custom
"""
import re
from typing import Dict, List, Any, Optional, Tuple

# ─── GATEWAY INSTRUCTION KNOWLEDGE BASE ──────────────────────────────────────
# Each gateway has: detection patterns, field extractors, validation rules,
# setup instructions that guide the admin after detection.
GATEWAY_INTELLIGENCE: Dict[str, Dict] = {
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
            "api_key":   r"^c7_(live|test)_[a-f0-9]{48,}$",
            "api_secret": r"^[a-f0-9]{60,}$",
        },
        "setup_instructions": [
            "1. Acesse o painel C7 em carteirado7.com e va em Configuracoes > API",
            "2. Copie a API Key (c7_live_...) e o API Secret (hex longo)",
            "3. O Token Interno e o Bearer Token do seu painel",
            "4. A Base URL padrao e https://api.carteirado7.com/v2",
            "5. O Codigo Adquirente e opcional — use apenas se solicitado",
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
            "3. A Public Key e usada no frontend para tokenizar cartoes",
            "4. Nunca use credenciais TEST em producao",
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
            "2. Copie a Secret Key (sk_live_...) — nunca exponha no frontend",
            "3. A Publishable Key (pk_live_...) e segura para usar no cliente",
            "4. Para webhooks, crie um endpoint e copie o Signing Secret (whsec_...)",
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
            "3. O E-mail e o mesmo do seu login PagSeguro",
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
            "3. Em Pix > Minhas chaves, adicione sua chave Pix",
            "4. Para sandbox, use sandbox=true nas configuracoes",
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
            r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",           # CPF formatado
            r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",     # CNPJ
            r"\+55\s?\(?\d{2}\)?\s?\d{4,5}-?\d{4}",     # telefone
            r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}",  # UUID v4 aleatoria
        ],
        "field_extractors": {
            "pix_key":  r"([a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\+55[\s\d\(\)\-]{10,14}|[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
            "pix_name": r"(?:nome|name|recebedor)[\"'\s:=]+([A-Za-z\s]{3,50})",
            "pix_city": r"(?:cidade|city)[\"'\s:=]+([A-Za-z\s]{2,30})",
        },
        "field_validators": {},
        "setup_instructions": [
            "1. Use qualquer chave Pix cadastrada no seu banco: CPF, CNPJ, e-mail, telefone ou chave aleatoria",
            "2. O Nome e exibido no QR Code do pagador (maximo 25 caracteres)",
            "3. A Cidade e exibida no QR Code (maximo 15 caracteres)",
            "4. Nao e necessario nenhuma integracao adicional",
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
            "raw_credentials": r"(.+)",
            "base_url": r"(https?://[^\s\"']+)",
        },
        "field_validators": {},
        "setup_instructions": [
            "1. Cole as credenciais no campo 'Credenciais (JSON)'",
            "2. Informe a URL base da API",
            "3. O sistema armazenara de forma criptografada",
        ],
        "warnings": {}
    }
}


class APIIntelligenceEngine:
    """
    Multi-layer API credential detector and auto-configurator.
    Reads raw text (API docs, pasted credentials, JSON configs) and
    returns structured detection + field extraction + validation + instructions.
    """

    def analyze(self, raw_text: str) -> Dict[str, Any]:
        """
        Full analysis pipeline:
          1. Normalize text
          2. Score each gateway
          3. Extract fields for best match
          4. Validate extracted fields
          5. Return setup instructions + warnings
        """
        text = self._normalize(raw_text)
        if len(text) < 5:
            return {"ok": False, "error": "Texto muito curto para analise."}

        scores = self._score_gateways(text)
        best_gw, confidence = max(scores.items(), key=lambda x: x[1]) if scores else ("custom", 0.1)

        if confidence < 0.05:
            best_gw = "custom"
            confidence = 0.15

        fields = self._extract_fields(text, best_gw)
        validated = self._validate_fields(fields, best_gw)
        issues = self._check_issues(text, best_gw, fields)
        instructions = GATEWAY_INTELLIGENCE[best_gw].get("setup_instructions", [])
        meta = {k: GATEWAY_INTELLIGENCE[best_gw].get(k) for k in ("name", "logo", "color")}

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
            "runner_up": [{"gateway": gw, "confidence": round(s, 2)} for gw, s in runners],
            "field_count": len([v for v in fields.values() if v]),
            "all_valid": all(v for v in validated.values()) if validated else True,
        }

    def _normalize(self, text: str) -> str:
        # Collapse whitespace, normalize quotes, remove null bytes
        text = text.replace("\x00", "").replace("\r\n", "\n")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:16384]  # cap at 16KB

    def _score_gateways(self, text: str) -> Dict[str, float]:
        text_lower = text.lower()
        scores = {}
        for gw_id, gw in GATEWAY_INTELLIGENCE.items():
            score = 0.0
            # Keyword matching (lower weight)
            for kw in gw.get("doc_keywords", []):
                if kw.lower() in text_lower:
                    score += 0.15
            # Pattern matching (higher weight)
            for pat in gw.get("detection_patterns", []):
                try:
                    if re.search(pat, text, re.IGNORECASE):
                        score += 0.35
                except re.error:
                    pass
            # Field extraction bonus
            extracted = self._extract_fields(text, gw_id)
            score += 0.1 * len([v for v in extracted.values() if v])
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
                    # Use first capture group if available, else full match
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

        # Test mode detection
        if any(k in text_lower for k in ["test_", "sk_test", "pk_test", "sandbox", "_test_"]):
            w = warnings.get("test_mode", "Modo de testes detectado — use credenciais de producao.")
            issues.append(f"ATENCAO: {w}")

        # Missing critical fields
        gw_cfg = GATEWAY_INTELLIGENCE.get(gateway, {})
        required_by_gw = {
            "c7": ["api_key", "api_secret"],
            "mercadopago": ["access_token"],
            "stripe": ["secret_key"],
            "pagseguro": ["token", "email"],
            "efipay": ["client_id", "client_secret"],
            "pix_manual": ["pix_key"],
        }
        required = required_by_gw.get(gateway, [])
        for req in required:
            if not fields.get(req):
                issues.append(f"Campo obrigatorio nao encontrado: '{req}'")

        # Long text warning
        if len(text) > 4000:
            issues.append("Texto muito longo — cole apenas as credenciais para melhor precisao.")

        return issues


# Global instance
_engine = APIIntelligenceEngine()

def analyze_api_text(raw_text: str) -> Dict[str, Any]:
    """Public interface for Flask routes."""
    return _engine.analyze(raw_text)

def get_gateway_schema(gateway_id: str) -> Dict:
    """Returns the full schema for a gateway for UI rendering."""
    return GATEWAY_INTELLIGENCE.get(gateway_id, GATEWAY_INTELLIGENCE["custom"])

def list_supported_gateways() -> List[Dict]:
    """Returns summary list of all supported gateways."""
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
