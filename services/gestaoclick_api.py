from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


class GestaoClickAPIError(RuntimeError):
    """Erro padronizado para falhas de comunicacao com o GestaoClick."""


def get_config(name: str, default: str = "") -> str:
    """Le configuracoes do .env, variaveis do ambiente ou Secrets do Streamlit Cloud."""
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value)

    try:
        import streamlit as st

        secret_value = st.secrets.get(name, default)
        return str(secret_value) if secret_value not in (None, "") else default
    except Exception:
        return default


def _base_url() -> str:
    url = get_config("GESTAOCLICK_URL", "").strip().rstrip("/")
    if not url:
        raise GestaoClickAPIError("GESTAOCLICK_URL nao configurado.")
    return url


def _headers() -> dict[str, str]:
    token = get_config("GESTAOCLICK_TOKEN", "").strip()
    if not token:
        raise GestaoClickAPIError("GESTAOCLICK_TOKEN nao configurado.")
    return {
        "Authorization": f"Bearer {token}",
        "access-token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _timeout() -> int:
    try:
        return int(get_config("GESTAOCLICK_TIMEOUT", "30"))
    except ValueError:
        return 30


def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{_base_url()}/{path.lstrip('/')}"
    response = requests.request(
        method=method,
        url=url,
        headers=_headers(),
        timeout=_timeout(),
        **kwargs,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {"texto": response.text}

    if response.status_code >= 400:
        raise GestaoClickAPIError(
            f"GestaoClick retornou HTTP {response.status_code}: {payload}"
        )
    if isinstance(payload, dict):
        return payload
    return {"dados": payload}


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "dados", "retorno", "venda", "cliente"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return payload


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return ""


def buscar_venda(venda_id: str) -> dict[str, Any]:
    return _unwrap(_request("GET", f"vendas/{venda_id}"))


def buscar_cliente(cliente_id: str) -> dict[str, Any]:
    return _unwrap(_request("GET", f"clientes/{cliente_id}"))


def buscar_endereco_venda(venda_id: str) -> dict[str, Any]:
    venda = buscar_venda(venda_id)
    cliente = venda.get("cliente") if isinstance(venda.get("cliente"), dict) else {}
    endereco = venda.get("endereco_entrega") if isinstance(venda.get("endereco_entrega"), dict) else {}
    fonte = endereco or venda or cliente

    return {
        "venda_id": str(_first_value(venda, ("id", "venda_id", "codigo")) or venda_id),
        "numero_venda": str(_first_value(venda, ("numero", "numero_venda", "codigo", "id"))),
        "cliente": str(_first_value(venda, ("cliente_nome", "nome_cliente")) or _first_value(cliente, ("nome", "razao_social"))),
        "telefone": str(_first_value(venda, ("telefone", "celular")) or _first_value(cliente, ("telefone", "celular"))),
        "endereco": str(_first_value(fonte, ("endereco", "logradouro", "rua"))),
        "cidade": str(_first_value(fonte, ("cidade", "municipio"))),
        "estado": str(_first_value(fonte, ("estado", "uf"))),
        "cep": str(_first_value(fonte, ("cep", "codigo_postal"))),
    }


def buscar_endereco_cliente(cliente_id: str) -> dict[str, Any]:
    cliente = buscar_cliente(cliente_id)
    endereco = cliente.get("endereco") if isinstance(cliente.get("endereco"), dict) else {}
    fonte = endereco or cliente

    return {
        "cliente": str(_first_value(cliente, ("nome", "razao_social", "cliente"))),
        "telefone": str(_first_value(cliente, ("telefone", "celular", "fone"))),
        "endereco": str(_first_value(fonte, ("endereco", "logradouro", "rua"))),
        "cidade": str(_first_value(fonte, ("cidade", "municipio"))),
        "estado": str(_first_value(fonte, ("estado", "uf"))),
        "cep": str(_first_value(fonte, ("cep", "codigo_postal"))),
    }


def atualizar_status_venda(venda_id: str, status: str) -> dict[str, Any]:
    payload = {
        "situacao": status,
        "status": status,
    }
    return _request("PUT", f"vendas/{venda_id}", json=payload)
