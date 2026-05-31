# Changelog — GestaoPQLatam

Formato: `## [vX.XX] — AAAA-MM-DD`
Mudanças de schema são marcadas com 🗄️ e incluem o SQL aplicado.

---

## [v1.04] — 2026-05-31

### Alterações
- Exclusão de cartão agora remove também as atividades vinculadas, com confirmação dupla no frontend.
- Adicionada contagem de atividades por cartão na listagem de cartões.
- Correção de bug: exclusão falhava com erro de FK quando o cartão possuía atividades.

### 🗄️ Migração de banco
**Necessária:** Não.
O schema não foi alterado. A tabela `schema_version` é criada automaticamente na primeira
inicialização do executável — sem impacto nos dados existentes.

**Versão de schema:** 1 (baseline — estado inicial do banco)

---

## [v1.03] — 2026-05-XX

### Alterações
- Simulação de PQs via backend (estado em memória no servidor).
- Validação de formulário no frontend.
- APIs REST: `/api/simulacao/adicionar`, `/remover`, `/limpar`.

### 🗄️ Migração de banco
**Necessária:** Não.

---

## [v1.02] — 2026-05-XX

### Alterações
- Página de Simulação de PQs (`/simulacao`).

### 🗄️ Migração de banco
**Necessária:** Não.

---

## [v1.01] — 2026-05-XX

### Alterações
- Versão inicial do sistema.
- Tabelas: `cartoes`, `clube_latam`, `atividades`.

### 🗄️ Migração de banco
**Necessária:** Não (criação inicial).

---

## Como adicionar uma migração futura

1. Incrementar `SCHEMA_VERSION_ATUAL` em `migrations.py`.
2. Adicionar a entrada no dicionário `MIGRATIONS` com o SQL:
   ```python
   MIGRATIONS = {
       2: "ALTER TABLE atividades ADD COLUMN origem TEXT;",
   }
   ```
3. Documentar neste arquivo com o bloco 🗄️, incluindo o SQL.
4. O executável aplica a migração automaticamente na primeira inicialização.
   Em caso de falha, o banco é restaurado ao estado anterior e o app não sobe.
   O log fica em `logs/migration.log` ao lado do executável.
