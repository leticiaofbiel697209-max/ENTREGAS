from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "entregas.db"


def get_connection() -> sqlite3.Connection:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _create_indexes(conn: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        conn.execute(statement)


def init_db() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entregadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS rotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_rota TEXT NOT NULL,
                entregador TEXT NOT NULL,
                veiculo TEXT,
                observacao TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS entregas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rota_id INTEGER NOT NULL,
                venda_id TEXT,
                numero_venda TEXT,
                cliente TEXT NOT NULL,
                telefone TEXT,
                endereco TEXT NOT NULL,
                cidade TEXT,
                estado TEXT,
                cep TEXT,
                status TEXT NOT NULL DEFAULT 'PENDENTE',
                recebido_por TEXT,
                observacao TEXT,
                data_entrega TEXT,
                atualizado_por TEXT,
                api_retorno TEXT,
                origem_pedido TEXT,
                loja_id TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rota_id) REFERENCES rotas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ocorrencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entrega_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                descricao TEXT,
                data_ocorrencia TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                FOREIGN KEY (entrega_id) REFERENCES entregas(id) ON DELETE CASCADE
            );
            """
        )

        # Colunas adicionais mantem o banco simples e viabilizam login e auditoria.
        _add_column_if_missing(conn, "entregadores", "codigo_acesso", "TEXT")
        _add_column_if_missing(conn, "rotas", "entregador_id", "INTEGER")
        _add_column_if_missing(conn, "entregas", "atualizado_por", "TEXT")
        _add_column_if_missing(conn, "entregas", "api_retorno", "TEXT")
        _add_column_if_missing(conn, "entregas", "origem_pedido", "TEXT")
        _add_column_if_missing(conn, "entregas", "loja_id", "TEXT")
        _add_column_if_missing(conn, "ocorrencias", "usuario", "TEXT")

        _create_indexes(
            conn,
            [
                "CREATE INDEX IF NOT EXISTS idx_entregas_status ON entregas(status)",
                "CREATE INDEX IF NOT EXISTS idx_entregas_rota_id ON entregas(rota_id)",
                "CREATE INDEX IF NOT EXISTS idx_rotas_data ON rotas(data_rota)",
                "CREATE INDEX IF NOT EXISTS idx_ocorrencias_entrega ON ocorrencias(entrega_id)",
            ],
        )
        conn.commit()
