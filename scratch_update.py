import re

file_path = r'd:\OLPG\templates\index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the coupon SVG
old_svg_block = r'<div class="coupon-banner-exact">\s*<div class="coupon-exact-left">\s*<svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#6e0ad6" stroke-width="2\.5" style="transform: rotate\(-10deg\);"><path d="M15\.3 4\.3.*?<\/svg>\s*<div>\s*<div class="coupon-exact-title">R\$ 26 OFF<\/div>\s*<div class="coupon-exact-sub">Cobre as taxas do PARCELA\? em atraso do seu pagamento\.<\/div>\s*<div class="coupon-exact-link">Cupom limitado\.<\/div>\s*<\/div>\s*<\/div>\s*<button class="coupon-copy-btn-exact" id="coupon-copy-btn">Copiar<\/button>\s*<\/div>'

new_svg_block = '''<div class="coupon-banner-exact">
          <div class="coupon-exact-left">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6a00d5" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="transform: rotate(-45deg); margin-top: 4px;"><path d="M22 10a2 2 0 0 0-2-2 4 4 0 0 1-4-4 2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2 4 4 0 0 1 4 4 2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4z"></path></svg>
            <div>
              <div class="coupon-exact-title">R$ 26 OFF</div>
              <div class="coupon-exact-sub">Cobre as taxas do PARCELA em atraso do<br>seu pagamento.</div>
              <div class="coupon-exact-link">Cupom limitado.</div>
            </div>
          </div>
          <button class="coupon-copy-btn-exact" id="coupon-copy-btn">Copiar</button>
        </div>'''

content = re.sub(old_svg_block, new_svg_block, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("HTML updated!")
