from __future__ import annotations

import os
import unicodedata
from datetime import date, timedelta
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


class GestaoClickAPIError(RuntimeError):
    """Erro padronizado para falhas de comunicacao com o GestaoClick."""


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

        # Tambem aceita Secrets agrupados como [gestaoclick].
        for group_name in ("gestaoclick", "GESTAOCLICK"):
            group = st.secrets.get(group_name, {})
            if hasattr(group, "get"):
                for candidate in candidates:
                    grouped_value = group.get(candidate)
                    if grouped_value not in (None, ""):
                        return str(grouped_value)
        return default
    except Exception:
        return default


def _base_url() -> str:
    url = get_config("GESTAOCLICK_URL", "https://api.gestaoclick.com").strip().rstrip("/")
    if not url:
        raise GestaoClickAPIError("GESTAOCLICK_URL nao configurado.")
    return url


def status_configuracao() -> dict[str, str | bool]:
    token = get_config("GESTAOCLICK_TOKEN", "").strip()
    secret_token = get_config("GESTAOCLICK_SECRET_TOKEN", "").strip()
    return {
        "url": _base_url(),
        "token_configurado": bool(token),
        "secret_token_configurado": bool(secret_token),
    }


def _headers() -> dict[str, str]:
    token = get_config("GESTAOCLICK_TOKEN", "").strip()
    secret_token = get_config("GESTAOCLICK_SECRET_TOKEN", "").strip()
    if not token:
        raise GestaoClickAPIError("GESTAOCLICK_TOKEN nao configurado.")
    if not secret_token:
        raise GestaoClickAPIError("GESTAOCLICK_SECRET_TOKEN nao configurado.")
    return {
        "access-token": token,
        "secret-access-token": secret_token,
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


def _sale_status_id(venda: dict[str, Any]) -> str:
    return str(_first_value(venda, ("situacao_id", "id_situacao", "status_id")) or "")


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


def normalizar_venda_para_entrega(
    venda: dict[str, Any],
    situacoes_por_id: dict[str, str] | None = None,
    origem: str = "vendas",
) -> dict[str, str]:
    cliente = _sale_cliente(venda)
    endereco = _sale_address_source(venda)
    situacao_id = _sale_status_id(venda)
    status = _sale_status(venda)
    if not status and situacoes_por_id:
        status = situacoes_por_id.get(situacao_id, "")

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
        "situacao_id": situacao_id,
        "data": str(_first_value(venda, ("data", "data_venda", "data_cadastro"))),
        "valor_total": str(_first_value(venda, ("valor_total", "valor", "total"))),
        "origem": origem,
    }


def _listar_situacoes(endpoint: str) -> list[dict[str, str]]:
    payload = _request("GET", endpoint)
    situacoes = []
    for item in _extract_items(payload):
        situacoes.append(
            {
                "id": str(_first_value(item, ("id", "situacao_id"))),
                "nome": str(_first_value(item, ("nome", "situacao", "descricao"))),
            }
        )
    return situacoes


def listar_situacoes_vendas() -> list[dict[str, str]]:
    return _listar_situacoes("situacoes_vendas")


def listar_situacoes_orcamentos() -> list[dict[str, str]]:
    return _listar_situacoes("situacoes_orcamentos")


def _listar_registros(endpoint: str, params: dict[str, Any] | None = None, max_paginas: int = 10) -> list[dict[str, Any]]:
    registros: list[dict[str, Any]] = []
    params_base = dict(params or {})

    for pagina in range(1, max_paginas + 1):
        params_pagina = {
            **params_base,
            "pagina": pagina,
            "limite": 100,
        }
        payload = _request("GET", endpoint, params=params_pagina)
        itens = _extract_items(payload)
        if not itens:
            break

        registros.extend(itens)
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        if not meta.get("proxima_pagina"):
            break

    return registros


def _buscar_pedidos_endpoint(
    endpoint: str,
    endpoint_situacoes: str,
    origem: str,
    data_inicio: date | None,
    max_paginas: int,
) -> list[dict[str, str]]:
    situacoes = _listar_situacoes(endpoint_situacoes)
    situacoes_por_id = {item["id"]: item["nome"] for item in situacoes if item.get("id")}
    params: dict[str, Any] = {
        "ordenacao": "data",
        "direcao": "desc",
    }
    if data_inicio:
        params["data_inicio"] = data_inicio.isoformat()

    registros = _listar_registros(endpoint, params=params, max_paginas=max_paginas)
    return [
        normalizar_venda_para_entrega(registro, situacoes_por_id, origem=origem)
        for registro in registros
    ]


def listar_pedidos_gestaoclick(
    data_inicio: date | None = None,
    incluir_orcamentos: bool = True,
    max_paginas: int = 10,
) -> list[dict[str, str]]:
    if data_inicio is None:
        data_inicio = date.today() - timedelta(days=180)

    pedidos = _buscar_pedidos_endpoint(
        endpoint="vendas",
        endpoint_situacoes="situacoes_vendas",
        origem="venda",
        data_inicio=data_inicio,
        max_paginas=max_paginas,
    )

    if incluir_orcamentos:
        pedidos.extend(
            _buscar_pedidos_endpoint(
                endpoint="orcamentos",
                endpoint_situacoes="situacoes_orcamentos",
                origem="orcamento",
                data_inicio=data_inicio,
                max_paginas=max_paginas,
            )
        )

    pedidos_unicos: list[dict[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for pedido in pedidos:
        chave = (pedido.get("origem", ""), pedido.get("venda_id", "") or pedido.get("numero_venda", ""))
        if chave not in vistos:
            pedidos_unicos.append(pedido)
            vistos.add(chave)

    return pedidos_unicos


def listar_vendas_por_situacoes(situacoes: tuple[str, ...] = ("em andamento", "pronta entrega")) -> list[dict[str, str]]:
    desejadas = {_normalize_text(situacao) for situacao in situacoes}
    pedidos = listar_pedidos_gestaoclick(incluir_orcamentos=False)
    return [pedido for pedido in pedidos if _normalize_text(pedido.get("situacao")) in desejadas]


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
