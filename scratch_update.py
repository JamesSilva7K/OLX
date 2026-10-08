import re

file_path = r'd:\OLPG\templates\index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the coupon SVG
old_svg = r'<svg width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="#7B02E8" stroke-width="2"><path \s*d="M20.59 13.41.*?<\/svg>'
new_svg = r'<svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#6e0ad6" stroke-width="2.5" style="transform: rotate(-10deg);"><path d="M15.3 4.3a2 2 0 0 1 2.8 0l1.6 1.6a2 2 0 0 1 0 2.8l-9 9a2 2 0 0 1-2.8 0L6.3 16.1a2 2 0 0 1 0-2.8l9-9z"/><path d="M11.5 7.5l-3 3M15 11l-3 3"/></svg>'
content = re.sub(old_svg, new_svg, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("SVG updated!")
