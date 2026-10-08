import re

file_path = r'd:\OLPG\templates\index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update tags
old_tags = r'<div class="product-tags">.*?</div>'
new_tags = '''<div class="product-tags">
          <span class="tag tag-green-badge">Entrega rápida</span>
          <span class="tag tag-purple-badge"><svg width="12" height="12" viewBox="0 0 24 24" fill="#6e0ad6"><path d="M10.5 4.5l-4 4 4 4"/></svg> Permite auto / Uber</span>
          <span class="tag tag-purple-badge" style="display:inline-flex; align-items:center; gap:4px;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#6e0ad6" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            Garantia da OLX
          </span>
        </div>'''
content = re.sub(old_tags, new_tags, content, flags=re.DOTALL)

# 2. Update price "no Pix" to "com Pix" and color
content = content.replace('>no Pix<', '>com Pix<').replace('color:#4b9015', 'color:#00a650')

# 3. Add gray block below description
old_desc = r'(<p class="product-description".*?</p>)'
new_desc = r'\1\n        <div style="margin-top:20px; height:60px; background:#f4f4f4; border-radius:8px;"></div>'
if 'height:60px; background:#f4f4f4' not in content:
    content = re.sub(old_desc, new_desc, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("HTML updated successfully.")
