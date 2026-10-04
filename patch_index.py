import re

with open(r'd:\OLPG\templates\index.html', 'r', encoding='utf8') as f:
    txt = f.read()

# Modify the seller card in index.html to look amazing
seller_card_html = """
    <!-- Seller Card Renovado -->
    <div class="seller-card" style="font-family:'Nunito Sans',sans-serif; background:#fff; border-radius:12px; padding:20px; box-shadow:0 4px 12px rgba(0,0,0,0.06); border:1px solid #eaeaea;">
      <div class="seller-header" style="display:flex; align-items:center; gap:16px; margin-bottom:16px;">
        <div class="seller-avatar" style="width:64px; height:64px; background:#f5f5f5; border-radius:50%; display:flex; align-items:center; justify-content:center; overflow:hidden; flex-shrink:0; border:2px solid #e2e8f0; position:relative;">
          {% if seller_avatar %}
            <img src="{{ seller_avatar }}" alt="{{ seller_name if seller_name else 'Vendedor' }}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" onerror="this.style.display='none';this.nextElementSibling.style.display='block';" />
            <svg viewBox="0 0 24 24" fill="#cfd4d9" width="46" height="46" style="margin-top:10px;display:none;"><path d="M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm0 2c-3.33 0-10 1.67-10 5v3h20v-3c0-3.33-6.67-5-10-5z"/></svg>
          {% else %}
            <svg viewBox="0 0 24 24" fill="#cfd4d9" width="46" height="46" style="margin-top:10px;"><path d="M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm0 2c-3.33 0-10 1.67-10 5v3h20v-3c0-3.33-6.67-5-10-5z"/></svg>
          {% endif %}
          <div style="position:absolute; bottom:0; right:0; width:16px; height:16px; background:#10b981; border:2px solid #fff; border-radius:50%;" title="Online agora"></div>
        </div>
        <div style="flex:1;">
          <div class="seller-name" style="font-size:18px; font-weight:800; color:#1f2937; display:flex; align-items:center; gap:6px;">
            {{ seller_name if seller_name else 'Vendedor OLX' }}
            <svg fill="#8b5cf6" width="16" height="16" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
          </div>
          <div style="font-size:13px; color:#6b7280; font-weight:600; display:flex; align-items:center; gap:6px; margin-top:4px;">
            <svg fill="#f59e0b" width="14" height="14" viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>
            {{ seller_rating if seller_rating else '4.9' }} ({{ seller_reviews if seller_reviews else '120' }} avaliações)
          </div>
        </div>
      </div>

      <div style="background:#f9fafb; border-radius:8px; padding:12px; margin-bottom:16px; display:flex; justify-content:space-between; text-align:center;">
        <div>
          <div style="font-size:16px; font-weight:800; color:#111827;">{{ seller_sales_completed if seller_sales_completed else '34' }}</div>
          <div style="font-size:11px; color:#6b7280; text-transform:uppercase; font-weight:700;">Vendas</div>
        </div>
        <div style="width:1px; background:#e5e7eb;"></div>
        <div>
          <div style="font-size:16px; font-weight:800; color:#111827;">{{ seller_sales_canceled if seller_sales_canceled else '0' }}</div>
          <div style="font-size:11px; color:#6b7280; text-transform:uppercase; font-weight:700;">Canceladas</div>
        </div>
        <div style="width:1px; background:#e5e7eb;"></div>
        <div>
          <div style="font-size:16px; font-weight:800; color:#111827;">{{ seller_dispatch_time if seller_dispatch_time else '1 dia' }}</div>
          <div style="font-size:11px; color:#6b7280; text-transform:uppercase; font-weight:700;">Despacho</div>
        </div>
      </div>

      <!-- Barra de Experiência (Fidelidade OLX) -->
      <div style="margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-size:12px; font-weight:800; color:#374151; display:flex; align-items:center; gap:6px;">
            <svg fill="#8b5cf6" width="14" height="14" viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2zm0 3.8l7.5 13.2H4.5L12 5.8z"/></svg>
            {{ seller_level if seller_level else 'Nível Especialista' }}
          </span>
          <span style="font-size:12px; font-weight:700; color:#8b5cf6;">100% Excelente</span>
        </div>
        <div style="width:100%; height:6px; background:#e5e7eb; border-radius:4px; overflow:hidden;">
          <div style="width:100%; height:100%; background:linear-gradient(90deg, #8b5cf6, #3b82f6); border-radius:4px;"></div>
        </div>
      </div>

      <!-- Verificações -->
      <div style="display:flex; flex-direction:column; gap:10px; margin-bottom:16px;">
        {% if seller_email_verified != 0 %}
        <div style="display:flex; align-items:center; gap:10px; font-size:13px; color:#4b5563; font-weight:600;">
          <div style="background:#e0e7ff; width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center;">
            <svg fill="none" stroke="#4f46e5" stroke-width="2.5" width="14" height="14" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
          </div>
          E-mail verificado
          <svg fill="#10b981" width="16" height="16" viewBox="0 0 24 24" style="margin-left:auto;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
        </div>
        {% endif %}
        
        {% if seller_phone_verified != 0 %}
        <div style="display:flex; align-items:center; gap:10px; font-size:13px; color:#4b5563; font-weight:600;">
          <div style="background:#dcfce7; width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center;">
            <svg fill="none" stroke="#16a34a" stroke-width="2.5" width="14" height="14" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg>
          </div>
          Telefone verificado
          <svg fill="#10b981" width="16" height="16" viewBox="0 0 24 24" style="margin-left:auto;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
        </div>
        {% endif %}

        {% if seller_id_verified != 0 %}
        <div style="display:flex; align-items:center; gap:10px; font-size:13px; color:#4b5563; font-weight:600;">
          <div style="background:#ffedd5; width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center;">
            <svg fill="none" stroke="#ea580c" stroke-width="2.5" width="14" height="14" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2"/></svg>
          </div>
          Identidade confirmada
          <svg fill="#10b981" width="16" height="16" viewBox="0 0 24 24" style="margin-left:auto;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
        </div>
        {% endif %}
      </div>

      <div class="seller-since" style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: #6b7280; font-weight:600; justify-content:center; margin-bottom:16px;">
        <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="#9ca3af" stroke-width="2.5"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        Na OLX desde {{ seller_since if seller_since else 'Setembro 2021' }}
      </div>

      <a {% if seller_fb_verified == 1 and seller_fb_url %}href="{{seller_fb_url}}" target="_blank"{% else %}href="#" onclick="event.preventDefault();"{% endif %} style="display:block; text-align:center; padding:12px; background:#f3f4f6; color:#4b5563; border-radius:8px; font-weight:800; font-size:14px; text-decoration:none; border:1px solid #e5e7eb; transition:all 0.2s;">
        Acessar perfil completo
      </a>
    </div>
"""

start_str = '<!-- Seller Card Identico -->'
end_str = '  </div><!-- /right-col -->'

start_idx = txt.find(start_str)
end_idx = txt.find(end_str)

if start_idx != -1 and end_idx != -1:
    txt = txt[:start_idx] + seller_card_html + '\n' + txt[end_idx:]
else:
    print("Could not find seller card markers.")

with open(r'd:\OLPG\templates\index.html', 'w', encoding='utf8') as f:
    f.write(txt)
