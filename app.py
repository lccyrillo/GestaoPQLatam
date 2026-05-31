"""GestaoPQLatam — Servidor Flask principal."""

import os
import sys
import json
import threading
import webbrowser
from datetime import date, datetime
import psutil
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

import database as db
import calculadora as calc

_IS_FROZEN = getattr(sys, 'frozen', False)

# Porta: 5001 no executável distribuído, 5000 no ambiente de desenvolvimento.
PORT = 5001 if _IS_FROZEN else 5000

# Quando empacotado pelo PyInstaller, os templates ficam em sys._MEIPASS/templates.
if _IS_FROZEN:
    _TEMPLATE_DIR = os.path.join(sys._MEIPASS, 'templates')
else:
    _TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')


def encerrar_instancias_anteriores():
    """Encerra outros processos do mesmo executável antes de subir o servidor."""
    if not _IS_FROZEN:
        return
    exe_atual = sys.executable
    pid_atual = os.getpid()
    for proc in psutil.process_iter(['pid', 'exe']):
        try:
            if proc.info['pid'] != pid_atual and proc.info['exe'] == exe_atual:
                proc.terminate()
                proc.wait(timeout=3)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            pass


encerrar_instancias_anteriores()

app = Flask(__name__, template_folder=_TEMPLATE_DIR)
app.secret_key = 'gestaopqlatam-2025'

APP_VERSAO = '1.06'

db.init_db()
db.aplicar_migracoes()


@app.context_processor
def inject_footer():
    return {
        'app_versao': APP_VERSAO,
        'app_ambiente': 'Produção' if _IS_FROZEN else 'Desenvolvimento',
        'app_db_path': db.DB_PATH,
    }

ANOS_DISPONIVEIS = list(range(2024, date.today().year + 2))
ANO_ATUAL = date.today().year

TIPOS_ATIVIDADE = {
    'voo': 'Voo',
    'aluguel_carro': 'Aluguel de Carro',
    'clube': 'Clube LATAM',
    'seguro': 'Seguro Viagem',
    'hospedagem': 'Hospedagem',
    'cartao_itau': 'Cartão de Crédito Itaú',
    'cartao_nubank': 'Cartão de Crédito Nubank',
    'bonificacao': 'Bonificação Extra',
}

STATUS_LABEL = {
    'pendente': ('warning', 'Pendente'),
    'confirmado': ('success', 'Confirmado'),
}


# ── Helpers de template ───────────────────────────────────────────────────────

@app.template_filter('fmt_pq')
def fmt_pq(valor):
    if valor is None:
        return '—'
    return f'{valor:,.0f}'.replace(',', '.')


