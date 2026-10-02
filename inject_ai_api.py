import re

with open('app.py', 'r', encoding='utf-8') as f:
    app_py = f.read()

ai_endpoint = '''
@app.route('/api/admin/ai/generate-desc', methods=['POST'])
def api_admin_ai_generate_desc():
    """Gera uma descrição inteligente de vendas com base no nome do produto."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
         return jsonify({"ok": False, "error": "unauthorized"}), 401
         
    data = request.json or {}
    name = data.get('name', '').strip()
    price = data.get('price', '').strip()
    
    if not name:
        return jsonify({"ok": False, "error": "Nome do produto é obrigatório"}), 400
        
    n_lower = name.lower()
    
    # 1. Identificação da Categoria
    desc = f"**{name}**\\n\\n"
    
    if any(x in n_lower for x in ['iphone', 'galaxy', 'motorola', 'xiaomi', 'smartphone', 'celular']):
        desc += (
            "✅ Aparelho em estado de zero, sem marcas de uso profundas.\\n"
            "✅ Bateria com excelente saúde e autonomia.\\n"
            "✅ Desbloqueado para todas as operadoras.\\n"
            "✅ Acompanha cabo e carregador.\\n\\n"
            "Aparelho todo original, nunca foi aberto. iCloud/Conta limpos. Funciona absolutamente tudo (Face ID/Biometria, câmeras, alto-falantes perfeitos).\\n\\n"
        )
    elif any(x in n_lower for x in ['ps4', 'ps5', 'xbox', 'nintendo', 'playstation', 'console']):
        desc += (
            "✅ Console muito bem conservado, rodando silencioso e sem aquecimento.\\n"
            "✅ Controle original funcionando perfeitamente, sem drift.\\n"
            "✅ Cabos originais inclusos (HDMI e Energia).\\n\\n"
            "Videogame de uso pessoal, higienizado e pronto para jogar. Leitor de discos perfeito e conexão online liberada (sem ban).\\n\\n"
        )
    elif any(x in n_lower for x in ['geladeira', 'fogao', 'fogão', 'maquina', 'máquina', 'tv', 'smart', 'ar condicionado', 'microondas']):
        desc += (
            "✅ Eletrodoméstico seminovo, revisado e funcionando 100%.\\n"
            "✅ Sem ferrugem, estética impecável.\\n"
            "✅ Voltagem padrão.\\n\\n"
            "Ótima oportunidade para quem quer qualidade pagando menos. Pode testar tudo na hora.\\n\\n"
        )
    elif any(x in n_lower for x in ['pc', 'notebook', 'macbook', 'gamer', 'computador']):
        desc += (
            "✅ Máquina super rápida e formatada, pronta para uso.\\n"
            "✅ Ótimo estado de conservação, tela sem riscos ou dead pixels.\\n"
            "✅ Bateria segurando carga perfeitamente.\\n"
            "✅ Fonte/Carregador original incluso.\\n\\n"
            "Excelente para trabalho pesado, estudos ou jogos. Sistema fluido e sem travamentos.\\n\\n"
        )
    elif any(x in n_lower for x in ['carro', 'moto', 'honda', 'yamaha', 'chevrolet', 'fiat', 'volkswagen']):
        desc += (
            "✅ Veículo de procedência, documentação rigorosamente em dia (IPVA pago).\\n"
            "✅ Mecânica revisada, sem vazamentos ou barulhos.\\n"
            "✅ Lataria e pintura em excelente estado.\\n"
            "✅ Pneus novos.\\n\\n"
            "Veículo para pessoas exigentes. Só pegar e transferir. Não aceito trocas absurdas.\\n\\n"
        )
    else:
        desc += (
            "✅ Produto em excelente estado de conservação.\\n"
            "✅ Totalmente testado e funcionando perfeitamente.\\n"
            "✅ Pronto para uso imediato.\\n\\n"
            "Oportunidade única! Item muito bem cuidado, sem defeitos ou detalhes que desabonem. "
            "Excelente custo-benefício comparado ao valor de um novo.\\n\\n"
        )
        
    desc += "Motivo da venda: Precisando do dinheiro / Atualização de equipamento.\\n"
    if price:
        desc += f"Valor: R$ {price} (Aceito cartão, taxas por conta do comprador).\\n"
    desc += "Interessados chamar no chat ou WhatsApp. Golpistas nem percam tempo."
    
    return jsonify({"ok": True, "description": desc})
'''

if '/api/admin/ai/generate-desc' not in app_py:
    # Insert before the run block or after some admin routes
    app_py = app_py.replace('if __name__ == "__main__":', ai_endpoint + '\nif __name__ == "__main__":')
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(app_py)
    print("AI API injected!")
else:
    print("AI API already exists!")
