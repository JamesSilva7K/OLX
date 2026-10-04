import re

with open(r'd:\OLPG\templates\admin.html', 'r', encoding='utf8') as f:
    txt = f.read()

# Replace saveProd function payload
payload_add = '''    seller_sales_completed: document.getElementById('edit-seller-sales-completed') ? document.getElementById('edit-seller-sales-completed').value.trim() : "",
    seller_sales_canceled: document.getElementById('edit-seller-sales-canceled') ? document.getElementById('edit-seller-sales-canceled').value.trim() : "",
    seller_dispatch_time: document.getElementById('edit-seller-dispatch-time') ? document.getElementById('edit-seller-dispatch-time').value.trim() : "",
    seller_rating: document.getElementById('edit-seller-rating') ? document.getElementById('edit-seller-rating').value.trim() : "",
    seller_reviews: document.getElementById('edit-seller-reviews') ? document.getElementById('edit-seller-reviews').value.trim() : "",
    seller_level: document.getElementById('edit-seller-level') ? document.getElementById('edit-seller-level').value.trim() : "",
    seller_email_verified: document.getElementById('edit-seller-email-verified') ? (document.getElementById('edit-seller-email-verified').checked ? 1 : 0) : 1,
    seller_phone_verified: document.getElementById('edit-seller-phone-verified') ? (document.getElementById('edit-seller-phone-verified').checked ? 1 : 0) : 1,
    seller_id_verified: document.getElementById('edit-seller-id-verified') ? (document.getElementById('edit-seller-id-verified').checked ? 1 : 0) : 1,
    seller_fb_verified: document.getElementById('edit-seller-fb-verified') ? (document.getElementById('edit-seller-fb-verified').checked ? 1 : 0) : 0,
    seller_fb_url: document.getElementById('edit-seller-fb-url') ? document.getElementById('edit-seller-fb-url').value.trim() : "",
'''

txt = txt.replace(
    "seller_avatar: (document.getElementById('edit-seller-avatar')?.value||'').trim(),",
    "seller_avatar: (document.getElementById('edit-seller-avatar')?.value||'').trim(),\n" + payload_add
)

# Update editProd modal open logic
modal_populate_add = '''
  if(document.getElementById('edit-seller-sales-completed')) document.getElementById('edit-seller-sales-completed').value = p.seller_sales_completed || '';
  if(document.getElementById('edit-seller-sales-canceled')) document.getElementById('edit-seller-sales-canceled').value = p.seller_sales_canceled || '';
  if(document.getElementById('edit-seller-dispatch-time')) document.getElementById('edit-seller-dispatch-time').value = p.seller_dispatch_time || '';
  if(document.getElementById('edit-seller-rating')) document.getElementById('edit-seller-rating').value = p.seller_rating || '';
  if(document.getElementById('edit-seller-reviews')) document.getElementById('edit-seller-reviews').value = p.seller_reviews || '';
  if(document.getElementById('edit-seller-level')) document.getElementById('edit-seller-level').value = p.seller_level || '';
  
  if(document.getElementById('edit-seller-email-verified')) document.getElementById('edit-seller-email-verified').checked = (p.seller_email_verified === undefined || p.seller_email_verified == 1);
  if(document.getElementById('edit-seller-phone-verified')) document.getElementById('edit-seller-phone-verified').checked = (p.seller_phone_verified === undefined || p.seller_phone_verified == 1);
  if(document.getElementById('edit-seller-id-verified')) document.getElementById('edit-seller-id-verified').checked = (p.seller_id_verified === undefined || p.seller_id_verified == 1);
  if(document.getElementById('edit-seller-fb-verified')) document.getElementById('edit-seller-fb-verified').checked = (p.seller_fb_verified == 1);
  if(document.getElementById('edit-seller-fb-url')) document.getElementById('edit-seller-fb-url').value = p.seller_fb_url || '';
  if(typeof toggleFbUrl === 'function') toggleFbUrl();
'''

