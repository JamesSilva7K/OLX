import re

with open(r'd:\OLPG\templates\index.html', 'r', encoding='utf8') as f:
    txt = f.read()

# Define the new seller card HTML matching the second image
new_seller_card = """
    <!-- Sobre o anunciante -->
    <div style="font-family:'Nunito Sans',sans-serif; margin-top: 32px;">
      <h2 style="font-size: 20px; font-weight: 700; color: #1a1d23; margin-bottom: 16px; margin-left: 4px;">Sobre o anunciante</h2>
      
      <div class="seller-card" style="background:#fff; border-radius:12px; padding:24px; box-shadow:0 4px 16px rgba(0,0,0,0.06); border:1px solid #e5e7eb;">
        
        <!-- Validation Banner -->
        <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 16px; position: relative; margin-bottom: 24px;">
          <div style="display:inline-block; background:#ea580c; color:#fff; font-size:11px; font-weight:700; padding:2px 6px; border-radius:4px; margin-bottom:8px;">Novo</div>
          <button style="position:absolute; right:12px; top:12px; background:none; border:none; cursor:pointer; color:#6b7280;">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
          <div style="font-size: 14px; color: #1f2937; margin-bottom: 8px; line-height: 1.4;">Esta conta passou por um processo de validação de identidade</div>
          <a href="#" style="font-size: 13px; color: #6d28d9; text-decoration: none; font-weight: 600;">Saiba mais</a>
        </div>

        <!-- Header: Avatar + Info -->
        <div style="display:flex; align-items:center; gap:16px; margin-bottom:24px;">
          <div class="seller-avatar" style="width:64px; height:64px; background:#bfdbfe; border-radius:50%; display:flex; align-items:center; justify-content:center; overflow:hidden; flex-shrink:0;">
            {% if seller_avatar %}
              <img src="{{ seller_avatar }}" alt="{{ seller_name if seller_name else 'Vendedor' }}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" onerror="this.style.display='none';this.nextElementSibling.style.display='block';" />
              <svg viewBox="0 0 24 24" fill="#60a5fa" width="46" height="46" style="margin-top:10px;display:none;"><path d="M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm0 2c-3.33 0-10 1.67-10 5v3h20v-3c0-3.33-6.67-5-10-5z"/></svg>
            {% else %}
              <svg viewBox="0 0 24 24" fill="#60a5fa" width="46" height="46" style="margin-top:10px;"><path d="M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm0 2c-3.33 0-10 1.67-10 5v3h20v-3c0-3.33-6.67-5-10-5z"/></svg>
            {% endif %}
          </div>
          <div>
            <div style="font-size:12px; color:#4b5563; font-weight:600; display:flex; align-items:center; gap:4px; margin-bottom:2px;">
              Conta verificada
              <svg fill="#0ea5e9" width="14" height="14" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            </div>
            <div class="seller-name" style="font-size:20px; font-weight:700; color:#1a1d23; margin-bottom:2px;">
              {{ seller_name if seller_name else 'Vendedor OLX' }}
            </div>
            <div style="font-size:13px; color:#6b7280;">
              Último acesso há 13 horas
            </div>
          </div>
        </div>

        <!-- Barra de Nível -->
        <div style="position:relative; margin-bottom:24px; padding-top:20px;">
          <div style="position:absolute; top:0; right:0; background:#f3e8ff; color:#6d28d9; font-size:12px; font-weight:700; padding:4px 8px; border-radius:12px;">{{ seller_level if seller_level else 'Especialista' }}</div>
          <div style="display:flex; gap:4px; height:6px;">
            <div style="flex:1; background:#c4b5fd; border-radius:4px 0 0 4px;"></div>
            <div style="flex:1; background:#c4b5fd;"></div>
            <div style="flex:1; background:#c4b5fd;"></div>
            <div style="flex:1; background:#6d28d9; border-radius:0 4px 4px 0; position:relative;">
              <!-- Pin icon at the end -->
              <svg style="position:absolute; right:-6px; top:-4px;" fill="#6d28d9" width="16" height="16" viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
            </div>
          </div>
        </div>

        <!-- Since / Location -->
        <div style="display:flex; flex-direction:column; gap:8px; margin-bottom:24px; font-size:14px; color:#4b5563;">
          <div style="display:flex; align-items:center; gap:8px;">
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="#6b7280" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            Na OLX desde {{ seller_since if seller_since else 'junho de 2026' }}
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="#6b7280" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            {{ breadcrumb_zone if breadcrumb_zone else 'Parque Savoy City' }}, {{ breadcrumb_state if breadcrumb_state else 'São Paulo - SP' }}
          </div>
        </div>

        <!-- Button Access Profile -->
        <a {% if seller_fb_verified == 1 and seller_fb_url %}href="{{seller_fb_url}}" target="_blank"{% else %}href="#" onclick="event.preventDefault();"{% endif %} style="display:block; text-align:center; padding:12px; background:#fff; color:#1a1d23; border-radius:24px; font-weight:700; font-size:14px; text-decoration:none; border:1px solid #4b5563; transition:all 0.2s; margin-bottom: 24px;">
          Acessar perfil do anunciante
        </a>

        <div style="height:1px; background:#e5e7eb; margin-bottom:24px;"></div>

        <!-- Histórico de vendas -->
        <h3 style="font-size: 16px; font-weight: 700; color: #1a1d23; margin-bottom: 12px;">Histórico de vendas</h3>
        
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:20px;">
          <span style="font-size:18px; font-weight:800; color:#1f2937;">{{ seller_rating if seller_rating else '4,7' }}</span>
          <div style="display:flex; gap:2px; color:#fbbf24;">
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
            <svg width="16" height="16" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
          </div>
          <span style="font-size:12px; color:#6d28d9; font-weight:600;">({{ seller_reviews if seller_reviews else '23' }} avaliações)</span>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:12px; margin-bottom:24px;">
          <div>
            <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#16a34a" stroke-width="2" style="margin-bottom:8px;"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
            <div style="font-size:16px; font-weight:800; color:#1f2937;">{{ seller_sales_completed if seller_sales_completed else '26' }}</div>
            <div style="font-size:12px; color:#4b5563; line-height:1.2; margin-top:2px;">Vendas<br>concluídas</div>
          </div>
          <div>
            <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#dc2626" stroke-width="2" style="margin-bottom:8px;"><path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/></svg>
            <div style="font-size:16px; font-weight:800; color:#1f2937;">{{ seller_sales_canceled if seller_sales_canceled else '01' }}</div>
            <div style="font-size:12px; color:#4b5563; line-height:1.2; margin-top:2px;">Vendas<br>canceladas</div>
          </div>
          <div>
            <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#9ca3af" stroke-width="2" style="margin-bottom:8px;"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg>
            <div style="font-size:16px; font-weight:800; color:#1f2937;">{{ seller_dispatch_time if seller_dispatch_time else '03 horas' }}</div>
            <div style="font-size:12px; color:#4b5563; line-height:1.2; margin-top:2px;">Tempo médio<br>de despacho</div>
          </div>
        </div>

        <div style="height:1px; background:#e5e7eb; margin-bottom:24px;"></div>

        <!-- Informações verificadas -->
        <h3 style="font-size: 16px; font-weight: 700; color: #1a1d23; margin-bottom: 16px;">Informações verificadas</h3>
        <div style="display:flex; flex-direction:column; gap:12px;">
          {% if seller_email_verified != 0 %}
          <div style="display:flex; align-items:center; gap:8px; font-size:14px; color:#1f2937; font-weight:600;">
            <svg fill="#10b981" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            E-mail
          </div>
          {% endif %}
          
          {% if seller_phone_verified != 0 %}
          <div style="display:flex; align-items:center; gap:8px; font-size:14px; color:#1f2937; font-weight:600;">
            <svg fill="#10b981" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            Telefone
          </div>
          {% endif %}

          {% if seller_id_verified != 0 %}
          <div style="display:flex; align-items:center; gap:8px; font-size:14px; color:#1f2937; font-weight:600;">
            <svg fill="#10b981" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            Identidade
          </div>
          {% endif %}
        </div>

      </div>
    </div>
"""

start_str = '<!-- Seller Card Renovado -->'
end_str = '  </div><!-- /right-col -->'

start_idx = txt.find(start_str)
end_idx = txt.find(end_str)

if start_idx != -1 and end_idx != -1:
    txt = txt[:start_idx] + new_seller_card + '\n' + txt[end_idx:]
else:
    print("Could not find seller card markers.")

with open(r'd:\OLPG\templates\index.html', 'w', encoding='utf8') as f:
    f.write(txt)
