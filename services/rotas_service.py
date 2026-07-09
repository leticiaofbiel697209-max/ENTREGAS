from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import pandas as pd

from services.db import get_connection


STATUS_PENDENTE = "PENDENTE"
STATUS_EM_ROTA = "EM ROTA"
STATUS_ENTREGUE = "ENTREGUE"
STATUS_FALHA = "FALHA"


def get_config(name: str, default: str = "") -> str:
    """Le configuracoes do .env, variaveis do ambiente ou Secrets do Streamlit Cloud."""
    candidates = (name, name.lower())

    value = os.getenv(name) or os.getenv(name.lower())
    if value not in (None, ""):
        return str(value)

    try:
        import streamlit as st

        for candidate in candidates:
            secret_value = st.secrets.get(candidate)
            if secret_value not in (None, ""):
                return str(secret_value)

        # Tambem aceita Secrets agrupados como [admin].
        for group_name in ("admin", "ADMIN"):
            group = st.secrets.get(group_name, {})
            if hasattr(group, "get"):
                for candidate in candidates:
                    grouped_value = group.get(candidate)
                    if grouped_value not in (None, ""):
                        return str(grouped_value)
        return default
    except Exception:
        return default


def autenticar_admin(usuario: str, senha: str) -> bool:
    admin_user = get_config("ADMIN_USER", "admin")
    admin_password = get_config("ADMIN_PASSWORD", "123456")
    return usuario.strip().lower() == admin_user.strip().lower() and bool(senha) and senha == admin_password


def autenticar_entregador(nome: str, codigo: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, nome
            FROM entregadores
            WHERE lower(nome) = lower(?) AND COALESCE(codigo_acesso, '') = ?
            """,
            (nome.strip(), codigo),
        ).fetchone()
    return dict(row) if row else None


def listar_entregadores() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, nome, codigo_acesso FROM entregadores ORDER BY nome").fetchall()
    return [dict(row) for row in rows]


def salvar_entregador(nome: str, codigo_acesso: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO entregadores (nome, codigo_acesso)
            VALUES (?, ?)
            ON CONFLICT(nome) DO UPDATE SET codigo_acesso = excluded.codigo_acesso
            """,
            (nome.strip(), codigo_acesso.strip()),
        )
        conn.commit()


def excluir_entregador(entregador_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM entregadores WHERE id = ?", (entregador_id,))
        conn.commit()


def criar_rota(data_rota: date, entregador_id: int, entregador: str, veiculo: str, observacao: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO rotas (data_rota, entregador_id, entregador, veiculo, observacao)
            VALUES (?, ?, ?, ?, ?)
            """,
            (data_rota.isoformat(), entregador_id, entregador, veiculo.strip(), observacao.strip()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def listar_rotas() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT r.*, COUNT(e.id) AS total_entregas
            FROM rotas r
            LEFT JOIN entregas e ON e.rota_id = r.id
            GROUP BY r.id
            ORDER BY r.data_rota DESC, r.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def adicionar_entrega(rota_id: int, dados: dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO entregas (
                rota_id, venda_id, numero_venda, cliente, telefone, endereco,
                cidade, estado, cep, status, observacao, origem_pedido, loja_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rota_id,
                dados.get("venda_id", "").strip(),
                dados.get("numero_venda", "").strip(),
                dados.get("cliente", "").strip(),
                dados.get("telefone", "").strip(),
                dados.get("endereco", "").strip(),
                dados.get("cidade", "").strip(),
                dados.get("estado", "").strip(),
                dados.get("cep", "").strip(),
                STATUS_EM_ROTA,
                dados.get("observacao", "").strip(),
                dados.get("origem", dados.get("origem_pedido", "")).strip(),
                dados.get("loja_id", "").strip(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def listar_entregas_rota(rota_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.*, r.entregador, r.entregador_id, r.data_rota
            FROM entregas e
            JOIN rotas r ON r.id = e.rota_id
            WHERE e.rota_id = ?
            ORDER BY e.id DESC
            """,
            (rota_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def listar_entregas_entregador(entregador_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.*, r.entregador, r.entregador_id, r.data_rota, r.veiculo
            FROM entregas e
            JOIN rotas r ON r.id = e.rota_id
            WHERE r.entregador_id = ?
              AND e.status IN (?, ?, ?)
            ORDER BY r.data_rota ASC, e.id ASC
            """,
            (entregador_id, STATUS_PENDENTE, STATUS_EM_ROTA, STATUS_FALHA),
        ).fetchall()
    return [dict(row) for row in rows]


def listar_entregas_concluidas_entregador(entregador_id: int, limite: int = 20) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.*, r.entregador, r.entregador_id, r.data_rota, r.veiculo
            FROM entregas e
            JOIN rotas r ON r.id = e.rota_id
            WHERE r.entregador_id = ?
              AND e.status = ?
            ORDER BY e.data_entrega DESC, e.id DESC
            LIMIT ?
            """,
            (entregador_id, STATUS_ENTREGUE, limite),
        ).fetchall()
    return [dict(row) for row in rows]


def obter_entrega(entrega_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT e.*, r.entregador, r.entregador_id, r.data_rota
            FROM entregas e
            JOIN rotas r ON r.id = e.rota_id
            WHERE e.id = ?
            """,
            (entrega_id,),
        ).fetchone()
    return dict(row) if row else None


def atualizar_endereco_entrega(
    entrega_id: int,
    endereco: str,
    cidade: str,
    estado: str,
    cep: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE entregas
            SET endereco = ?, cidade = ?, estado = ?, cep = ?
            WHERE id = ?
            """,
            (endereco.strip(), cidade.strip(), estado.strip(), cep.strip(), entrega_id),
        )
        conn.commit()


def registrar_entrega_concluida(
    entrega_id: int,
    recebido_por: str,
    observacao: str,
    usuario: str,
    api_retorno: str,
) -> None:
    agora = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE entregas
            SET status = ?, recebido_por = ?, observacao = ?, data_entrega = ?,
                atualizado_por = ?, api_retorno = ?
            WHERE id = ?
            """,
            (STATUS_ENTREGUE, recebido_por.strip(), observacao.strip(), agora, usuario, api_retorno, entrega_id),
        )
        conn.execute(
            """
            INSERT INTO ocorrencias (entrega_id, tipo, descricao, data_ocorrencia, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entrega_id, STATUS_ENTREGUE, observacao.strip(), agora, usuario),
        )
        conn.commit()


def registrar_falha(entrega_id: int, motivo: str, observacao: str, usuario: str) -> None:
    agora = datetime.now().isoformat(timespec="seconds")
    descricao = motivo if not observacao else f"{motivo}: {observacao}"
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE entregas
            SET status = ?, observacao = ?, data_entrega = ?, atualizado_por = ?
            WHERE id = ?
            """,
            (STATUS_FALHA, descricao, agora, usuario, entrega_id),
        )
        conn.execute(
            """
            INSERT INTO ocorrencias (entrega_id, tipo, descricao, data_ocorrencia, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entrega_id, STATUS_FALHA, descricao, agora, usuario),
        )
        conn.commit()


def registrar_ocorrencia(entrega_id: int, descricao: str, usuario: str) -> None:
    agora = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ocorrencias (entrega_id, tipo, descricao, data_ocorrencia, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entrega_id, "OCORRENCIA", descricao.strip(), agora, usuario),
        )
        conn.commit()


