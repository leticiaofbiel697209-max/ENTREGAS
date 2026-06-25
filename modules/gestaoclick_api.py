from __future__ import annotations

import os
import unicodedata
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
        if secret_value not in (None, ""):
            return str(secret_value)

        # Tambem aceita Secrets agrupados como [gestaoclick].
        group = st.secrets.get("gestaoclick", {})
        if hasattr(group, "get"):
            grouped_value = group.get(name, default)
            return str(grouped_value) if grouped_value not in (None, "") else default
        return default
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


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("data", "dados", "retorno", "vendas", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested
    return []


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return ""


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _field_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    value = _first_value(data, keys)
    if isinstance(value, dict):
        return str(_first_value(value, ("nome", "descricao", "situacao", "status", "titulo")))
    return str(value or "")


def _sale_status(venda: dict[str, Any]) -> str:
    direct = _field_text(
        venda,
        (
            "situacao",
            "situacao_nome",
            "nome_situacao",
            "status",
            "status_nome",
            "descricao_situacao",
        ),
    )
    if direct:
        return direct

    for key in ("situacao", "status"):
        value = venda.get(key)
        if isinstance(value, dict):
            nested = _field_text(value, ("nome", "descricao", "titulo", "status", "situacao"))
            if nested:
                return nested
    return ""


def _sale_cliente(venda: dict[str, Any]) -> dict[str, Any]:
    cliente = venda.get("cliente")
    if isinstance(cliente, dict):
        return cliente
    return {}


def _sale_address_source(venda: dict[str, Any]) -> dict[str, Any]:
    for key in ("endereco_entrega", "endereco", "endereco_cliente", "cliente_endereco"):
        value = venda.get(key)
        if isinstance(value, dict):
            return value
    cliente = _sale_cliente(venda)
    endereco_cliente = cliente.get("endereco")
    if isinstance(endereco_cliente, dict):
        return endereco_cliente
    return venda


def normalizar_venda_para_entrega(venda: dict[str, Any]) -> dict[str, str]:
    cliente = _sale_cliente(venda)
    endereco = _sale_address_source(venda)
    status = _sale_status(venda)

    return {
        "venda_id": str(_first_value(venda, ("id", "venda_id", "codigo", "id_venda"))),
        "numero_venda": str(_first_value(venda, ("numero", "numero_venda", "codigo", "id"))),
        "cliente": str(
            _first_value(venda, ("cliente_nome", "nome_cliente", "razao_social"))
            or _first_value(cliente, ("nome", "razao_social", "fantasia"))
        ),
        "telefone": str(
            _first_value(venda, ("telefone", "celular", "fone"))
            or _first_value(cliente, ("telefone", "celular", "fone"))
        ),
        "endereco": str(_first_value(endereco, ("endereco", "logradouro", "rua", "endereco_entrega"))),
        "cidade": str(_first_value(endereco, ("cidade", "municipio"))),
        "estado": str(_first_value(endereco, ("estado", "uf"))),
        "cep": str(_first_value(endereco, ("cep", "codigo_postal"))),
        "observacao": str(_first_value(venda, ("observacoes", "observacao", "obs"))),
        "situacao": status,
    }


def listar_vendas_por_situacoes(situacoes: tuple[str, ...] = ("em andamento", "pronta entrega")) -> list[dict[str, str]]:
    desejadas = {_normalize_text(situacao) for situacao in situacoes}
    vendas: list[dict[str, Any]] = []

    # Algumas contas aceitam filtros, outras retornam a lista geral; por isso filtramos tambem no app.
    for params in (
        {"limite": 100},
        {"limit": 100},
        {},
    ):
        payload = _request("GET", "vendas", params=params)
        vendas = _extract_items(payload)
        if vendas:
            break

    normalizadas = [normalizar_venda_para_entrega(venda) for venda in vendas]
    filtradas = [
        venda
        for venda in normalizadas
        if _normalize_text(venda.get("situacao")) in desejadas
    ]
    return filtradas


def buscar_venda(venda_id: str) -> dict[str, Any]:
    return _unwrap(_request("GET", f"vendas/{venda_id}"))


def buscar_cliente(cliente_id: str) -> dict[str, Any]:
    return _unwrap(_request("GET", f"clientes/{cliente_id}"))


def buscar_endereco_venda(venda_id: str) -> dict[str, Any]:
    venda = buscar_venda(venda_id)
    dados = normalizar_venda_para_entrega(venda)
    dados["venda_id"] = dados.get("venda_id") or venda_id
    return dados


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
