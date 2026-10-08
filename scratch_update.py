import re

file_path = r'd:\OLPG\templates\index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_css = r'\.coupon-exact-sub \{.*?\}'
new_css = '''.coupon-exact-sub {
      font-size: 11px;
      color: #4a4a4a;
      line-height: 1.3;
      margin-top: 3px;
      font-weight: 500;
    }'''
content = re.sub(old_css, new_css, content, flags=re.DOTALL)

old_bg = r'\.coupon-banner-exact \{.*?background:\s*#[a-fA-F0-9]+;.*?\}'
new_bg = '''.coupon-banner-exact {
      display: flex;
      align-items: stretch;
      justify-content: space-between;
      border: 1px solid #e3d2ff;
      border-right: none;
      border-radius: 8px;
      margin-bottom: 20px;
      background: #faf5ff;
      height: 76px;
    }'''
content = re.sub(old_bg, new_bg, content, flags=re.DOTALL)

old_svg_block = r'<div class="coupon-banner-exact">\s*<div class="coupon-exact-left">\s*<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6a00d5" stroke-width="2\.2" stroke-linecap="round" stroke-linejoin="round" style="transform: rotate\(-45deg\); margin-top: 4px;"><path d="M22 10a2 2 0 0 0-2-2 4 4 0 0 1-4-4 2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2 4 4 0 0 1 4 4 2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4z"><\/path><\/svg>\s*<div>\s*<div class="coupon-exact-title">R\$ 26 OFF<\/div>\s*<div class="coupon-exact-sub">Cobre as taxas do PARCELA em atraso do<br>seu pagamento\.<\/div>\s*<div class="coupon-exact-link">Cupom limitado\.<\/div>\s*<\/div>\s*<\/div>\s*<button class="coupon-copy-btn-exact" id="coupon-copy-btn">Copiar<\/button>\s*<\/div>'

new_svg_block = '''<div class="coupon-banner-exact">
          <div class="coupon-exact-left">
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#6a00d5" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1.5" fill="#6a00d5" stroke="none"/></svg>
            <div>
              <div class="coupon-exact-title">R$ 26 OFF</div>
              <div class="coupon-exact-sub">Cobre as taxas do PARCELA? em atraso<br>do seu pagamento.</div>
              <div class="coupon-exact-link">Cupom limitado.</div>
            </div>
          </div>
          <button class="coupon-copy-btn-exact" id="coupon-copy-btn">Copiar</button>
        </div>'''

content = re.sub(old_svg_block, new_svg_block, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("HTML updated!")
