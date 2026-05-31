"""Registro de migrações de schema do banco de dados.

Regras:
  - SCHEMA_VERSION_ATUAL deve ser incrementado a cada nova migração adicionada.
  - Jamais alterar ou remover uma entrada já publicada em MIGRATIONS.
  - Cada valor pode conter múltiplos statements separados por ';'.
  - Documentar cada migração no CHANGELOG.md antes de publicar.
"""

# Versão de schema que o código atual espera encontrar no banco.
SCHEMA_VERSION_ATUAL: int = 1

# Chave = versão de destino | Valor = SQL a aplicar.
MIGRATIONS: dict[int, str] = {
    # Exemplo de como adicionar uma migração futura:
    # 2: "ALTER TABLE atividades ADD COLUMN origem TEXT;",
}