def indicadores_dashboard() -> dict[str, int]:
    hoje = date.today().isoformat()
    with get_connection() as conn:
        pendentes = conn.execute(
            "SELECT COUNT(*) AS total FROM entregas WHERE status = ?",
            (STATUS_PENDENTE,),
        ).fetchone()["total"]
        em_rota = conn.execute(
            "SELECT COUNT(*) AS total FROM entregas WHERE status = ?",
            (STATUS_EM_ROTA,),
        ).fetchone()["total"]
        concluidas_hoje = conn.execute(
            "SELECT COUNT(*) AS total FROM entregas WHERE status = ? AND date(data_entrega) = ?",
            (STATUS_ENTREGUE, hoje),
        ).fetchone()["total"]
        falhas = conn.execute(
            "SELECT COUNT(*) AS total FROM entregas WHERE status = ?",
            (STATUS_FALHA,),
        ).fetchone()["total"]
        ocorrencias = conn.execute(
            "SELECT COUNT(*) AS total FROM ocorrencias WHERE tipo = 'OCORRENCIA'",
        ).fetchone()["total"]
    return {
        "pendentes": int(pendentes),
        "em_rota": int(em_rota),
        "concluidas_hoje": int(concluidas_hoje),
        "falhas": int(falhas),
        "ocorrencias": int(ocorrencias),
    }


def historico_dataframe(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    entregador: str | None = None,
    cliente: str | None = None,
    status: str | None = None,
) -> pd.DataFrame:
    query = """
        SELECT
            COALESCE(e.data_entrega, e.criado_em) AS data,
            e.cliente,
            e.numero_venda AS venda,
            r.entregador,
            e.status,
            e.recebido_por,
            e.observacao
        FROM entregas e
        JOIN rotas r ON r.id = e.rota_id
        WHERE 1 = 1
    """
    params: list[Any] = []

    if data_inicio:
        query += " AND date(COALESCE(e.data_entrega, e.criado_em)) >= ?"
        params.append(data_inicio.isoformat())
    if data_fim:
        query += " AND date(COALESCE(e.data_entrega, e.criado_em)) <= ?"
        params.append(data_fim.isoformat())
    if entregador:
        query += " AND r.entregador = ?"
        params.append(entregador)
    if cliente:
        query += " AND lower(e.cliente) LIKE lower(?)"
        params.append(f"%{cliente}%")
    if status:
        query += " AND e.status = ?"
        params.append(status)

    query += " ORDER BY data DESC"

    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)
