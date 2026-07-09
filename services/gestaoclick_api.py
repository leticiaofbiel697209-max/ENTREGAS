from __future__ import annotations

import os
import unicodedata
from datetime import date
from typing import Any

import requests
from dotenv import load_dotenv

from services.db import obter_config


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


def _clean_value(value: Any, default: Any = "") -> Any:
    return default if value in (None, "") else value


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _field_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    value = _first_value(data, keys)
    if isinstance(value, dict):
        return str(_first_value(value, ("nome", "descricao", "situacao", "status", "titulo")))
    return str(value or "")


def _field_id(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Extrai IDs mesmo quando a API devolve o campo como objeto aninhado."""
    value = _first_value(data, keys)
    if isinstance(value, dict):
        value = _first_value(value, ("id", "codigo", "cliente_id", "venda_id"))
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


def _unwrap_address_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    endereco = item.get("endereco")
    if isinstance(endereco, dict):
        merged = {**item, **endereco}
        return merged
    return item


def _address_kind(address: dict[str, Any]) -> str:
    return _normalize_text(
        _first_value(
            address,
            (
                "tipo",
                "tipo_endereco",
                "nome_tipo",
                "nome_tipo_endereco",
                "descricao",
                "identificacao",
            ),
        )
    )


def _pick_address(container: dict[str, Any]) -> dict[str, Any]:
    direct_keys = ("endereco_entrega", "endereco", "endereco_cliente", "cliente_endereco")
    for key in direct_keys:
        value = container.get(key)
        if isinstance(value, dict):
            return value

    list_keys = (
        "enderecos_entrega",
        "enderecos",
        "enderecos_cliente",
        "enderecos_cadastro",
    )
    candidates: list[dict[str, Any]] = []
    for key in list_keys:
        value = container.get(key)
        if isinstance(value, list):
            candidates.extend(_unwrap_address_item(item) for item in value)

    candidates = [item for item in candidates if item]
    if not candidates:
        return {}

    for item in candidates:
        kind = _address_kind(item)
        if "entrega" in kind:
            return item
    for item in candidates:
        kind = _address_kind(item)
        if "principal" in kind or item.get("principal") in ("1", 1, True):
            return item
    return candidates[0]


def _format_address(address: dict[str, Any]) -> str:
    raw = _first_value(address, ("logradouro", "rua", "endereco_entrega", "endereco"))
    if isinstance(raw, dict):
        raw = _first_value(raw, ("logradouro", "rua", "endereco"))
    numero = _first_value(address, ("numero", "numero_endereco"))
    bairro = _first_value(address, ("bairro",))
    complemento = _first_value(address, ("complemento",))

    parts = [str(raw).strip()]
    if numero:
        parts.append(str(numero).strip())
    if complemento:
        parts.append(str(complemento).strip())
    line = ", ".join(part for part in parts if part)
    if bairro:
        line = f"{line} - {bairro}" if line else str(bairro)
    return line


def _address_payload(address: dict[str, Any], label: str = "") -> dict[str, str]:
    return {
        "label": label or _address_kind(address).title() or "Endereco",
        "endereco": _format_address(address),
        "cidade": str(_first_value(address, ("cidade", "municipio", "nome_cidade"))),
        "estado": str(_first_value(address, ("estado", "uf"))),
        "cep": str(_first_value(address, ("cep", "codigo_postal"))),
    }


def _list_addresses(container: dict[str, Any]) -> list[dict[str, str]]:
    """Lista enderecos disponiveis, priorizando o mesmo formato usado pelo GestaoClick."""
    enderecos: list[dict[str, str]] = []
    direct = _pick_address(container)
    if direct:
        enderecos.append(_address_payload(direct, _address_kind(direct).title()))

    for key in ("enderecos_entrega", "enderecos", "enderecos_cliente", "enderecos_cadastro"):
        value = container.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            address = _unwrap_address_item(item)
            if not address:
                continue
            payload = _address_payload(address, _address_kind(address).title())
            if payload["endereco"] and payload not in enderecos:
                enderecos.append(payload)
    return enderecos


def _sale_address_source(venda: dict[str, Any]) -> dict[str, Any]:
    address = _pick_address(venda)
    if address:
        return address
    cliente = _sale_cliente(venda)
    address = _pick_address(cliente)
    if address:
        return address
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
    cliente_id = _field_id(venda, ("cliente_id", "id_cliente", "cliente"))
    if not status and situacoes_por_id:
        status = situacoes_por_id.get(situacao_id, "")

    return {
        "venda_id": str(_first_value(venda, ("id", "venda_id", "codigo", "id_venda"))),
        "numero_venda": str(_first_value(venda, ("numero", "numero_venda", "codigo", "id"))),
        "cliente_id": cliente_id,
        "cliente": str(
            _first_value(venda, ("cliente_nome", "nome_cliente", "razao_social"))
            or _first_value(cliente, ("nome", "razao_social", "fantasia"))
        ),
        "telefone": str(
            _first_value(venda, ("telefone", "celular", "fone"))
            or _first_value(cliente, ("telefone", "celular", "fone"))
        ),
        "endereco": _format_address(endereco),
        "cidade": str(_first_value(endereco, ("cidade", "municipio", "nome_cidade"))),
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

    fonte = _pick_address(cliente) or cliente

    if not dados.get("cliente"):
        dados["cliente"] = str(_first_value(cliente, ("nome", "razao_social", "fantasia")))
    if not dados.get("telefone"):
        dados["telefone"] = str(_first_value(cliente, ("telefone", "celular", "fone")))
    if precisa_endereco:
        dados["endereco"] = _format_address(fonte)
        dados["cidade"] = str(_first_value(fonte, ("cidade", "municipio", "nome_cidade")))
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


def buscar_venda_por_numero(numero_venda: str) -> dict[str, Any]:
    loja = obter_loja_alvo()
    candidatos = _listar_registros(
        "vendas",
        params={
            "codigo": numero_venda,
            "tipo": "produto",
            "loja_id": loja["id"],
        },
        max_paginas=3,
    )
    for venda in candidatos:
        if str(_first_value(venda, ("codigo", "numero", "numero_venda", "id"))) == str(numero_venda):
            return _unwrap(venda)
    if candidatos:
        return _unwrap(candidatos[0])
    raise GestaoClickAPIError(f"Venda numero {numero_venda} nao encontrada na loja NOVAPRINT.")


def _lojas_possiveis_venda(venda: dict[str, Any], loja_id_preferida: str = "") -> list[str]:
    possiveis: list[str] = []

    def add(loja_id: Any) -> None:
        loja_texto = str(loja_id or "").strip()
        if loja_texto and loja_texto not in possiveis:
            possiveis.append(loja_texto)

    add(loja_id_preferida)
    loja_id = _field_id(venda, ("loja_id", "id_loja", "loja"))
    add(loja_id)

    codigo = str(_first_value(venda, ("codigo", "numero", "numero_venda", "id")) or "")
    venda_id = str(_first_value(venda, ("id", "venda_id")) or "")
    if not codigo:
        return possiveis

    lojas_para_testar: list[str] = []
    try:
        lojas_para_testar = [loja["id"] for loja in listar_lojas() if loja.get("id")]
    except Exception:
        lojas_para_testar = []

    for loja_teste in lojas_para_testar:
        try:
            candidatos = _listar_registros(
                "vendas",
                params={
                    "codigo": codigo,
                    "tipo": _clean_value(venda.get("tipo"), "produto"),
                    "loja_id": loja_teste,
                },
                max_paginas=1,
            )
        except Exception:
            continue

        for candidato in candidatos:
            candidato_id = str(_first_value(candidato, ("id", "venda_id")) or "")
            candidato_codigo = str(_first_value(candidato, ("codigo", "numero", "numero_venda")) or "")
            if (venda_id and candidato_id == venda_id) or candidato_codigo == codigo:
                add(_field_id(candidato, ("loja_id", "id_loja", "loja")) or loja_teste)

    try:
        candidatos_sem_loja = _listar_registros(
            "vendas",
            params={"codigo": codigo, "tipo": _clean_value(venda.get("tipo"), "produto")},
            max_paginas=3,
        )
    except Exception:
        candidatos_sem_loja = []

    for candidato in candidatos_sem_loja:
        candidato_id = str(_first_value(candidato, ("id", "venda_id")) or "")
        candidato_codigo = str(_first_value(candidato, ("codigo", "numero", "numero_venda")) or "")
        if (venda_id and candidato_id == venda_id) or candidato_codigo == codigo:
            add(_field_id(candidato, ("loja_id", "id_loja", "loja")))

    return possiveis


def _descobrir_loja_venda(venda: dict[str, Any], loja_id_preferida: str = "") -> str:
    lojas = _lojas_possiveis_venda(venda, loja_id_preferida)
    return lojas[0] if lojas else ""


def _situacao_venda_atual(venda: dict[str, Any]) -> tuple[str, str]:
    situacao_id = str(_first_value(venda, ("situacao_id", "id_situacao", "status_id")) or "")
    situacao_nome = _sale_status(venda)
    return situacao_id, situacao_nome


def _buscar_situacao_id_venda(nome: str) -> str:
    """Retorna somente a situacao explicitamente configurada para evitar chute perigoso."""
    status_id_config = get_config(f"GESTAOCLICK_STATUS_{nome}_ID", "").strip()
    if not status_id_config:
        status_id_config = obter_config(f"GESTAOCLICK_STATUS_{nome}_ID", "").strip()
    if status_id_config:
        return status_id_config

    status_nome_config = get_config(f"GESTAOCLICK_STATUS_{nome}_NOME", "").strip()
    situacoes = listar_situacoes_vendas()
    if status_nome_config:
        alvo = _normalize_text(status_nome_config)
        for situacao in situacoes:
            if _normalize_text(situacao.get("nome")) == alvo:
                return situacao.get("id", "")
        nomes = ", ".join(item.get("nome", "") for item in situacoes if item.get("nome"))
        raise GestaoClickAPIError(
            f"Situacao configurada para {nome} nao encontrada: {status_nome_config}. "
            f"Situacoes disponiveis: {nomes}"
        )

    nomes = ", ".join(f"{item.get('id')} - {item.get('nome')}" for item in situacoes if item.get("id"))
    raise GestaoClickAPIError(
        f"Configure GESTAOCLICK_STATUS_{nome}_ID com o ID exato da situacao correta no GestaoClick. "
        f"Nao vou alterar a venda por nome para evitar erro financeiro. Situacoes disponiveis: {nomes}"
    )


def _buscar_atributo_venda_id(nome: str) -> str:
    alvo = _normalize_text(nome)
    payload = _get_first_success("atributos_vendas")
    for atributo in _extract_items(payload):
        if _normalize_text(_first_value(atributo, ("nome", "descricao"))) == alvo:
            return str(_first_value(atributo, ("id", "atributo_id")))
    return ""


def _normalizar_produtos_para_put(venda: dict[str, Any]) -> list[dict[str, Any]]:
    produtos = []
    for item in venda.get("produtos") or []:
        produto = item.get("produto") if isinstance(item, dict) else None
        if not isinstance(produto, dict):
            continue
        produtos.append(
            {
                "produto": {
                    "id": _clean_value(produto.get("id")),
                    "produto_id": _clean_value(produto.get("produto_id")),
                    "variacao_id": _clean_value(produto.get("variacao_id")),
                    "detalhes": _clean_value(produto.get("detalhes")),
                    "quantidade": _clean_value(produto.get("quantidade"), "1"),
                    "valor_venda": _clean_value(produto.get("valor_venda"), "0"),
                    "tipo_desconto": _clean_value(produto.get("tipo_desconto"), "R$"),
                    "desconto_valor": _clean_value(produto.get("desconto_valor"), "0"),
                    "desconto_porcentagem": _clean_value(produto.get("desconto_porcentagem"), "0"),
                }
            }
        )
    return produtos


def _normalizar_pagamentos_para_put(venda: dict[str, Any]) -> list[dict[str, Any]]:
    pagamentos = []
    for item in venda.get("pagamentos") or []:
        pagamento = item.get("pagamento") if isinstance(item, dict) else None
        if not isinstance(pagamento, dict):
            continue
        pagamentos.append({"pagamento": pagamento})
    return pagamentos


def _remover_atributo_existente(items: Any, atributo_id: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    filtrados = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(
            item.get("atributo_id")
            or item.get("id")
            or item.get("campo_id")
            or item.get("atributo_venda_id")
            or ""
        )
        nested = item.get("atributo") if isinstance(item.get("atributo"), dict) else {}
        nested_id = str(nested.get("atributo_id") or nested.get("id") or "")
        if item_id != atributo_id and nested_id != atributo_id:
            filtrados.append(item)
    return filtrados


def _aplicar_recebedor_payload(payload: dict[str, Any], venda: dict[str, Any], atributo_id: str, recebido_por: str) -> None:
    simples = {"atributo_id": atributo_id, "valor": recebido_por}
    com_id = {"id": atributo_id, "atributo_id": atributo_id, "nome": "RECEBEDOR", "valor": recebido_por}
    wrapper = {"atributo": {"id": atributo_id, "atributo_id": atributo_id, "nome": "RECEBEDOR", "valor": recebido_por}}
    campo = {"campo_id": atributo_id, "atributo_id": atributo_id, "nome": "RECEBEDOR", "valor": recebido_por}

    base_atributos = _remover_atributo_existente(venda.get("atributos"), atributo_id)
    base_valores = _remover_atributo_existente(venda.get("valores_atributos"), atributo_id)
    base_campos = _remover_atributo_existente(venda.get("campos_extras"), atributo_id)

    payload["atributos"] = base_atributos + [com_id, wrapper]
    payload["valores_atributos"] = base_valores + [simples, wrapper]
    payload["campos_extras"] = base_campos + [campo]
    payload["atributos_vendas"] = [simples]
    payload["campo_extra"] = {"RECEBEDOR": recebido_por, atributo_id: recebido_por}
    payload["campos_extra"] = {"RECEBEDOR": recebido_por, atributo_id: recebido_por}
    payload["recebedor"] = recebido_por
    payload["RECEBEDOR"] = recebido_por


def _venda_tem_recebedor(venda: Any, recebido_por: str) -> bool:
    alvo = _normalize_text(recebido_por)
    if not alvo:
        return True
    if isinstance(venda, dict):
        for key, value in venda.items():
            if _normalize_text(key) == "recebedor" and _normalize_text(value) == alvo:
                return True
            if _venda_tem_recebedor(value, recebido_por):
                return True
    if isinstance(venda, list):
        return any(_venda_tem_recebedor(item, recebido_por) for item in venda)
    return _normalize_text(venda) == alvo


def _montar_payload_venda(
    venda: dict[str, Any],
    situacao_id: str,
    recebido_por: str,
    incluir_recebedor: bool = True,
    loja_id: str = "",
) -> dict[str, Any]:
    atributo_recebedor_id = _buscar_atributo_venda_id("RECEBEDOR") if incluir_recebedor else ""

    payload = {
        "tipo": _clean_value(venda.get("tipo"), "produto"),
        "codigo": _clean_value(venda.get("codigo") or venda.get("numero_venda") or venda.get("id")),
        "cliente_id": _clean_value(venda.get("cliente_id")),
        "loja_id": loja_id or _descobrir_loja_venda(venda),
        "vendedor_id": _clean_value(venda.get("vendedor_id")),
        "data": _clean_value(venda.get("data"), date.today().isoformat()),
        "situacao_id": situacao_id or _clean_value(venda.get("situacao_id")),
        "transportadora_id": _clean_value(venda.get("transportadora_id")),
        "centro_custo_id": _clean_value(venda.get("centro_custo_id")),
        "valor_frete": _clean_value(venda.get("valor_frete"), "0"),
        "condicao_pagamento": _clean_value(venda.get("condicao_pagamento"), "a_vista"),
        "observacoes": _clean_value(venda.get("observacoes")),
        "observacoes_interna": _clean_value(venda.get("observacoes_interna")),
        "produtos": _normalizar_produtos_para_put(venda),
        "pagamentos": _normalizar_pagamentos_para_put(venda),
    }

    if incluir_recebedor and atributo_recebedor_id and recebido_por:
        _aplicar_recebedor_payload(payload, venda, atributo_recebedor_id, recebido_por)

    return {key: value for key, value in payload.items() if value not in (None, "")}


def listar_vendas_por_situacoes(situacoes: tuple[str, ...] = ("em andamento", "pronta entrega")) -> list[dict[str, str]]:
    desejadas = {_normalize_text(situacao) for situacao in situacoes}
    pedidos = listar_pedidos_gestaoclick(incluir_ordens_servico=False)
    return [pedido for pedido in pedidos if _normalize_text(pedido.get("situacao")) in desejadas]


def buscar_venda(venda_id: str) -> dict[str, Any]:
    return _unwrap(_request("GET", f"vendas/{venda_id}"))


def buscar_cliente(cliente_id: str) -> dict[str, Any]:
    return _unwrap(_get_first_success(f"clientes/{cliente_id}"))


def buscar_cliente_por_termo(termo: str) -> dict[str, Any]:
    filtros = []
    termo_limpo = termo.strip()
    somente_numeros = "".join(char for char in termo_limpo if char.isdigit())
    if termo_limpo:
        filtros.extend(
            [
                {"nome": termo_limpo},
                {"cpf_cnpj": termo_limpo},
                {"telefone": termo_limpo},
                {"email": termo_limpo},
            ]
        )
    if somente_numeros and somente_numeros != termo_limpo:
        filtros.extend(
            [
                {"cpf_cnpj": somente_numeros},
                {"telefone": somente_numeros},
            ]
        )

    for params in filtros:
        clientes = _listar_registros("clientes", params=params, max_paginas=2)
        if clientes:
            return _unwrap(clientes[0])
    raise GestaoClickAPIError(f"Cliente {termo} nao encontrado.")


def buscar_endereco_venda(venda_id: str) -> dict[str, Any]:
    try:
        venda = buscar_venda_por_numero(venda_id)
    except Exception:
        venda = buscar_venda(venda_id)
    dados = normalizar_venda_para_entrega(venda)
    dados["venda_id"] = dados.get("venda_id") or venda_id
    dados = _completar_com_cliente(dados, dados.get("cliente_id", ""))
    dados["opcoes_endereco"] = listar_enderecos_venda(str(dados.get("venda_id") or venda_id))
    return dados


def buscar_endereco_cliente(cliente_id: str) -> dict[str, Any]:
    try:
        cliente = buscar_cliente(cliente_id)
    except Exception:
        cliente = buscar_cliente_por_termo(cliente_id)
    fonte = _pick_address(cliente) or cliente

    dados = {
        "cliente": str(_first_value(cliente, ("nome", "razao_social", "cliente"))),
        "telefone": str(_first_value(cliente, ("telefone", "celular", "fone"))),
        "endereco": _format_address(fonte),
        "cidade": str(_first_value(fonte, ("cidade", "municipio", "nome_cidade"))),
        "estado": str(_first_value(fonte, ("estado", "uf"))),
        "cep": str(_first_value(fonte, ("cep", "codigo_postal"))),
    }
    dados["opcoes_endereco"] = _list_addresses(cliente)
    return dados


def listar_enderecos_venda(venda_id: str) -> list[dict[str, str]]:
    venda = buscar_venda(venda_id)
    enderecos = _list_addresses(venda)
    cliente_id = _field_id(venda, ("cliente_id", "id_cliente", "cliente"))
    if cliente_id:
        try:
            cliente = buscar_cliente(cliente_id)
            for endereco in _list_addresses(cliente):
                if endereco["endereco"] and endereco not in enderecos:
                    enderecos.append(endereco)
        except Exception:
            pass
    return enderecos


def atualizar_status_venda(
    venda_id: str,
    status: str,
    recebido_por: str = "",
    loja_id: str = "",
) -> dict[str, Any]:
    venda = buscar_venda(venda_id)
    situacao_id = _buscar_situacao_id_venda(status)
    if not situacao_id:
        raise GestaoClickAPIError(f"Situacao {status} nao configurada nas situacoes de vendas.")

    situacao_original_id, situacao_original_nome = _situacao_venda_atual(venda)
    if situacao_original_id == situacao_id:
        raise GestaoClickAPIError(
            f"A venda ja esta na situacao configurada para {status} "
            f"({situacao_id} - {situacao_original_nome}). Confira no GestaoClick antes de confirmar novamente."
        )

    last_error: Exception | None = None
    resposta_status = None
    payload_status: dict[str, Any] = {}
    recebedor_enviado = False
    erro_recebedor = ""
    lojas_para_tentar = _lojas_possiveis_venda(venda, loja_id)
    if not lojas_para_tentar:
        lojas_para_tentar = [""]

    # O GestaoClick bloqueia algumas edicoes quando a venda ja esta ENTREGUE.
    # Por isso o RECEBEDOR e gravado primeiro, mantendo a situacao original.
    if recebido_por:
        if situacao_original_id == situacao_id:
            erro_recebedor = (
                "A venda ja estava ENTREGUE antes do envio; o GestaoClick pode bloquear "
                "alteracao de campos extras nessa situacao."
            )
        else:
            for loja_tentativa in lojas_para_tentar:
                try:
                    payload_recebedor = _montar_payload_venda(
                        venda,
                        situacao_original_id,
                        recebido_por,
                        incluir_recebedor=True,
                        loja_id=loja_tentativa,
                    )
                except Exception as exc:
                    last_error = exc
                    erro_recebedor = str(exc)
                    continue

                for candidate in _endpoint_candidates(f"vendas/{venda_id}"):
                    try:
                        _request("PUT", candidate, json=payload_recebedor)
                        try:
                            venda_com_recebedor = buscar_venda(venda_id)
                            recebedor_enviado = _venda_tem_recebedor(venda_com_recebedor, recebido_por)
                            if not recebedor_enviado:
                                erro_recebedor = (
                                    "GestaoClick aceitou a tentativa de preencher RECEBEDOR, "
                                    "mas o valor nao apareceu na venda ao consultar novamente."
                                )
                        except Exception as exc:
                            recebedor_enviado = True
                            erro_recebedor = f"Nao foi possivel confirmar RECEBEDOR apos gravar: {exc}"
                        break
                    except Exception as exc:
                        last_error = exc
                if recebedor_enviado:
                    break

            if not recebedor_enviado and not erro_recebedor:
                erro_recebedor = str(last_error or "Campo RECEBEDOR nao aceito pela API.")

    for loja_tentativa in lojas_para_tentar:
        payload = _montar_payload_venda(
            venda,
            situacao_id,
            "",
            incluir_recebedor=False,
            loja_id=loja_tentativa,
        )
        for candidate in _endpoint_candidates(f"vendas/{venda_id}"):
            try:
                resposta_status = _request("PUT", candidate, json=payload)
                payload_status = payload
                break
            except Exception as exc:
                last_error = exc
        if resposta_status is not None:
            break

    if resposta_status is None:
        if last_error:
            raise last_error
        raise GestaoClickAPIError("Nao foi possivel atualizar a venda.")

    venda_confirmada = buscar_venda(venda_id)
    situacao_confirmada_id, situacao_confirmada_nome = _situacao_venda_atual(venda_confirmada)
    if str(situacao_confirmada_id) != str(situacao_id):
        raise GestaoClickAPIError(
            "GestaoClick recebeu a atualizacao, mas a venda nao ficou na situacao configurada. "
            f"Esperado ID {situacao_id}; atual ID {situacao_confirmada_id} - {situacao_confirmada_nome}. "
            "A entrega nao sera marcada como entregue localmente."
        )

    return {
        "status_atualizado": True,
        "situacao_id_enviada": situacao_id,
        "situacao_confirmada_id": situacao_confirmada_id,
        "situacao_confirmada_nome": situacao_confirmada_nome,
        "loja_id_enviada": payload_status.get("loja_id", ""),
        "recebedor_enviado": recebedor_enviado,
        "erro_recebedor": erro_recebedor,
        "retorno": resposta_status,
    }
