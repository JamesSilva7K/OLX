import re
import sys

with open('templates/admin.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Add AI button to the UI
ai_button_html = '''<label class="flbl" style="display:flex; justify-content:space-between; align-items:center;">
          <span>Descrição do Produto</span>
          <button type="button" onclick="generateAIDesc()" style="background: linear-gradient(135deg, #8B5CF6, #EC4899); border: none; padding: 4px 10px; border-radius: 6px; color: #fff; font-size: 10px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 4px; box-shadow: 0 2px 8px rgba(139,92,246,0.3); transition: transform 0.15s ease;" onmousedown="this.style.transform='scale(0.95)'" onmouseup="this.style.transform='scale(1)'">
            <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            Gerar com IA
          </button>
        </label>'''

html = re.sub(r'<label class="flbl">Descri.*?</label>', ai_button_html, html, flags=re.DOTALL, count=1)

# Add the JS function
ai_js = '''
async function generateAIDesc() {
    const nameInput = document.getElementById('edit-name');
    const priceInput = document.getElementById('edit-price');
    const oldpInput = document.getElementById('edit-oldp');
    const descInput = document.getElementById('edit-desc');
    
    if (!nameInput.value.trim()) {
        toast('Digite o nome do produto primeiro para a IA entender!', 'err');
        return;
    }
    
    // Animate button
    descInput.value = "Gerando descrição inteligentemente...";
    descInput.style.opacity = "0.7";
    
    try {
        const r = await apiFetch('/api/admin/ai/generate-desc', {
            method: 'POST',
            body: JSON.stringify({
                name: nameInput.value.trim(),
                price: priceInput.value.trim(),
                old_price: oldpInput.value.trim()
            })
        });
        const d = await r.json();
        
        if (d.ok) {
            descInput.value = d.description;
            toast('Descrição gerada com sucesso!', 'ok');
        } else {
            descInput.value = "";
            toast(d.error || 'Erro ao gerar', 'err');
        }
    } catch(e) {
        descInput.value = "";
        toast('Falha de conexão com IA', 'err');
    }
    descInput.style.opacity = "1";
}
'''
if 'function generateAIDesc' not in html:
    html = html.replace('function renderProducts', ai_js + '\nfunction renderProducts')

with open('templates/admin.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('UI Enhanced with AI Button!')
