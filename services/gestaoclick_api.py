from __future__ import annotations

import os
import unicodedata
from datetime import date
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
    loja_id = get_config("GESTAOCLICK_LOJA_ID", "").strip()
    return {
        "url": _base_url(),
        "token_configurado": bool(token),
        "secret_token_configurado": bool(secret_token),
        "loja_id_configurado": bool(loja_id),
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


def _endpoint_candidates(endpoint: str) -> tuple[str, ...]:
    clean = endpoint.strip("/")
    if clean.startswith("api/"):
        return (clean,)
    return (clean, f"api/{clean}")


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


def _get_first_success(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    last_error: Exception | None = None
    for candidate in _endpoint_candidates(endpoint):
        try:
            return _request("GET", candidate, params=params or {})
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return {"data": []}


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
        "cliente_id": str(_first_value(venda, ("cliente_id", "id_cliente"))),
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
        "loja_id": str(_first_value(venda, ("loja_id", "id_loja"))),
        "nome_loja": str(_first_value(venda, ("nome_loja", "loja"))),
    }


def _completar_com_cliente(dados: dict[str, str], cliente_id: str) -> dict[str, str]:
    if not cliente_id:
        return dados

    precisa_endereco = not dados.get("endereco") or "nao informado" in _normalize_text(dados.get("endereco"))
    precisa_telefone = not dados.get("telefone")
    if not precisa_endereco and not precisa_telefone:
        return dados

    try:
        cliente = buscar_cliente(cliente_id)
    except Exception:
        return dados

    endereco_cliente = cliente.get("endereco") if isinstance(cliente.get("endereco"), dict) else {}
    fonte = endereco_cliente or cliente

    if not dados.get("cliente"):
        dados["cliente"] = str(_first_value(cliente, ("nome", "razao_social", "fantasia")))
    if not dados.get("telefone"):
        dados["telefone"] = str(_first_value(cliente, ("telefone", "celular", "fone")))
    if precisa_endereco:
        dados["endereco"] = str(_first_value(fonte, ("endereco", "logradouro", "rua")))
        dados["cidade"] = str(_first_value(fonte, ("cidade", "municipio")))
        dados["estado"] = str(_first_value(fonte, ("estado", "uf")))
        dados["cep"] = str(_first_value(fonte, ("cep", "codigo_postal")))

    return dados


def listar_lojas() -> list[dict[str, str]]:
    payload = _get_first_success("lojas")
    lojas = []
    for item in _extract_items(payload):
        lojas.append(
            {
                "id": str(_first_value(item, ("id", "loja_id", "codigo"))),
                "nome": str(_first_value(item, ("nome", "nome_loja", "razao_social", "fantasia"))),
            }
        )
    return lojas


def obter_loja_alvo() -> dict[str, str]:
    loja_id_config = get_config("GESTAOCLICK_LOJA_ID", "").strip()
    if loja_id_config:
        return {"id": loja_id_config, "nome": "NOVAPRINT"}

    lojas = listar_lojas()
    for loja in lojas:
        if _normalize_text(loja.get("nome")) == "novaprint":
            return loja
    for loja in lojas:
        if "novaprint" in _normalize_text(loja.get("nome")):
            return loja

    nomes = ", ".join(loja.get("nome", "") for loja in lojas if loja.get("nome"))
    detalhe = f" Lojas encontradas: {nomes}." if nomes else ""
    raise GestaoClickAPIError(
        "Nao encontrei a loja NOVAPRINT na API. Configure GESTAOCLICK_LOJA_ID nos Secrets." + detalhe
    )


def _listar_situacoes(endpoint: str) -> list[dict[str, str]]:
    payload = None
    last_error: Exception | None = None
    for candidate in _endpoint_candidates(endpoint):
        try:
            payload = _request("GET", candidate)
            if _extract_items(payload):
                break
        except Exception as exc:
            last_error = exc
    if payload is None:
        if last_error:
            raise last_error
        return []

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


def listar_situacoes_ordens_servicos() -> list[dict[str, str]]:
    return _listar_situacoes("situacoes_ordens_servicos")


def _listar_registros(endpoint: str, params: dict[str, Any] | None = None, max_paginas: int = 10) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for candidate in _endpoint_candidates(endpoint):
        registros: list[dict[str, Any]] = []
        params_base = dict(params or {})

        try:
            for pagina in range(1, max_paginas + 1):
                params_pagina = {
                    **params_base,
                    "pagina": pagina,
                    "limite": 100,
                }
                payload = _request("GET", candidate, params=params_pagina)
                itens = _extract_items(payload)
                if not itens:
                    break

                registros.extend(itens)
                meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
                if not meta.get("proxima_pagina"):
                    break
        except Exception as exc:
            last_error = exc
            continue

        if registros:
            return registros

    if last_error:
        raise last_error
    return []


def _buscar_pedidos_endpoint(
    endpoint: str,
    endpoint_situacoes: str,
    origem: str,
    params_extras: dict[str, Any] | None,
    data_inicio: date | None,
    loja_id: str,
    max_paginas: int,
) -> list[dict[str, str]]:
    situacoes = _listar_situacoes(endpoint_situacoes)
    situacoes_por_id = {item["id"]: item["nome"] for item in situacoes if item.get("id")}
    params: dict[str, Any] = {
        "ordenacao": "data",
        "direcao": "desc",
        "loja_id": loja_id,
    }
    if data_inicio:
        params["data_inicio"] = data_inicio.isoformat()
    params.update(params_extras or {})

    registros = _listar_registros(endpoint, params=params, max_paginas=max_paginas)
    return [
        normalizar_venda_para_entrega(registro, situacoes_por_id, origem=origem)
        for registro in registros
    ]


def listar_pedidos_gestaoclick(
    data_inicio: date | None = None,
    incluir_ordens_servico: bool = True,
    max_paginas: int = 10,
) -> list[dict[str, str]]:
    loja = obter_loja_alvo()
    loja_id = loja["id"]

    pedidos = _buscar_pedidos_endpoint(
        endpoint="vendas",
        endpoint_situacoes="situacoes_vendas",
        origem="venda_produto",
        params_extras={"tipo": "produto"},
        data_inicio=data_inicio,
        loja_id=loja_id,
        max_paginas=max_paginas,
    )

    if incluir_ordens_servico:
        pedidos.extend(
            _buscar_pedidos_endpoint(
                endpoint="ordens_servicos",
                endpoint_situacoes="situacoes_ordens_servicos",
                origem="ordem_servico",
                params_extras=None,
                data_inicio=data_inicio,
                loja_id=loja_id,
                max_paginas=max_paginas,
            )
        )

    pedidos_unicos: list[dict[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for pedido in pedidos:
        nome_loja = _normalize_text(pedido.get("nome_loja"))
        pedido_loja_id = str(pedido.get("loja_id", ""))
        if pedido_loja_id and pedido_loja_id != loja_id:
            continue
        if nome_loja and "novaprint" not in nome_loja:
            continue
        chave = (pedido.get("origem", ""), pedido.get("venda_id", "") or pedido.get("numero_venda", ""))
        if chave not in vistos:
            pedidos_unicos.append(pedido)
            vistos.add(chave)

    return pedidos_unicos


def buscar_pedido_detalhado(origem: str, pedido_id: str) -> dict[str, str]:
    origem_normalizada = _normalize_text(origem)
    if origem_normalizada == "ordem_servico":
        payload = _get_first_success(f"ordens_servicos/{pedido_id}")
        situacoes = listar_situacoes_ordens_servicos()
        origem_retorno = "ordem_servico"
    else:
        payload = _get_first_success(f"vendas/{pedido_id}")
        situacoes = listar_situacoes_vendas()
        origem_retorno = "venda_produto"

    situacoes_por_id = {item["id"]: item["nome"] for item in situacoes if item.get("id")}
    dados = normalizar_venda_para_entrega(_unwrap(payload), situacoes_por_id, origem=origem_retorno)
    dados["venda_id"] = dados.get("venda_id") or pedido_id
    return _completar_com_cliente(dados, dados.get("cliente_id", ""))


def listar_vendas_por_situacoes(situacoes: tuple[str, ...] = ("em andamento", "pronta entrega")) -> list[dict[str, str]]:
    desejadas = {_normalize_text(situacao) for situacao in situacoes}
    pedidos = listar_pedidos_gestaoclick(incluir_ordens_servico=False)
    return [pedido for pedido in pedidos if _normalize_text(pedido.get("situacao")) in desejadas]


def buscar_venda(venda_id: str) -> dict[str, Any]:
    return _unwrap(_request("GET", f"vendas/{venda_id}"))


def buscar_cliente(cliente_id: str) -> dict[str, Any]:
    return _unwrap(_request("GET", f"clientes/{cliente_id}"))


def buscar_endereco_venda(venda_id: str) -> dict[str, Any]:
    venda = buscar_venda(venda_id)
    dados = normalizar_venda_para_entrega(venda)
    dados["venda_id"] = dados.get("venda_id") or venda_id
    return _completar_com_cliente(dados, dados.get("cliente_id", ""))


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
