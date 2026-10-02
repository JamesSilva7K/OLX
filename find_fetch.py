with open('templates/admin.html', encoding='utf-8') as f:
    content = f.read()
# Find apiFetch
idx = content.find('apiFetch')
if idx < 0:
    print('apiFetch NAO encontrado no arquivo!')
else:
    # Find the function definition
    fn_idx = content.rfind('apiFetch', 0, idx)
    # Search for 'async function' or similar before apiFetch
    import re
    matches = [(m.start(), m.group()) for m in re.finditer(r'(?:async\s+)?function\s+apiFetch\b', content)]
    print(f'apiFetch encontrado {len(list(re.finditer("apiFetch", content)))} vezes')
    print('Definicoes de funcao apiFetch:')
    for start, match in matches:
        print(f'  Linha aprox {content[:start].count(chr(10))+1}: {content[start:start+100]}')
    
    # Also check what pattern is used for API calls
    # Look for fetch( calls
    fetch_matches = list(re.finditer(r'await fetch\(|const r\s*=\s*await', content))
    print(f'\nTotal de await fetch() / const r = await: {len(fetch_matches)}')
    if fetch_matches:
        first = fetch_matches[0]
        snip = content[first.start():first.start()+300]
        print('Primeiro exemplo:')
        print(snip[:200])