txt = txt.replace(
    "if(document.getElementById('edit-shipping-coupon')) document.getElementById('edit-shipping-coupon').value = p.shipping_coupon||'';",
    "if(document.getElementById('edit-shipping-coupon')) document.getElementById('edit-shipping-coupon').value = p.shipping_coupon||'';\n" + modal_populate_add
)

# Insert the HTML form fields into the admin modal.
# We will insert them right after edit-seller-since

html_add = '''
      <div class="fr">
        <div class="fg">
          <label class="flbl">Nível (Ex: Especialista)</label>
          <input type="text" class="fi" id="edit-seller-level" placeholder="Especialista"/>
        </div>
        <div class="fg">
          <label class="flbl">Nota / Estrelas (Ex: 4,7)</label>
          <input type="text" class="fi" id="edit-seller-rating" placeholder="4,7"/>
        </div>
      </div>
      <div class="fr">
        <div class="fg">
          <label class="flbl">Vendas Concluídas</label>
          <input type="number" class="fi" id="edit-seller-sales-completed" placeholder="26"/>
        </div>
        <div class="fg">
          <label class="flbl">Vendas Canceladas</label>
          <input type="number" class="fi" id="edit-seller-sales-canceled" placeholder="01"/>
        </div>
      </div>
      <div class="fr">
        <div class="fg">
          <label class="flbl">Tempo de Despacho</label>
          <input type="text" class="fi" id="edit-seller-dispatch-time" placeholder="03 horas"/>
        </div>
        <div class="fg">
          <label class="flbl">Nº de Avaliações</label>
          <input type="number" class="fi" id="edit-seller-reviews" placeholder="23"/>
        </div>
      </div>

      <div class="sec-ttl" style="margin:12px 0 8px;font-size:12px">
        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" width="14" height="14"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        Verificações do Vendedor
      </div>
      <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:14px;margin-bottom:12px">
        <div class="tgl-wrap" style="padding:4px 0">
          <div class="tgl-info"><div class="tgl-name" style="font-size:12px">E-mail Verificado</div></div>
          <label class="tgl"><input type="checkbox" id="edit-seller-email-verified" checked /><span class="tgl-sl"></span></label>
        </div>
        <div class="tgl-wrap" style="padding:4px 0">
          <div class="tgl-info"><div class="tgl-name" style="font-size:12px">Telefone Verificado</div></div>
          <label class="tgl"><input type="checkbox" id="edit-seller-phone-verified" checked /><span class="tgl-sl"></span></label>
        </div>
        <div class="tgl-wrap" style="padding:4px 0">
          <div class="tgl-info"><div class="tgl-name" style="font-size:12px">Identidade Verificada</div></div>
          <label class="tgl"><input type="checkbox" id="edit-seller-id-verified" checked /><span class="tgl-sl"></span></label>
        </div>
        <div class="tgl-wrap" style="padding:4px 0">
          <div class="tgl-info"><div class="tgl-name" style="font-size:12px">Facebook Vinculado</div></div>
          <label class="tgl"><input type="checkbox" id="edit-seller-fb-verified" onchange="toggleFbUrl()" /><span class="tgl-sl"></span></label>
        </div>
        <div class="fg" id="wrap-fb-url" style="display:none;margin-top:10px">
          <label class="flbl">Link do Perfil do Facebook *</label>
          <input type="url" class="fi" id="edit-seller-fb-url" placeholder="https://facebook.com/..."/>
        </div>
        <script>
          function toggleFbUrl() {
            var fbCheck = document.getElementById('edit-seller-fb-verified');
            var fbWrap = document.getElementById('wrap-fb-url');
            if(fbCheck && fbWrap) {
              if(fbCheck.checked) {
                fbWrap.style.display = 'flex';
              } else {
                fbWrap.style.display = 'none';
              }
            }
          }
        </script>
      </div>
'''

