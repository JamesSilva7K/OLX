"""Fix stats 401 response — add ok:False"""
with open('app.py', encoding='utf-8') as f:
    content = f.read()

old = '        return jsonify({"error": "unauthorized"}), 401\n\n    if TG_WH_AVAILABLE:\n        if role == "supreme_admin":'
new = '        return jsonify({"ok": False, "error": "unauthorized"}), 401\n\n    if TG_WH_AVAILABLE:\n        if role == "supreme_admin":'
count = content.count(old)
print('occurrences found:', count)
if count == 1:
    new_content = content.replace(old, new, 1)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Fixed stats 401.')
else:
    print('Context not unique, cannot replace safely')
