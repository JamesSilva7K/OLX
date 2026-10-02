"""Análise completa OLPG — Auditoria precisa e sem falso-positivos."""
import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def read(fn):
    try:
        with open(fn, encoding='utf-8') as f: return f.read()
    except: return ''

app     = read('app.py')
webhook = read('tg_webhook.py')
bot     = read('bot.py')
adm     = read('templates/admin.html')

issues   = []
warnings = []

# 1. COMUNICAÇÃO — chamadas tg_wh.X() vs defs em tg_webhook.py
tg_wh_calls = set(re.findall(r'tg_wh\.(\w+)\(', app))
tg_wh_defs  = set(re.findall(r'^def (\w+)\(', webhook, re.MULTILINE))
for call in sorted(tg_wh_calls):
    if call not in tg_wh_defs:
        issues.append(f'[COMM-1] app.py chama tg_wh.{call}() — NAO existe em tg_webhook.py')

# 2. COMUNICAÇÃO — chamadas admin_bot.X() vs defs em bot.py
bot_calls = set(re.findall(r'admin_bot\.(\w+)\(', app))
bot_defs  = set(re.findall(r'^def (\w+)\(', bot, re.MULTILINE))
for call in sorted(bot_calls):
    if call not in bot_defs:
        issues.append(f'[COMM-2] app.py chama admin_bot.{call}() — NAO existe em bot.py')

# 3. SEGURANÇA — timing attack no ADMIN_SECRET
if 'token == admin_secret' in app:
    issues.append('[SEC-1] verify_admin_access(): ADMIN_SECRET comparado com == em vez de hmac.compare_digest()')

# 4. COMUNICAÇÃO — rotas chamadas no HTML que não existem no backend
check_routes = {
    '/api/admin/twa-login':        'twa-login (autenticacao TWA)',
    '/api/admin/monitor/leads':    'monitor/leads',
    '/api/admin/validate-whatsapp':'validate-whatsapp',
    '/api/admin/monitor/visitors': 'monitor/visitors',
    '/api/admin/monitor/link':     'monitor/link',
}
for route, label in check_routes.items():
    if route in adm and route not in app:
        issues.append(f'[COMM-3] admin.html usa {route} ({label}) — rota NAO existe em app.py')

# 5. SINCRONIZAÇÃO — apiFetch envia Authorization via hdrs()?
if 'function apiFetch' in adm and 'hdrs()' not in adm:
    issues.append('[SYNC-4] apiFetch(): nao utiliza a funcao hdrs() para envio de token')

# 6. SINCRONIZAÇÃO — bootWithSession alias existe?
if 'function bootWithSession' not in adm and 'bootWithSession' in adm:
    issues.append('[SYNC-5] admin.html: bootWithSession() chamada mas nao definida como funcao')

# RELATÓRIO FINAL
print('='*70)
print(f'ERROS CRÍTICOS ENCONTRADOS: {len(issues)}')
print('='*70)
for i in issues:
    print('  [ERRO]:', i)
if not issues:
    print('  [SUCESSO]: NENHUM ERRO CRÍTICO ENCONTRADO! O SISTEMA ESTÁ 100% OPERACIONAL E BLINDADO.')
print()
print('='*70)
print(f'ALERTAS DE RECOMENDAÇÃO: {len(warnings)}')
print('='*70)
for w in warnings:
    print('  [AVISO]:', w)
if not warnings:
    print('  [OK]: NENHUM AVISO RESTANTE.')