txt = txt.replace(
    '''<div class="fg">
          <label class="flbl">Data de Entrada</label>
          <input type="text" class="fi" id="edit-seller-since" placeholder="Ex: Setembro 2021"/>
        </div>
      </div>''',
    '''<div class="fg">
          <label class="flbl">Data de Entrada</label>
          <input type="text" class="fi" id="edit-seller-since" placeholder="Ex: Setembro 2021"/>
        </div>
      </div>''' + html_add
)

# And inject API check for fb URL
fb_check = '''
  if(document.getElementById('edit-seller-fb-verified') && document.getElementById('edit-seller-fb-verified').checked) {
    if(!document.getElementById('edit-seller-fb-url').value.trim()) {
      toast('Insira o link do Facebook válido.', 'err');
      return;
    }
  }
'''
txt = txt.replace(
    "if(!name||!price){toast('Nome e Preço são obrigatórios.','err');return;}",
    "if(!name||!price){toast('Nome e Preço são obrigatórios.','err');return;}\n" + fb_check
)

# For ViaCEP, LO asked for "validação inteligente de cep e automatico mostrando resultado preciso do cep". 
# The modal has a Breadcrumb field. I will add a CEP field right before the "Zona / Bairro" or Breadcrumb.

cep_html = '''
      <div class="fr">
        <div class="fg" style="position:relative">
          <label class="flbl">CEP</label>
          <input type="text" class="fi" id="edit-cep" placeholder="00000-000" maxlength="9" oninput="maskCEP(this)" onblur="searchCEP(this.value)" />
          <div id="cep-loader" class="spin" style="display:none;position:absolute;right:14px;top:32px;border-width:2px;border-top-color:#8B5CF6;width:14px;height:14px"></div>
        </div>
        <div class="fg">
          <label class="flbl">Bairro/Zona Automático</label>
          <input type="text" class="fi" id="edit-cep-neighborhood" readonly style="opacity:0.7"/>
        </div>
      </div>
      <div class="fr">
        <div class="fg">
          <label class="flbl">Cidade Automático</label>
          <input type="text" class="fi" id="edit-cep-city" readonly style="opacity:0.7"/>
        </div>
        <div class="fg">
          <label class="flbl">Estado Automático</label>
          <input type="text" class="fi" id="edit-cep-state" readonly style="opacity:0.7"/>
        </div>
      </div>
      <script>
        function maskCEP(inp){
            let v = inp.value.replace(/\\D/g, '');
            if(v.length > 5) v = v.replace(/^(\\d{5})(\\d)/, "$1-$2");
            inp.value = v;
        }
        async function searchCEP(cep){
            cep = cep.replace(/\\D/g, '');
            if(cep.length !== 8) return;
            document.getElementById('cep-loader').style.display = 'inline-block';
            try {
                const r = await fetch('https://viacep.com.br/ws/'+cep+'/json/');
                const d = await r.json();
                if(!d.erro){
                    document.getElementById('edit-cep-neighborhood').value = d.bairro || '';
                    document.getElementById('edit-cep-city').value = d.localidade || '';
                    document.getElementById('edit-cep-state').value = d.uf || '';
                    // Populate breadcrumb custom automatically
                    const bZone = document.getElementById('edit-breadcrumb-zone');
                    if(bZone) {
                        bZone.value = d.bairro || d.localidade;
                        // Forca modo personalizado
                        _locIsDefault = false;
                        const btn = document.getElementById('loc-default-btn');
                        if(btn) btn.classList.add('is-custom');
                        document.getElementById('loc-custom-wrap').style.display = 'block';
                        document.getElementById('loc-default-txt').textContent = 'Personalizado';
                        updateLocPreview(bZone.value);
                    }
                } else {
                    toast('CEP não encontrado', 'err');
                }
            }catch(e){
                console.log(e);
            }
            document.getElementById('cep-loader').style.display = 'none';
        }
      </script>
'''

txt = txt.replace(
    '<!-- Breadcrumb preview strip -->',
    cep_html + '\n<!-- Breadcrumb preview strip -->'
)


with open(r'd:\OLPG\templates\admin.html', 'w', encoding='utf8') as f:
    f.write(txt)
