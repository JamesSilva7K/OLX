with open(r'd:\OLPG\templates\index.html', 'r', encoding='utf8') as f:
    txt = f.read()

start_marker = '<!-- Sobre o anunciante -->'
end_marker = '  </div><!-- /right-col -->'

start_idx = txt.find(start_marker)
end_idx = txt.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"Markers not found: start={start_idx}, end={end_idx}")
else:
    new_section = '''<!-- Sobre o anunciante -->
    <div style="font-family:'Nunito Sans',sans-serif; margin-top: 32px;">
      <h2 style="font-size: 20px; font-weight: 700; color: #1a1d23; margin-bottom: 16px; margin-left: 4px;">Sobre o anunciante</h2>
      
      <div class="seller-card" style="background:#fff; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.07); border:1px solid #e5e7eb;">
        
        <!-- Banner identidade -->
        <div id="id-validation-banner" style="border:1px solid #e5e7eb; border-radius:8px; padding:12px 14px; position:relative; margin-bottom:18px;">
          <div style="display:inline-block; background:#ea580c; color:#fff; font-size:11px; font-weight:700; padding:2px 7px; border-radius:4px; margin-bottom:6px;">Novo</div>
          <button onclick="document.getElementById('id-validation-banner').style.display='none'" style="position:absolute; right:10px; top:10px; background:none; border:none; cursor:pointer; color:#6b7280; line-height:1;">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
          <div style="font-size:13px; color:#1f2937; margin-bottom:6px; line-height:1.45; padding-right:20px;">Esta conta passou por um processo de validação de identidade</div>
          <a href="#" style="font-size:13px; color:#6d28d9; text-decoration:none; font-weight:600;">Saiba mais</a>
        </div>

        <!-- Avatar + Info -->
        <div style="display:flex; align-items:center; gap:14px; margin-bottom:14px;">
          <div style="width:54px; height:54px; background:#bfdbfe; border-radius:50%; display:flex; align-items:center; justify-content:center; overflow:hidden; flex-shrink:0;">
            {% if seller_avatar %}
              <img src="{{ seller_avatar }}" alt="{{ seller_name if seller_name else 'Vendedor' }}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" onerror="this.style.display='none'" />
            {% else %}
              <svg viewBox="0 0 24 24" fill="#60a5fa" width="32" height="32"><path d="M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm0 2c-3.33 0-10 1.67-10 5v3h20v-3c0-3.33-6.67-5-10-5z"/></svg>
            {% endif %}
          </div>
          <div>
            <div style="font-size:11px; color:#6b7280; font-weight:600; display:flex; align-items:center; gap:3px; margin-bottom:1px;">
              Conta verificada
              <svg fill="#3b82f6" width="12" height="12" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            </div>
            <div style="font-size:18px; font-weight:700; color:#1a1d23; line-height:1.2; margin-bottom:1px;">{{ seller_name if seller_name else 'Vendedor OLX' }}</div>
            <div style="font-size:12px; color:#6b7280;">Último acesso há 11 horas</div>
          </div>
        </div>

        <!-- Barra de nível -->
        <div style="position:relative; margin-bottom:18px;">
          <div style="position:absolute; top:-4px; right:0; background:#f3e8ff; color:#7c3aed; font-size:11px; font-weight:700; padding:3px 8px; border-radius:10px;">{{ seller_level if seller_level else 'Especialista' }}</div>
          <div style="display:flex; gap:3px; height:5px; margin-top:18px;">
            <div style="flex:1; background:#c4b5fd; border-radius:3px 0 0 3px;"></div>
            <div style="flex:1; background:#c4b5fd;"></div>
            <div style="flex:1; background:#c4b5fd;"></div>
            <div style="flex:1; background:#7c3aed; border-radius:0 3px 3px 0; position:relative;">
              <svg style="position:absolute; right:-3px; top:-7px;" fill="#7c3aed" width="14" height="14" viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
            </div>
          </div>
        </div>

        <!-- Na OLX / Localização -->
        <div style="display:flex; flex-direction:column; gap:9px; margin-bottom:16px; font-size:13px; color:#374151;">
          <div style="display:flex; align-items:center; gap:7px;">
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="#6b7280" stroke-width="2" style="flex-shrink:0;"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            Na OLX desde {{ seller_since if seller_since else 'junho de 2026' }}
          </div>
          <div style="display:flex; align-items:center; gap:7px;">
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="#6b7280" stroke-width="2" style="flex-shrink:0;"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            {{ breadcrumb_zone if breadcrumb_zone else 'Parque Savoy City' }}, {{ breadcrumb_state if breadcrumb_state else 'São Paulo - SP' }}
          </div>
        </div>

        <!-- Botão Acessar Perfil -->
        <a {% if seller_fb_verified == 1 and seller_fb_url %}href="{{ seller_fb_url }}" target="_blank"{% else %}href="#" onclick="event.preventDefault();"{% endif %} style="display:block; text-align:center; padding:10px 16px; background:#fff; color:#1a1d23; border-radius:22px; font-weight:600; font-size:13.5px; text-decoration:none; border:1.5px solid #4b5563; margin-bottom:24px;">
          Acessar perfil do anunciante
        </a>

        <!-- Histórico de vendas -->
        <h3 style="font-size:15px; font-weight:700; color:#1a1d23; margin:0 0 10px;">Histórico de vendas</h3>

        <div style="display:flex; align-items:center; gap:5px; margin-bottom:16px;">
          <span style="font-size:16px; font-weight:800; color:#1f2937;">{{ seller_rating if seller_rating else '4,7' }}</span>
          <svg width="14" height="14" fill="#f59e0b" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
          <svg width="14" height="14" fill="#f59e0b" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
          <svg width="14" height="14" fill="#f59e0b" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
          <svg width="14" height="14" fill="#f59e0b" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
          <svg width="14" height="14" viewBox="0 0 20 20"><defs><linearGradient id="hstar"><stop offset="70%" stop-color="#f59e0b"/><stop offset="70%" stop-color="#d1d5db"/></linearGradient></defs><path fill="url(#hstar)" d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
          <span style="font-size:12px; color:#6b7280;">({{ seller_reviews if seller_reviews else '23' }} avaliações)</span>
        </div>

        <!-- Stats 3 cols -->
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; margin-bottom:24px;">
          <div>
            <svg width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="#16a34a" stroke-width="2" style="margin-bottom:5px; display:block;"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
            <div style="font-size:15px; font-weight:800; color:#111;">{{ seller_sales_completed if seller_sales_completed else '26' }}</div>
            <div style="font-size:11px; color:#6b7280; line-height:1.3; margin-top:2px;">Vendas<br>concluídas</div>
          </div>
          <div>
            <svg width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="#ef4444" stroke-width="2" style="margin-bottom:5px; display:block;"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
            <div style="font-size:15px; font-weight:800; color:#111;">{{ seller_sales_canceled if seller_sales_canceled else '01' }}</div>
            <div style="font-size:11px; color:#6b7280; line-height:1.3; margin-top:2px;">Vendas<br>canceladas</div>
          </div>
          <div>
            <svg width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="#9ca3af" stroke-width="2" style="margin-bottom:5px; display:block;"><rect x="1" y="3" width="15" height="13" rx="2"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
            <div style="font-size:15px; font-weight:800; color:#111;">{{ seller_dispatch_time if seller_dispatch_time else '03 horas' }}</div>
            <div style="font-size:11px; color:#6b7280; line-height:1.3; margin-top:2px;">Tempo médio<br>de despacho</div>
          </div>
        </div>

        <!-- Informações verificadas -->
        <h3 style="font-size:15px; font-weight:700; color:#1a1d23; margin:0 0 12px;">Informações verificadas</h3>
        <div style="display:flex; flex-direction:column; gap:10px;">
          {% if seller_email_verified != 0 %}
          <div style="display:flex; align-items:center; gap:8px; font-size:14px; color:#1f2937;">
            <svg fill="#10b981" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            E-mail
          </div>
          {% endif %}
          {% if seller_phone_verified != 0 %}
          <div style="display:flex; align-items:center; gap:8px; font-size:14px; color:#1f2937;">
            <svg fill="#10b981" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            Telefone
          </div>
          {% endif %}
          {% if seller_id_verified != 0 %}
          <div style="display:flex; align-items:center; gap:8px; font-size:14px; color:#1f2937;">
            <svg fill="#10b981" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            Identidade
          </div>
          {% endif %}
          <!-- Facebook sempre visível: verde se ativo, cinza se não -->
          <div style="display:flex; align-items:center; gap:8px; font-size:14px; color:#1f2937;">
            {% if seller_fb_verified == 1 %}
              <svg fill="#10b981" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
            {% else %}
              <svg fill="#9ca3af" width="18" height="18" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6H9v-2h2V9c0-2.21 1.34-3 3-3 .88 0 1.73.07 2 .1v2h-1c-1.1 0-1 .52-1 1v1h2.5l-.5 2H14v6z"/></svg>
            {% endif %}
            Facebook
          </div>
        </div>

      </div>
    </div>

  '''

    txt = txt[:start_idx] + new_section + end_marker + txt[end_idx + len(end_marker):]
    print("Done")

with open(r'd:\OLPG\templates\index.html', 'w', encoding='utf8') as f:
    f.write(txt)