@app.template_filter('fmt_data')
def fmt_data(valor):
    if not valor:
        return '—'
    try:
        return datetime.strptime(str(valor), '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return str(valor)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    ano = request.args.get('ano', ANO_ATUAL, type=int)
    totais = db.totais_extrato(ano)
    categorias = calc.progresso_categorias(totais['total_estimado'])
    recentes = db.listar_atividades(ano=ano)[:8]
    return render_template(
        'dashboard.html',
        totais=totais,
        categorias=categorias,
        recentes=recentes,
        ano=ano,
        anos=ANOS_DISPONIVEIS,
        tipos=TIPOS_ATIVIDADE,
        status_label=STATUS_LABEL,
    )


# ── Cartões ───────────────────────────────────────────────────────────────────

@app.route('/cartoes')
def cartoes():
    lista = db.listar_cartoes()
    ativ_count = {c['id']: db.contar_atividades_cartao(c['id']) for c in lista}
    return render_template(
        'cartoes.html',
        cartoes=lista,
        tipos_cartao=calc.NOME_TIPO_CARTAO,
        limites=calc.LIMITE_ANUAL_CARTAO,
        ativ_count=ativ_count,
    )


@app.route('/cartoes/novo', methods=['GET', 'POST'])
def cartao_novo():
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        tipo = request.form['tipo']
        ativo = 1 if request.form.get('ativo') else 0
        if not nome:
            flash('Nome do cartão é obrigatório.', 'danger')
            return redirect(url_for('cartao_novo'))
        db.salvar_cartao(nome, tipo, ativo)
        flash('Cartão cadastrado com sucesso.', 'success')
        return redirect(url_for('cartoes'))
    return render_template('cartao_form.html', cartao=None, tipos_cartao=calc.NOME_TIPO_CARTAO)


@app.route('/cartoes/<int:cid>/editar', methods=['GET', 'POST'])
def cartao_editar(cid):
    cartao = db.obter_cartao(cid)
    if not cartao:
        flash('Cartão não encontrado.', 'danger')
        return redirect(url_for('cartoes'))
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        tipo = request.form['tipo']
        ativo = 1 if request.form.get('ativo') else 0
        if not nome:
            flash('Nome do cartão é obrigatório.', 'danger')
            return redirect(url_for('cartao_editar', cid=cid))
        db.salvar_cartao(nome, tipo, ativo, cartao_id=cid)
        flash('Cartão atualizado.', 'success')
        return redirect(url_for('cartoes'))
    return render_template('cartao_form.html', cartao=cartao, tipos_cartao=calc.NOME_TIPO_CARTAO)


@app.route('/cartoes/<int:cid>/excluir', methods=['POST'])
def cartao_excluir(cid):
    num_ativ = db.contar_atividades_cartao(cid)
    force = request.form.get('force') == '1'
    if num_ativ > 0 and not force:
        flash(
            f'Este cartão possui {num_ativ} atividade(s) vinculada(s). '
            'Use o botão de exclusão na página para confirmar — todas as atividades serão apagadas.',
            'danger'
        )
        return redirect(url_for('cartoes'))
    db.excluir_cartao(cid)
    if num_ativ > 0:
        flash(f'Cartão e {num_ativ} atividade(s) vinculada(s) removidos.', 'success')
    else:
        flash('Cartão removido.', 'success')
    return redirect(url_for('cartoes'))


# ── Clube LATAM ───────────────────────────────────────────────────────────────

@app.route('/clube')
def clube():
    historico = db.listar_clube()
    return render_template(
        'clube.html',
        historico=historico,
        planos=calc.NOME_PLANO_CLUBE,
        pqs_por_plano=calc.PQ_CLUBE_MENSAL,
    )


@app.route('/clube/novo', methods=['GET', 'POST'])
def clube_novo():
    if request.method == 'POST':
        plano = request.form['plano']
        data_inicio = request.form['data_inicio']
        data_fim = request.form.get('data_fim') or None
        ativo = 1 if request.form.get('ativo') else 0
        if not data_inicio:
            flash('Data de início é obrigatória.', 'danger')
            return redirect(url_for('clube_novo'))
        db.salvar_clube(plano, data_inicio, data_fim, ativo)
        flash('Assinatura do Clube LATAM registrada.', 'success')
        return redirect(url_for('clube'))
    return render_template('clube_form.html', reg=None, planos=calc.NOME_PLANO_CLUBE,
                           pqs_por_plano=calc.PQ_CLUBE_MENSAL)


@app.route('/clube/<int:rid>/editar', methods=['GET', 'POST'])
def clube_editar(rid):
    historico = db.listar_clube()
    reg = next((r for r in historico if r['id'] == rid), None)
    if not reg:
        flash('Registro não encontrado.', 'danger')
        return redirect(url_for('clube'))
    if request.method == 'POST':
        plano = request.form['plano']
        data_inicio = request.form['data_inicio']
        data_fim = request.form.get('data_fim') or None
        ativo = 1 if request.form.get('ativo') else 0
        db.salvar_clube(plano, data_inicio, data_fim, ativo, clube_id=rid)
        flash('Registro atualizado.', 'success')
        return redirect(url_for('clube'))
    return render_template('clube_form.html', reg=reg, planos=calc.NOME_PLANO_CLUBE,
                           pqs_por_plano=calc.PQ_CLUBE_MENSAL)


@app.route('/clube/<int:rid>/excluir', methods=['POST'])
def clube_excluir(rid):
    db.excluir_clube(rid)
    flash('Registro removido.', 'success')
    return redirect(url_for('clube'))


# ── Atividades ────────────────────────────────────────────────────────────────

@app.route('/atividades')
def atividades_lista():
    ano = request.args.get('ano', ANO_ATUAL, type=int)
    tipo = request.args.get('tipo', '')
    status = request.args.get('status', '')
    lista = db.listar_atividades(
        ano=ano,
        tipo=tipo or None,
        status=status or None,
    )
    return render_template(
        'atividades_lista.html',
        atividades=lista,
        ano=ano,
        anos=ANOS_DISPONIVEIS,
        tipo_filtro=tipo,
        status_filtro=status,
        tipos=TIPOS_ATIVIDADE,
        status_label=STATUS_LABEL,
    )


@app.route('/atividades/nova', methods=['GET', 'POST'])
def atividade_nova():
    todos_cartoes = db.listar_cartoes(apenas_ativos=True)
    cartoes_itau  = [c for c in todos_cartoes if c['tipo'] in calc.CARTOES_ITAU]
    cartoes_nubank = [c for c in todos_cartoes if c['tipo'] in calc.CARTOES_NUBANK]
    cartoes = todos_cartoes  # compat retroativa
    clube_ativo = db.obter_clube_ativo()

    if request.method == 'POST':
        tipo = request.form['tipo']
        data_atividade = request.form.get('data_atividade', '')
        ano_ativ = int(data_atividade[:4]) if data_atividade else ANO_ATUAL

        dados = {}
        pq_estimado = 0.0
        descricao = ''
        cartao_id = None

        if tipo == 'voo':
            tipo_voo = request.form['tipo_voo']
            valor_tarifa_brl = float(request.form.get('valor_tarifa') or 0)
            cotacao_voo = float(request.form.get('cotacao_voo') or 0)
            num_pernas = int(request.form.get('num_pernas') or 0)

            # Validação da soma dos percentuais
            total_pct = sum(
                float(request.form.get(f'perna_percentual_{i}') or 0)
                for i in range(num_pernas)
            )
            if num_pernas == 0 or abs(total_pct - 100) > 0.5:
                flash(f'A soma dos percentuais das pernas deve ser 100% (atual: {total_pct:.1f}%).', 'danger')
                return redirect(url_for('atividade_nova'))

            total_pq = 0.0
            n_registros = 0

            for i in range(num_pernas):
                data_perna  = request.form.get(f'perna_data_{i}', data_atividade)
                desc_perna  = request.form.get(f'perna_descricao_{i}', '').strip()
                pct         = float(request.form.get(f'perna_percentual_{i}') or 0)
                classe      = request.form.get(f'perna_classe_{i}', '')
                bonus_50    = request.form.get(f'perna_bonus_{i}') == '1'

                valor_perna_brl = valor_tarifa_brl * (pct / 100)
                label_perna = f'Perna {i+1}/{num_pernas} — ' if num_pernas > 1 else ''

                if tipo_voo == 'internacional':
                    valor_perna_usd = valor_perna_brl / cotacao_voo if cotacao_voo > 0 else 0
                    pq_perna, milhas = calc.calcular_pq_voo(tipo_voo, valor_perna_usd, classe, False)
                    desc_val = f'R$ {valor_perna_brl:,.2f} (US$ {valor_perna_usd:,.2f})'
                    dados_perna = {
                        'tipo_voo': tipo_voo,
                        'valor_tarifa_total_brl': valor_tarifa_brl,
                        'cotacao_voo': cotacao_voo,
                        'valor_tarifa_total_usd': round(valor_tarifa_brl / cotacao_voo, 2) if cotacao_voo else 0,
                        'percentual_perna': pct,
                        'valor_perna_brl': round(valor_perna_brl, 2),
                        'valor_perna_usd': round(valor_perna_usd, 2),
                        'classe': classe,
                        'milhas_estimadas': milhas,
                        'perna_num': i + 1,
                        'total_pernas': num_pernas,
                    }
                else:
                    pq_perna, milhas = calc.calcular_pq_voo(tipo_voo, valor_perna_brl, classe, False)
                    desc_val = f'R$ {valor_perna_brl:,.2f}'
                    dados_perna = {
                        'tipo_voo': tipo_voo,
                        'valor_tarifa_total_brl': valor_tarifa_brl,
                        'percentual_perna': pct,
                        'valor_perna_brl': round(valor_perna_brl, 2),
                        'classe': classe,
                        'milhas_estimadas': milhas,
                        'perna_num': i + 1,
                        'total_pernas': num_pernas,
                    }

                descricao_perna = (
                    f'Voo — {label_perna}{desc_perna} ({desc_val})'
                    if desc_perna else
                    f'Voo — {label_perna}({desc_val})'
                )
                db.criar_atividade('voo', descricao_perna, data_perna, pq_perna, dados_perna, None)
                total_pq += pq_perna
                n_registros += 1

                if bonus_50:
                    pq_bonus = round(pq_perna * 0.5, 2)
                    dados_bonus = {**dados_perna, 'is_bonus': True}
                    db.criar_atividade('voo', f'{descricao_perna} — Bônus 50%',
                                       data_perna, pq_bonus, dados_bonus, None)
                    total_pq += pq_bonus
                    n_registros += 1

            flash(f'{n_registros} registro(s) criado(s): {total_pq:,.0f} PQs estimados no total.', 'success')
            return redirect(url_for('atividades_lista'))

        elif tipo == 'aluguel_carro':
            empresa = request.form.get('empresa', '').strip()
            valor_brl = float(request.form.get('valor_brl_carro') or 0)
            cotacao = float(request.form.get('cotacao_carro') or 0)
            valor_usd = valor_brl / cotacao if cotacao > 0 else 0
            pq_estimado = calc.calcular_pq_aluguel_carro(valor_usd)
            dados = {'empresa': empresa, 'valor_brl': valor_brl, 'cotacao': cotacao, 'valor_usd': round(valor_usd, 2)}
            descricao = f'Aluguel de carro — {empresa or "Parceiro"} (R$ {valor_brl:,.2f} / US$ {valor_usd:,.2f})'

        elif tipo == 'clube':
            mes = int(request.form['mes_clube'])
            ano_ref = int(request.form['ano_ref_clube'])
            plano_usado = request.form.get('plano_clube', '')
            pq_estimado = calc.calcular_pq_clube(plano_usado)
            dados = {'mes': mes, 'ano': ano_ref, 'plano': plano_usado}
            descricao = (f'Clube LATAM — {calc.NOME_PLANO_CLUBE.get(plano_usado, plano_usado)} '
                         f'{mes:02d}/{ano_ref}')

        elif tipo == 'seguro':
            valor_brl = float(request.form.get('valor_brl_seguro') or 0)
            cotacao = float(request.form.get('cotacao_seguro') or 0)
            valor_usd = valor_brl / cotacao if cotacao > 0 else 0
            cobertura_inicio = request.form.get('cobertura_inicio', '')
            cobertura_fim = request.form.get('cobertura_fim', '')
            pq_estimado = calc.calcular_pq_seguro(valor_usd)
            dados = {'valor_brl': valor_brl, 'cotacao': cotacao, 'valor_usd': round(valor_usd, 2),
                     'cobertura_inicio': cobertura_inicio, 'cobertura_fim': cobertura_fim}
            descricao = f'Seguro viagem (R$ {valor_brl:,.2f} / US$ {valor_usd:,.2f})'

        elif tipo == 'hospedagem':
            hotel = request.form.get('hotel', '').strip()
            valor_brl = float(request.form.get('valor_brl_hosp') or 0)
            cotacao = float(request.form.get('cotacao_hosp') or 0)
            valor_usd = valor_brl / cotacao if cotacao > 0 else 0
            checkin = request.form.get('checkin', '')
            checkout = request.form.get('checkout', '')
            pq_estimado = calc.calcular_pq_hospedagem(valor_usd)
            dados = {'hotel': hotel, 'valor_brl': valor_brl, 'cotacao': cotacao,
                     'valor_usd': round(valor_usd, 2), 'checkin': checkin, 'checkout': checkout}
            descricao = f'Hospedagem — {hotel or "Hotel"} (R$ {valor_brl:,.2f} / US$ {valor_usd:,.2f})'

        elif tipo == 'cartao_itau':
            if not request.form.get('cartao_id'):
                flash('Nenhum cartão cadastrado. Cadastre um cartão antes de lançar esta atividade.', 'danger')
                return redirect(url_for('atividade_nova'))
            cartao_id = int(request.form['cartao_id'])
            valor_brl = float(request.form.get('valor_brl') or 0)
            cotacao_dolar = float(request.form.get('cotacao_dolar') or 1)
            local_compra = request.form.get('local_compra', 'brasil')
            mes = int(request.form.get('mes') or ANO_ATUAL)
            ano_ref = int(request.form.get('ano_ref') or ANO_ATUAL)
            cartao = db.obter_cartao(cartao_id)
            pq_acumulado = db.pq_cartao_no_ano(cartao_id, ano_ref)
            resultado = calc.calcular_pq_cartao(
                cartao['tipo'], valor_brl, cotacao_dolar, local_compra, pq_acumulado
            )
            pq_estimado = resultado['pq_efetivo']
            local_label = 'Exterior' if local_compra == 'exterior' else 'Brasil'
            dados = {
                'valor_brl': valor_brl, 'cotacao_dolar': cotacao_dolar,
                'valor_usd': resultado['valor_usd'], 'local_compra': local_compra,
                'mes': mes, 'ano': ano_ref, 'tipo_cartao': cartao['tipo'],
                'taxa_milhas': resultado['taxa_milhas'],
                'milhas': resultado['milhas'],
                'pq_bruto': resultado['pq_bruto'],
                'limite_anual': resultado['limite_anual'],
                'ja_acumulado': resultado['ja_acumulado'],
            }
            descricao = (f'Cartão {cartao["nome"]} — R$ {valor_brl:,.2f} '
                         f'(US$ {resultado["valor_usd"]:,.2f} · {local_label}) '
                         f'{mes:02d}/{ano_ref}')

        elif tipo == 'cartao_nubank':
            if not request.form.get('cartao_id_nubank'):
                flash('Nenhum cartão Nubank cadastrado. Cadastre um cartão antes de lançar esta atividade.', 'danger')
                return redirect(url_for('atividade_nova'))
            cartao_id = int(request.form['cartao_id_nubank'])
            valor_brl = float(request.form.get('valor_brl_nubank') or 0)
            cotacao_dolar = float(request.form.get('cotacao_dolar_nubank') or 1)
            local_compra = request.form.get('local_compra_nubank', 'regular')
            mes = int(request.form.get('mes_nubank') or ANO_ATUAL)
            ano_ref = int(request.form.get('ano_ref_nubank') or ANO_ATUAL)
            cartao = db.obter_cartao(cartao_id)
            pq_acumulado = db.pq_cartao_no_ano(cartao_id, ano_ref)
            resultado = calc.calcular_pq_cartao(
                cartao['tipo'], valor_brl, cotacao_dolar, local_compra, pq_acumulado
            )
            pq_estimado = resultado['pq_efetivo']
            local_label = 'Nu Viagens' if local_compra == 'nu_viagens' else 'Compra Regular'
            dados = {
                'valor_brl': valor_brl, 'cotacao_dolar': cotacao_dolar,
                'valor_usd': resultado['valor_usd'], 'local_compra': local_compra,
                'mes': mes, 'ano': ano_ref, 'tipo_cartao': cartao['tipo'],
                'taxa_milhas': resultado['taxa_milhas'],
                'milhas': resultado['milhas'],
                'pq_bruto': resultado['pq_bruto'],
                'limite_anual': resultado['limite_anual'],
                'ja_acumulado': resultado['ja_acumulado'],
            }
            descricao = (f'Cartão {cartao["nome"]} — R$ {valor_brl:,.2f} '
                         f'(US$ {resultado["valor_usd"]:,.2f} · {local_label}) '
                         f'{mes:02d}/{ano_ref}')

        elif tipo == 'bonificacao':
            descricao_manual = request.form.get('descricao_manual', '').strip()
            pq_manual = float(request.form['pq_manual'] or 0)
            pq_estimado = pq_manual
            dados = {'pq_manual': pq_manual}
            descricao = descricao_manual or 'Bonificação extra'

        db.criar_atividade(tipo, descricao, data_atividade, pq_estimado, dados, cartao_id)
        flash(f'Atividade registrada: {pq_estimado:,.0f} PQs estimados.', 'success')
        return redirect(url_for('atividades_lista'))

    return render_template(
        'atividades_lancar.html',
        tipos=TIPOS_ATIVIDADE,
        cartoes=cartoes,
        cartoes_itau=cartoes_itau,
        cartoes_nubank=cartoes_nubank,
        clube_ativo=clube_ativo,
        planos=calc.NOME_PLANO_CLUBE,
        pqs_clube=calc.PQ_CLUBE_MENSAL,
        ano_atual=ANO_ATUAL,
        classes_dom={
            'light': 'Light',
            'plus': 'Plus',
            'top_full': 'Top / Full Economy',
            'premium_economy': 'Premium Economy',
            'premium_business': 'Premium Business',
        },
        classes_int={
            'economy_light_plus': 'Economy Light/Plus',
            'economy_full': 'Economy Full',
            'premium_economy': 'Premium Economy',
            'premium_business': 'Premium Business',
        },
        tarifas_bonus_dom=list(calc.TARIFAS_BONUS_DOMESTICO),
        tarifas_bonus_int=list(calc.TARIFAS_BONUS_INTERNACIONAL),
    )


@app.route('/atividades/<int:aid>/validar', methods=['GET', 'POST'])
def atividade_validar(aid):
    ativ = db.obter_atividade(aid)
    if not ativ:
        flash('Atividade não encontrada.', 'danger')
        return redirect(url_for('atividades_lista'))
    if request.method == 'POST':
        pq_conf = float(request.form['pq_confirmado'] or 0)
        db.validar_atividade(aid, pq_conf)
        flash('Atividade confirmada com sucesso.', 'success')
        return redirect(url_for('atividades_lista'))
    return render_template(
        'atividades_validar.html',
        ativ=ativ,
        tipos=TIPOS_ATIVIDADE,
    )


@app.route('/atividades/<int:aid>/excluir', methods=['POST'])
def atividade_excluir(aid):
    db.excluir_atividade(aid)
    flash('Atividade removida.', 'success')
    return redirect(url_for('atividades_lista'))


# ── Extrato ───────────────────────────────────────────────────────────────────

@app.route('/extrato')
def extrato():
    ano = request.args.get('ano', ANO_ATUAL, type=int)
    atividades = db.listar_atividades(ano=ano)
    totais = db.totais_extrato(ano)
    categorias = calc.progresso_categorias(totais['total_estimado'])

    por_tipo = {}
    for a in atividades:
        t = a['tipo']
        if t not in por_tipo:
            por_tipo[t] = {'estimado': 0, 'confirmado': 0, 'count': 0}
        por_tipo[t]['estimado'] += a['pq_estimado']
        if a['status'] == 'confirmado':
            por_tipo[t]['confirmado'] += (a['pq_confirmado'] or 0)
        por_tipo[t]['count'] += 1

    return render_template(
        'extrato.html',
        atividades=atividades,
        totais=totais,
        categorias=categorias,
        por_tipo=por_tipo,
        ano=ano,
        anos=ANOS_DISPONIVEIS,
        tipos=TIPOS_ATIVIDADE,
        status_label=STATUS_LABEL,
    )


# ── API para cálculo dinâmico (AJAX) ─────────────────────────────────────────

@app.route('/api/calcular-pq-cartao')
def api_calcular_pq_cartao():
    cartao_id = request.args.get('cartao_id', type=int)
    valor_brl = request.args.get('valor_brl', type=float, default=0)
    cotacao = request.args.get('cotacao', type=float, default=1)
    local_compra = request.args.get('local_compra', default='brasil')
    ano = request.args.get('ano', type=int, default=ANO_ATUAL)
    if not cartao_id:
        return jsonify({'erro': 'cartao_id obrigatório'})
    if cotacao <= 0:
        return jsonify({'erro': 'Cotação inválida'})
    cartao = db.obter_cartao(cartao_id)
    if not cartao:
        return jsonify({'erro': 'Cartão não encontrado'})
    acumulado = db.pq_cartao_no_ano(cartao_id, ano)
    resultado = calc.calcular_pq_cartao(cartao['tipo'], valor_brl, cotacao, local_compra, acumulado)
    return jsonify(resultado)


@app.route('/api/info-clube')
def api_info_clube():
    clube = db.obter_clube_ativo()
    if not clube:
        return jsonify({'ativo': False})
    return jsonify({
        'ativo': True,
        'plano': clube['plano'],
        'nome_plano': calc.NOME_PLANO_CLUBE.get(clube['plano'], clube['plano']),
        'pq_mensal': calc.PQ_CLUBE_MENSAL.get(clube['plano'], 0),
    })


# ── Simulação ─────────────────────────────────────────────────────────────────

# Estado em memória — persiste enquanto o servidor estiver rodando
_sim_items: list = []
_sim_counter: int = 0
_sim_cartao_restante: dict = {}   # cartao_id → pq_restante no ciclo de simulação

_SIM_LABELS = {
    'voo': 'Voo', 'aluguel_carro': 'Aluguel Carro', 'seguro': 'Seguro',
    'hospedagem': 'Hospedagem', 'clube': 'Clube LATAM',
    'cartao_itau': 'Cartão Itaú', 'cartao_nubank': 'Cartão Nubank',
    'bonificacao': 'Bonificação',
}
_SIM_ID_MAP = {'aluguel_carro': 'carro', 'seguro': 'seguro', 'hospedagem': 'hosp'}


def _sim_init_cartao(cartao_id: int) -> float:
    """Retorna o limite restante do cartão na simulação, inicializando se necessário."""
    if cartao_id not in _sim_cartao_restante:
        cartao = db.obter_cartao(cartao_id)
        if not cartao:
            return 0.0
        acumulado = db.pq_cartao_no_ano(cartao_id, ANO_ATUAL)
        limite = calc.LIMITE_ANUAL_CARTAO.get(cartao['tipo'], 0)
        _sim_cartao_restante[cartao_id] = round(max(0.0, limite - acumulado), 2)
    return _sim_cartao_restante[cartao_id]


def _sim_estado():
    pq_simulado = sum(i['pq'] for i in _sim_items)
    # Expõe apenas os campos seguros para o cliente (sem cartao_id interno)
    itens_pub = [
        {k: v for k, v in i.items() if k != '_cartao_id'}
        for i in _sim_items
    ]
    return {'ok': True, 'itens': itens_pub, 'pq_simulado': pq_simulado}


@app.route('/simulacao')
def simulacao():
    ano = ANO_ATUAL
    atividades = db.listar_atividades(ano=ano)
    pq_atual = round(sum(a['pq_estimado'] for a in atividades), 2)

    todos_cartoes_sim = db.listar_cartoes(apenas_ativos=True)
    cartoes_sim = []
    cartoes_itau_sim = []
    cartoes_nubank_sim = []
    for c in todos_cartoes_sim:
        acumulado = db.pq_cartao_no_ano(c['id'], ano)
        limite = calc.LIMITE_ANUAL_CARTAO.get(c['tipo'], 0)
        entry = {
            'id': c['id'],
            'nome': c['nome'],
            'tipo': c['tipo'],
            'pq_acumulado': round(acumulado, 2),
            'limite_anual': limite,
            'pq_restante': round(max(0.0, limite - acumulado), 2),
        }
        cartoes_sim.append(entry)
        if c['tipo'] in calc.CARTOES_ITAU:
            cartoes_itau_sim.append(entry)
        elif c['tipo'] in calc.CARTOES_NUBANK:
            cartoes_nubank_sim.append(entry)

    estado = _sim_estado()
    return render_template(
        'simulacao.html',
        pq_atual=pq_atual,
        ano=ano,
        cartoes_sim=cartoes_sim,
        cartoes_itau_sim=cartoes_itau_sim,
        cartoes_nubank_sim=cartoes_nubank_sim,
        clube_ativo=db.obter_clube_ativo(),
        categorias=calc.CATEGORIAS,
        planos=calc.NOME_PLANO_CLUBE,
        pqs_clube=calc.PQ_CLUBE_MENSAL,
        classes_dom={
            'light': 'Light',
            'plus': 'Plus',
            'top_full': 'Top / Full Economy',
            'premium_economy': 'Premium Economy',
            'premium_business': 'Premium Business',
        },
        classes_int={
            'economy_light_plus': 'Economy Light/Plus',
            'economy_full': 'Economy Full',
            'premium_economy': 'Premium Economy',
            'premium_business': 'Premium Business',
        },
        tarifas_bonus_dom=list(calc.TARIFAS_BONUS_DOMESTICO),
        tarifas_bonus_int=list(calc.TARIFAS_BONUS_INTERNACIONAL),
        milhas_cartao=calc.MILHAS_CARTAO,
        sim_items=estado['itens'],
        pq_simulado=estado['pq_simulado'],
    )


@app.route('/api/simulacao/adicionar', methods=['POST'])
def api_sim_adicionar():
    global _sim_counter
    data = request.get_json() or {}
    tipo = data.get('tipo', '')

    pq = 0.0
    descricao = ''
    item_extra = {}

    try:
        if tipo == 'voo':
            tipo_voo = data.get('tipo_voo', 'domestico')
            valor    = float(data.get('valor') or 0)
            cotacao  = float(data.get('cotacao') or 0)
            classe   = data.get('classe', '')
            bonus    = bool(data.get('bonus', False))
            if valor <= 0:
                return jsonify({'ok': False, 'erro': 'Informe o valor da tarifa.', 'campo': 'sim-voo-valor'})
            if tipo_voo == 'internacional':
                if cotacao <= 0:
                    return jsonify({'ok': False, 'erro': 'Informe a cotação do dólar para voo internacional.', 'campo': 'sim-voo-cotacao'})
                valor_calc = valor / cotacao
            else:
                valor_calc = valor
            pq, _ = calc.calcular_pq_voo(tipo_voo, valor_calc, classe, bonus)
            descricao = f'Voo {"Dom." if tipo_voo == "domestico" else "Int."} R$ {valor:,.2f}'

        elif tipo in ('aluguel_carro', 'seguro', 'hospedagem'):
            valor   = float(data.get('valor') or 0)
            cotacao = float(data.get('cotacao') or 0)
            campo_id = _SIM_ID_MAP[tipo]
            if valor <= 0:
                return jsonify({'ok': False, 'erro': 'Informe o valor em reais.', 'campo': f'sim-{campo_id}-valor'})
            if cotacao <= 0:
                return jsonify({'ok': False, 'erro': 'Informe a cotação do dólar (R$/US$).', 'campo': f'sim-{campo_id}-cotacao'})
            valor_usd = valor / cotacao
            if tipo == 'aluguel_carro':
                pq = calc.calcular_pq_aluguel_carro(valor_usd)
                label = 'Aluguel Carro'
            elif tipo == 'seguro':
                pq = calc.calcular_pq_seguro(valor_usd)
                label = 'Seguro Viagem'
            else:
                pq = calc.calcular_pq_hospedagem(valor_usd)
                label = 'Hospedagem'
            descricao = f'{label} R$ {valor:,.2f}'

        elif tipo == 'clube':
            clube_ativo = db.obter_clube_ativo()
            if not clube_ativo:
                return jsonify({'ok': False, 'erro': 'Nenhuma assinatura ativa do Clube LATAM.'})
            meses = int(data.get('meses') or 0)
            if meses <= 0:
                return jsonify({'ok': False, 'erro': 'Informe quantos meses deseja simular.', 'campo': 'sim-clube-meses'})
            pq_mes = calc.PQ_CLUBE_MENSAL.get(clube_ativo['plano'], 0)
            if not pq_mes:
                return jsonify({'ok': False, 'erro': 'O plano ativo não gera PQs mensais diretamente.'})
            pq = float(pq_mes * meses)
            descricao = f'Clube LATAM — {meses} mês(es)'

        elif tipo in ('cartao_itau', 'cartao_nubank'):
            cartao_id = int(data.get('cartao_id') or 0)
            valor     = float(data.get('valor') or 0)
            cotacao   = float(data.get('cotacao') or 0)
            local     = data.get('local', 'brasil' if tipo == 'cartao_itau' else 'regular')
            if not cartao_id:
                return jsonify({'ok': False, 'erro': 'Selecione um cartão.'})
            if valor <= 0:
                return jsonify({'ok': False, 'erro': 'Informe o valor do gasto.', 'campo': 'sim-cartao-valor'})
            if cotacao <= 0:
                return jsonify({'ok': False, 'erro': 'Informe a cotação do dólar (R$/US$).', 'campo': 'sim-cartao-cotacao'})
            cartao = db.obter_cartao(cartao_id)
            if not cartao:
                return jsonify({'ok': False, 'erro': 'Cartão não encontrado.'})
            restante  = _sim_init_cartao(cartao_id)
            resultado = calc.calcular_pq_cartao(cartao['tipo'], valor, cotacao, local, 0)
            pq = min(float(resultado['pq_efetivo']), restante)
            _sim_cartao_restante[cartao_id] = round(max(0.0, restante - pq), 2)
            if tipo == 'cartao_nubank':
                local_label = 'Nu Viagens' if local == 'nu_viagens' else 'Regular'
            else:
                local_label = 'EXT' if local == 'exterior' else 'BR'
            descricao = f'{cartao["nome"]} R$ {valor:,.2f} ({local_label})'
            item_extra = {'_cartao_id': cartao_id}

        elif tipo == 'bonificacao':
            pq        = float(data.get('pq') or 0)
            descricao = (data.get('descricao') or '').strip() or 'Bonificação extra'
            if pq <= 0:
                return jsonify({'ok': False, 'erro': 'Informe a quantidade de PQs da bonificação.', 'campo': 'sim-bonus-pq'})

        else:
            return jsonify({'ok': False, 'erro': 'Tipo de atividade inválido.'})

    except Exception as e:
        return jsonify({'ok': False, 'erro': f'Erro no cálculo: {e}'})

    if pq <= 0 and tipo != 'bonificacao':
        return jsonify({'ok': False, 'erro': 'O valor informado resultou em 0 PQs. Verifique os campos.'})

    item = {
        'id': _sim_counter,
        'tipo': tipo,
        'label': _SIM_LABELS.get(tipo, tipo),
        'descricao': descricao,
        'pq': round(pq),
        **item_extra,
    }
    _sim_counter += 1
    _sim_items.append(item)
    return jsonify(_sim_estado())


@app.route('/api/simulacao/remover', methods=['POST'])
def api_sim_remover():
    global _sim_items
    item_id = (request.get_json() or {}).get('id')
    item = next((i for i in _sim_items if i['id'] == item_id), None)
    if item and item.get('tipo') in ('cartao_itau', 'cartao_nubank'):
        cid = item.get('_cartao_id')
        if cid is not None and cid in _sim_cartao_restante:
            cartao = db.obter_cartao(cid)
            if cartao:
                acumulado    = db.pq_cartao_no_ano(cid, ANO_ATUAL)
                limite       = calc.LIMITE_ANUAL_CARTAO.get(cartao['tipo'], 0)
                max_restante = round(max(0.0, limite - acumulado), 2)
                _sim_cartao_restante[cid] = min(
                    max_restante, _sim_cartao_restante[cid] + item['pq']
                )
    _sim_items = [i for i in _sim_items if i['id'] != item_id]
    return jsonify(_sim_estado())


@app.route('/api/simulacao/limpar', methods=['POST'])
def api_sim_limpar():
    global _sim_items, _sim_cartao_restante
    _sim_items = []
    _sim_cartao_restante = {}
    return jsonify(_sim_estado())


# ── Console SQL ───────────────────────────────────────────────────────────────

@app.route('/sql-console', methods=['GET', 'POST'])
def sql_console():
    query = ''
    colunas = []
    linhas = []
    erro = None

    conn = db.get_conn()
    tabelas = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    conn.close()

    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if not query:
            erro = 'Digite uma instrução SQL.'
        elif not query.lstrip().upper().startswith('SELECT'):
            erro = 'Apenas instruções SELECT são permitidas.'
        else:
            try:
                conn = db.get_conn()
                cur = conn.execute(query)
                colunas = [d[0] for d in cur.description]
                linhas = [list(row) for row in cur.fetchall()]
                conn.close()
            except Exception as e:
                erro = str(e)

    return render_template('sql_console.html', query=query, colunas=colunas, linhas=linhas, erro=erro, tabelas=tabelas)


# ── Inicialização ─────────────────────────────────────────────────────────────

def abrir_navegador():
    import time
    time.sleep(1)
    webbrowser.open(f'http://127.0.0.1:{PORT}')


if __name__ == '__main__':
    t = threading.Thread(target=abrir_navegador, daemon=True)
    t.start()
    app.run(debug=False, port=PORT)
