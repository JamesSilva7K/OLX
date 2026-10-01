"""
Auditoria de rotas e consistência de dados -- OLPG/app.py
Roda standalone, sem iniciar Flask.
"""
import re, sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def scan_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return lines

# ── 1. Mapear todas as rotas do app.py ────────────────────────────────────────
app_lines = scan_file("app.py")
routes = []
for i, ln in enumerate(app_lines):
    m = re.search(r"@app\.route\(['\"]([^'\"]+)['\"](?:.*?methods=\[([^\]]+)\])?", ln)
    if m:
        path = m.group(1)
        methods = (m.group(2) or "GET").replace("'","").replace('"','')
        routes.append((i+1, path, methods))

print("=" * 68)
print(f"  ROTAS ENCONTRADAS: {len(routes)}")
print("=" * 68)
for ln, path, meth in routes:
    print(f"  L{ln:<5} {meth:<25} {path}")

# ── 2. Verificar o que cada rota importante retorna ──────────────────────────
print("\n" + "=" * 68)
print("  VERIFICANDO CAMPOS DE RETORNO (jsonify)")
print("=" * 68)

content = "".join(app_lines)

# Find all jsonify calls to check what keys are returned
jsonify_calls = re.findall(r"jsonify\(\{([^}]{1,400})\}", content)
problem_keys = []
for j in jsonify_calls:
    if "ok" not in j and "error" not in j and "token" not in j:
        problem_keys.append(j[:80].strip())

if problem_keys:
    print(f"\n  [WARN] {len(problem_keys)} jsonify() sem campo 'ok' nem 'error':")
    for p in problem_keys[:10]:
        print(f"    → {p}")
else:
    print("\n  [OK] Todos os jsonify() têm campo 'ok' ou 'error'.")

# ── 3. Verificar rotas que o frontend JS chama mas podem não existir ──────────
print("\n" + "=" * 68)
print("  CRUZANDO CHAMADAS JS vs ROTAS BACKEND")
print("=" * 68)

admin_lines = scan_file("templates/admin.html")
admin_content = "".join(admin_lines)

# Extract API calls from JS
api_calls = re.findall(r"apiFetch(?:Safe)?\(['\"]([^'\"]+)['\"]", admin_content)
api_calls += re.findall(r"fetch\(['\"]([^'\"]+)['\"]", admin_content)
api_calls = sorted(set(api_calls))

route_paths = set(p for _, p, _ in routes)

print(f"\n  Chamadas API no frontend: {len(api_calls)}")
missing = []
ok_calls = []
for call in api_calls:
    # strip query string
    base = call.split("?")[0].split("+")[0].strip().rstrip("'")
    # dynamic slugs — normalize
    base_norm = re.sub(r"/[a-zA-Z_]+/\+", "/<x>/", base)
    # check if any route matches (simple substring)
    found = any(
        base.startswith(r) or r.startswith(base) or 
        re.sub(r"<[^>]+>", "X", r) in base or
        base in r
        for r in route_paths
    )
    if not found:
        missing.append(base)
    else:
        ok_calls.append(base)

if missing:
    print(f"\n  [WARN] {len(missing)} chamada(s) JS sem rota clara no backend:")
    for m in missing:
        print(f"    ✗ {m}")
else:
    print(f"\n  [OK] Todas as {len(ok_calls)} chamadas JS mapeadas.")

# ── 4. Verificar campos esperados pelo JS vs retornados pelo backend ──────────
print("\n" + "=" * 68)
print("  VERIFICANDO CAMPOS CRÍTICOS NOS ENDPOINTS")
print("=" * 68)

# Key data contracts to verify
checks = [
    ("/api/admin/stats",   ["ok", "stats"]),
    ("/api/admin/events",  ["ok", "events"]),
    ("/api/admin/sessions",["ok", "sessions"]),
    ("/api/admin/verify-token", ["ok", "admin_id", "role"]),
    ("/api/admin/request-code", ["ok", "expires"]),
    ("/api/config",        ["product_name", "product_price"]),
    ("/api/products",      ["ok", "products"]),
]

for endpoint, expected_fields in checks:
    # find the function returning this endpoint
    pattern = re.escape(endpoint).replace(r"\<", "<").replace(r"\>", ">")
    # look for the endpoint definition
    block_start = content.find(f"'{endpoint}'")
    if block_start == -1:
        block_start = content.find(f'"{endpoint}"')
    if block_start == -1:
        print(f"  [??] {endpoint} — rota NÃO encontrada no backend!")
        continue
    # extract next ~600 chars as the block
    block = content[block_start:block_start+1200]
    missing_fields = [f for f in expected_fields if f not in block]
    if missing_fields:
        print(f"  [WARN] {endpoint}")
        print(f"         Campos ausentes: {missing_fields}")
    else:
        print(f"  [OK]  {endpoint} → campos {expected_fields}")

# ── 5. Verificar erros Python (syntax) ────────────────────────────────────────
print("\n" + "=" * 68)
print("  VERIFICANDO SINTAXE DOS ARQUIVOS PRINCIPAIS")
print("=" * 68)
import subprocess, sys
for fname in ["app.py", "bot.py"]:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", fname],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  [OK]  {fname} — sintaxe válida")
    else:
        print(f"  [ERR] {fname} — ERRO DE SINTAXE:")
        print("       ", result.stderr[:300])

print("\n" + "=" * 68)
print("  AUDITORIA CONCLUÍDA")
print("=" * 68)
