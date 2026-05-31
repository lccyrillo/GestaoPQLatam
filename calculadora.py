"""Regras de cálculo de Pontos Qualificáveis do LATAM Pass."""

# --- Tarifas de milhas por tipo de voo ---

MILHAS_DOMESTICO = {
    'light': 5,
    'plus': 6,
    'top_full': 7,
    'premium_economy': 8,
    'premium_business': 10,
}

MILHAS_INTERNACIONAL = {
    'economy_light_plus': 5,
    'economy_full': 7,
    'premium_economy': 9,
    'premium_business': 12,
}

# Tarifas elegíveis para o bônus de +50% (Bônus LATAM Pass)
TARIFAS_BONUS_DOMESTICO = {'top_full', 'premium_economy', 'premium_business'}
TARIFAS_BONUS_INTERNACIONAL = {'economy_full', 'premium_economy', 'premium_business'}

# PQs base por unidade de moeda
PQ_VOO_DOMESTICO = 3.0       # por R$1 de tarifa (sem taxas)
PQ_VOO_INTERNACIONAL = 6.0   # por US$1 de tarifa (sem taxas)
PQ_ALUGUEL_CARRO = 6.0       # por US$1
PQ_SEGURO = 6.0               # por US$1
PQ_HOSPEDAGEM = 6.0           # por US$1
PQ_HOSPEDAGEM_MAX = 30000     # limite por reserva

# Cartão Itaú — milhas por US$1 gasto (gastos em BRL convertidos pela cotação do dia)
# Taxas distintas para compras no Brasil vs no exterior
# Cartão Nubank Ultravioleta — taxas distintas para Regular vs Nu Viagens
MILHAS_CARTAO = {
    'platinum':            {'brasil': 1.5, 'exterior': 2.0},
    'visa_infinite':       {'brasil': 2.5, 'exterior': 3.5},
    'mastercard_black':    {'brasil': 2.5, 'exterior': 3.5},
    'nubank_ultravioleta': {'regular': 2.2, 'nu_viagens': 9.0},
}

# Limite anual de PQs por tipo de cartão
LIMITE_ANUAL_CARTAO = {
    'platinum': 5000,
    'visa_infinite': 9000,
    'mastercard_black': 9000,
    'nubank_ultravioleta': 60000,
}

# Conjuntos para identificar o banco do cartão
CARTOES_ITAU   = frozenset({'platinum', 'visa_infinite', 'mastercard_black'})
CARTOES_NUBANK = frozenset({'nubank_ultravioleta'})

# PQs mensais do Clube LATAM por plano
PQ_CLUBE_MENSAL = {
    'mais': 0,
    'embarque_sem_itau': 500,
    'embarque_com_itau': 750,
    'acelere': 0,
    'turbo': 0,
}

# Nomes legíveis dos tipos de cartão
NOME_TIPO_CARTAO = {
    'platinum':            'Itaú Platinum',
    'visa_infinite':       'Itaú Visa Infinite',
    'mastercard_black':    'Itaú Mastercard Black',
    'nubank_ultravioleta': 'Nubank Ultravioleta',
}

# Nomes legíveis dos planos do clube
NOME_PLANO_CLUBE = {
    'mais': 'Mais',
    'embarque_sem_itau': 'Embarque (sem Itaú)',
    'embarque_com_itau': 'Embarque (com Itaú)',
    'acelere': 'Acelere',
    'turbo': 'Turbo',
}

# Categorias elite e seus limites de PQs
CATEGORIAS = [
    ('Gold', 12000),
    ('Platinum', 35000),
    ('Black', 100000),
    ('Black Signature', 200000),
]


def calcular_pq_voo(tipo, valor_tarifa, classe_tarifaria, bonus_50):
    """Retorna (pq_estimado, milhas_estimadas)."""
    if tipo == 'domestico':
        pq_base = valor_tarifa * PQ_VOO_DOMESTICO
        elegivel_bonus = classe_tarifaria in TARIFAS_BONUS_DOMESTICO
        milhas = valor_tarifa * MILHAS_DOMESTICO.get(classe_tarifaria, 5)
    else:
        pq_base = valor_tarifa * PQ_VOO_INTERNACIONAL
        elegivel_bonus = classe_tarifaria in TARIFAS_BONUS_INTERNACIONAL
        milhas = valor_tarifa * MILHAS_INTERNACIONAL.get(classe_tarifaria, 5)

    pq = pq_base * 1.5 if (bonus_50 and elegivel_bonus) else pq_base
    return round(pq, 2), round(milhas, 2)


def calcular_pq_aluguel_carro(valor_usd):
    return round(valor_usd * PQ_ALUGUEL_CARRO, 2)


def calcular_pq_seguro(valor_usd):
    return round(valor_usd * PQ_SEGURO, 2)


def calcular_pq_hospedagem(valor_usd):
    pq = valor_usd * PQ_HOSPEDAGEM
    return round(min(pq, PQ_HOSPEDAGEM_MAX), 2)


def calcular_pq_cartao(tipo_cartao, valor_brl, cotacao_dolar, local_compra, pq_ja_acumulado_ano):
    """Calcula PQs do cartão respeitando o limite anual.

    O acúmulo é baseado em US$: o valor em BRL é convertido pela cotação informada,
    depois aplica-se a taxa de milhas por US$1 conforme o local da compra.

    Itaú: local_compra = 'brasil' | 'exterior'. Fórmula: (milhas / 10) × 2.
    Nubank Ultravioleta: local_compra = 'regular' | 'nu_viagens'. Fórmula: milhas / 4.
    O bônus de +10% automático do Nubank não conta para PQs e não é aplicado aqui.
    """
    valor_usd = valor_brl / cotacao_dolar
    taxa_milhas = MILHAS_CARTAO[tipo_cartao][local_compra]  # milhas por US$1
    milhas = valor_usd * taxa_milhas
    if tipo_cartao in CARTOES_NUBANK:
        pq_bruto = milhas / 4      # 4 milhas → 1 PQ (bônus 10% não conta)
    else:
        pq_bruto = (milhas / 10) * 2
    limite = LIMITE_ANUAL_CARTAO[tipo_cartao]
    restante = max(0.0, limite - pq_ja_acumulado_ano)
    pq_efetivo = min(pq_bruto, restante)
    return {
        'valor_usd': round(valor_usd, 2),
        'taxa_milhas': taxa_milhas,
        'milhas': round(milhas, 2),
        'pq_bruto': round(pq_bruto, 2),
        'pq_efetivo': round(pq_efetivo, 2),
        'limite_anual': limite,
        'ja_acumulado': round(pq_ja_acumulado_ano, 2),
        'restante': round(restante, 2),
    }


def calcular_pq_clube(plano):
    return PQ_CLUBE_MENSAL.get(plano, 0)


def progresso_categorias(pq_total):
    """Retorna lista de dicts com progresso por categoria."""
    resultado = []
    for nome, meta in CATEGORIAS:
        pct = min(100, round(pq_total / meta * 100, 1)) if meta else 0
        resultado.append({
            'nome': nome,
            'meta': meta,
            'atual': pq_total,
            'percentual': pct,
            'falta': max(0, meta - pq_total),
            'atingida': pq_total >= meta,
        })
    return resultado
