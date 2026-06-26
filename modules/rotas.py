import hashlib
from datetime import date

import pandas as pd
import streamlit as st

from services import gestaoclick_api
from services.rotas_service import (
    adicionar_entrega,
    atualizar_endereco_entrega,
    criar_rota,
    listar_entregadores,
    listar_entregas_rota,
    listar_rotas,
)


def _campo(prefixo: str, nome: str, valor: str = "") -> str:
    return st.text_input(nome, value=valor or "", key=f"{prefixo}_{nome}")


def _selecionar_rota() -> int | None:
    rotas = listar_rotas()
    if not rotas:
        st.info("Crie uma rota antes de adicionar entregas.")
        return None

    opcoes = {
        f"#{rota['id']} - {rota['data_rota']} - {rota['entregador']} ({rota['total_entregas']} entregas)": rota["id"]
        for rota in rotas
    }
    escolha = st.selectbox("Rota", list(opcoes.keys()))
    return int(opcoes[escolha])


def _dados_vazios() -> dict[str, str]:
    return {
        "venda_id": "",
        "numero_venda": "",
        "cliente": "",
        "telefone": "",
        "endereco": "",
        "cidade": "",
        "estado": "",
        "cep": "",
        "observacao": "",
    }


def _aplicar_endereco(dados: dict, endereco: dict) -> dict:
    atualizados = dict(dados)
    atualizados["endereco"] = endereco.get("endereco", atualizados.get("endereco", ""))
    atualizados["cidade"] = endereco.get("cidade", atualizados.get("cidade", ""))
    atualizados["estado"] = endereco.get("estado", atualizados.get("estado", ""))
    atualizados["cep"] = endereco.get("cep", atualizados.get("cep", ""))
    return atualizados


def _selecionar_endereco(dados: dict, chave: str) -> dict:
    opcoes = dados.get("opcoes_endereco") or []
    if not opcoes:
        return dados

    labels = []
    for idx, endereco in enumerate(opcoes, start=1):
        label = endereco.get("label") or f"Endereco {idx}"
        resumo = " - ".join(
            item
            for item in (
                endereco.get("endereco", ""),
                endereco.get("cidade", ""),
                endereco.get("estado", ""),
                endereco.get("cep", ""),
            )
            if item
        )
        labels.append(f"{label}: {resumo}" if resumo else label)

    escolha = st.selectbox("Endereco para entrega", labels, key=f"endereco_opcao_{chave}")
    endereco = opcoes[labels.index(escolha)]
    return _aplicar_endereco(dados, endereco)


def _assinatura_dados(dados: dict) -> str:
    partes = [
        str(dados.get("venda_id", "")),
        str(dados.get("numero_venda", "")),
        str(dados.get("endereco", "")),
        str(dados.get("cep", "")),
    ]
    return hashlib.md5("|".join(partes).encode("utf-8")).hexdigest()[:8]


def _filtrar_por_data(tabela: pd.DataFrame, data_inicio: date) -> pd.DataFrame:
    if "data" not in tabela.columns or tabela.empty:
        return tabela
    datas_iso = pd.to_datetime(tabela["data"], errors="coerce", format="%Y-%m-%d").dt.date
    datas_br = pd.to_datetime(tabela["data"], errors="coerce", dayfirst=True).dt.date
    datas = datas_iso.fillna(datas_br)
    return tabela[datas.isna() | (datas >= data_inicio)]


def _render_editor_endereco_rota(entregas: list[dict]) -> None:
    st.markdown("#### Ajustar endereco da entrega")

    opcoes = {
        f"#{item['id']} - {item.get('numero_venda') or item.get('venda_id') or '-'} - {item['cliente']}": item
        for item in entregas
    }
    escolha = st.selectbox("Entrega da rota", list(opcoes.keys()), key="editar_endereco_entrega_rota")
    entrega = opcoes[escolha]

    dados = {
        "endereco": entrega.get("endereco", ""),
        "cidade": entrega.get("cidade", ""),
        "estado": entrega.get("estado", ""),
        "cep": entrega.get("cep", ""),
    }

    opcoes_endereco = []
    origem_pedido = str(entrega.get("origem_pedido") or "").lower()
    if entrega.get("venda_id") and origem_pedido != "ordem_servico":
        try:
            opcoes_endereco = gestaoclick_api.listar_enderecos_venda(str(entrega["venda_id"]))
        except Exception as exc:
            st.caption(f"Nao foi possivel buscar enderecos no GestaoClick: {exc}")

    if opcoes_endereco:
        labels = []
        for idx, endereco in enumerate(opcoes_endereco, start=1):
            label = endereco.get("label") or f"Endereco {idx}"
            resumo = " - ".join(
                item
                for item in (
                    endereco.get("endereco", ""),
                    endereco.get("cidade", ""),
                    endereco.get("estado", ""),
                    endereco.get("cep", ""),
                )
                if item
            )
            labels.append(f"{label}: {resumo}" if resumo else label)
        selecionado = st.selectbox("Endereco do GestaoClick", labels, key=f"endereco_rota_gc_{entrega['id']}")
        dados = _aplicar_endereco(dados, opcoes_endereco[labels.index(selecionado)])

    with st.form(f"form_editar_endereco_rota_{entrega['id']}_{_assinatura_dados(dados)}"):
        endereco = st.text_area("Endereco", value=dados.get("endereco", ""))
        col1, col2, col3 = st.columns([2, 1, 1])
        cidade = col1.text_input("Cidade", value=dados.get("cidade", ""))
        estado = col2.text_input("Estado", value=dados.get("estado", ""))
        cep = col3.text_input("CEP", value=dados.get("cep", ""))
        salvar = st.form_submit_button("Salvar endereco nesta entrega")

    if salvar:
        if not endereco.strip():
            st.error("Informe o endereco.")
            return
        atualizar_endereco_entrega(int(entrega["id"]), endereco, cidade, estado, cep)
        st.success("Endereco da entrega atualizado.")
        st.rerun()


def _form_entrega(rota_id: int, dados: dict[str, str], prefixo: str) -> None:
    assinatura = _assinatura_dados(dados)
    with st.form(f"form_entrega_{prefixo}"):
        col1, col2 = st.columns(2)
        venda_id = col1.text_input("ID da venda", value=dados.get("venda_id", ""), key=f"{prefixo}_{assinatura}_venda_id")
        numero_venda = col2.text_input(
            "Numero da venda",
            value=dados.get("numero_venda", ""),
            key=f"{prefixo}_{assinatura}_numero_venda",
        )
        cliente = st.text_input("Cliente", value=dados.get("cliente", ""), key=f"{prefixo}_{assinatura}_cliente")
        telefone = st.text_input("Telefone", value=dados.get("telefone", ""), key=f"{prefixo}_{assinatura}_telefone")
        endereco = st.text_area("Endereco", value=dados.get("endereco", ""), key=f"{prefixo}_{assinatura}_endereco")
        col3, col4, col5 = st.columns([2, 1, 1])
        cidade = col3.text_input("Cidade", value=dados.get("cidade", ""), key=f"{prefixo}_{assinatura}_cidade")
        estado = col4.text_input("Estado", value=dados.get("estado", ""), key=f"{prefixo}_{assinatura}_estado")
        cep = col5.text_input("CEP", value=dados.get("cep", ""), key=f"{prefixo}_{assinatura}_cep")
        observacao = st.text_area(
            "Observacao",
            value=dados.get("observacao", ""),
            key=f"{prefixo}_{assinatura}_observacao",
        )
        salvar = st.form_submit_button("Adicionar entrega")

    if salvar:
        obrigatorios = [cliente, endereco]
        if not all(valor.strip() for valor in obrigatorios):
            st.error("Cliente e endereco sao obrigatorios.")
            return
        adicionar_entrega(
            rota_id,
            {
                "venda_id": venda_id,
                "numero_venda": numero_venda,
                "cliente": cliente,
                "telefone": telefone,
                "endereco": endereco,
                "cidade": cidade,
                "estado": estado,
                "cep": cep,
                "observacao": observacao,
                "loja_id": str(dados.get("loja_id", "")),
            },
        )
        st.success("Entrega adicionada a rota.")
        st.rerun()


def render() -> None:
    st.title("Cadastro de rota")

    entregadores = listar_entregadores()
    if not entregadores:
        st.warning("Cadastre pelo menos um entregador em Configuracoes.")
        return

    with st.expander("Criar nova rota", expanded=True):
        with st.form("form_rota"):
            nomes = {item["nome"]: item["id"] for item in entregadores}
            entregador_nome = st.selectbox("Entregador", list(nomes.keys()))
            data_rota = st.date_input("Data da rota", value=date.today())
            veiculo = st.text_input("Veiculo")
            observacao = st.text_area("Observacao geral")
            salvar = st.form_submit_button("Salvar rota")

        if salvar:
            rota_id = criar_rota(data_rota, nomes[entregador_nome], entregador_nome, veiculo, observacao)
            st.success(f"Rota #{rota_id} criada.")
            st.rerun()

    st.subheader("Adicionar entregas na rota")
    rota_id = _selecionar_rota()
    if not rota_id:
        return

    origem = st.radio(
        "Origem do endereco",
        ["Buscar endereco da venda", "Buscar endereco do cliente", "Digitar manualmente"],
        horizontal=True,
    )

    dados = _dados_vazios()
    prefixo = "manual"

    if origem == "Buscar endereco da venda":
        venda_id = st.text_input("Informe o ID ou numero da venda no GestaoClick")
        if st.button("Buscar venda"):
            if not venda_id.strip():
                st.error("Informe o ID ou numero da venda.")
            else:
                try:
                    st.session_state["dados_venda_gc"] = gestaoclick_api.buscar_endereco_venda(venda_id.strip())
                    st.success("Venda localizada.")
                except Exception as exc:
                    st.error(f"Nao foi possivel buscar a venda: {exc}")
        dados.update(st.session_state.get("dados_venda_gc", {}))
        dados = _selecionar_endereco(dados, "venda")
        prefixo = "venda"

    elif origem == "Buscar endereco do cliente":
        cliente_id = st.text_input("Informe ID, nome, CPF/CNPJ, telefone ou e-mail do cliente")
        if st.button("Buscar cliente"):
            if not cliente_id.strip():
                st.error("Informe uma informacao do cliente.")
            else:
                try:
                    st.session_state["dados_cliente_gc"] = gestaoclick_api.buscar_endereco_cliente(cliente_id.strip())
                    st.success("Cliente localizado.")
                except Exception as exc:
                    st.error(f"Nao foi possivel buscar o cliente: {exc}")
        dados.update(st.session_state.get("dados_cliente_gc", {}))
        dados = _selecionar_endereco(dados, "cliente")
        prefixo = "cliente"

    _form_entrega(rota_id, dados, prefixo)

    st.divider()
    st.subheader("Selecionar vendas e ordens do GestaoClick")
    st.caption("Busca Vendas > Produtos e, se marcado, Ordens de servico. Use os filtros para escolher o que entra na rota.")
    try:
        config_gc = gestaoclick_api.status_configuracao()
        try:
            loja = gestaoclick_api.obter_loja_alvo()
            loja_texto = f" | Loja {loja['nome']} ({loja['id']})"
        except Exception as exc:
            loja_texto = f" | Loja NOVAPRINT nao localizada: {exc}"
        st.caption(
            f"Integracao: URL {config_gc['url']} | Token "
            f"{'configurado' if config_gc['token_configurado'] else 'nao configurado'} | Secret token "
            f"{'configurado' if config_gc['secret_token_configurado'] else 'nao configurado'}"
            f"{loja_texto}"
        )
    except Exception:
        st.caption("Integracao: configuracao do GestaoClick nao localizada.")

    col_data, col_os, col_paginas = st.columns([2, 1, 1])
    data_inicio_gc = col_data.date_input("Filtrar a partir de", value=date.today().replace(day=1))
    incluir_os = col_os.checkbox("Incluir O.S.", value=True)
    max_paginas = col_paginas.number_input("Paginas", min_value=1, max_value=30, value=10, step=1)

    col_buscar, col_limpar = st.columns([2, 1])
    if col_buscar.button("Buscar pedidos disponiveis"):
        try:
            st.session_state["vendas_disponiveis_gc"] = gestaoclick_api.listar_pedidos_gestaoclick(
                data_inicio=data_inicio_gc,
                incluir_ordens_servico=incluir_os,
                max_paginas=int(max_paginas),
            )
            if not st.session_state["vendas_disponiveis_gc"]:
                st.warning("Nenhum pedido foi retornado pela API.")
            else:
                st.success(f"{len(st.session_state['vendas_disponiveis_gc'])} pedido(s) encontrado(s).")
        except Exception as exc:
            st.error(f"Nao foi possivel buscar os pedidos: {exc}")

    if col_limpar.button("Limpar lista"):
        st.session_state.pop("vendas_disponiveis_gc", None)
        st.rerun()

    vendas_disponiveis = st.session_state.get("vendas_disponiveis_gc", [])
    if vendas_disponiveis:
        tabela = pd.DataFrame(vendas_disponiveis)
        tabela = _filtrar_por_data(tabela, data_inicio_gc)
        situacoes_disponiveis = sorted([str(valor) for valor in tabela["situacao"].dropna().unique() if str(valor).strip()])
        origens_disponiveis = sorted([str(valor) for valor in tabela["origem"].dropna().unique() if str(valor).strip()])

        default_situacoes = [
            valor
            for valor in situacoes_disponiveis
            if valor.strip().lower() in (
                "em andamento",
                "pronta entrega",
            )
        ]

        filtro_col1, filtro_col2, filtro_col3 = st.columns([3, 2, 2])
        situacoes_filtradas = filtro_col1.multiselect(
            "Situacao",
            situacoes_disponiveis,
            default=default_situacoes,
        )
        origens_filtradas = filtro_col2.multiselect(
            "Origem",
            origens_disponiveis,
            default=origens_disponiveis,
        )
        busca_cliente = filtro_col3.text_input("Filtrar cliente")

        if situacoes_filtradas:
            tabela = tabela[tabela["situacao"].isin(situacoes_filtradas)]
        if origens_filtradas:
            tabela = tabela[tabela["origem"].isin(origens_filtradas)]
        if busca_cliente.strip():
            tabela = tabela[tabela["cliente"].str.contains(busca_cliente.strip(), case=False, na=False)]

        st.caption(
            f"Exibindo {len(tabela)} de {len(vendas_disponiveis)} pedido(s). "
            f"Origens: {', '.join(origens_disponiveis) if origens_disponiveis else 'sem origem'}. "
            f"Situacoes recebidas: {', '.join(situacoes_disponiveis) if situacoes_disponiveis else 'sem situacao'}."
        )

        if tabela.empty:
            st.warning("Nenhum pedido ficou dentro dos filtros selecionados.")
        else:
            tabela.insert(0, "selecionar", False)
            colunas = [
                "selecionar",
                "origem",
                "venda_id",
                "numero_venda",
                "cliente",
                "data",
                "valor_total",
                "telefone",
                "endereco",
                "cidade",
                "estado",
                "cep",
                "loja_id",
                "situacao",
            ]
            tabela = tabela[[coluna for coluna in colunas if coluna in tabela.columns]]
            editada = st.data_editor(
                tabela,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "selecionar": st.column_config.CheckboxColumn("Selecionar"),
                    "venda_id": "ID",
                    "numero_venda": "Numero",
                    "cliente": "Cliente",
                    "situacao": "Situacao",
                    "origem": "Origem",
                    "data": "Data",
                    "valor_total": "Valor",
                    "loja_id": "Loja",
                },
                disabled=[
                    coluna
                    for coluna in tabela.columns
                    if coluna not in ("selecionar", "endereco", "cidade", "estado", "cep")
                ],
                key="editor_vendas_gc",
            )

            selecionadas = editada[editada["selecionar"]].drop(columns=["selecionar"]).to_dict("records")
            if st.button("Adicionar selecionadas na rota", disabled=not selecionadas):
                total = 0
                sem_endereco = 0
                for venda in selecionadas:
                    dados_editados = dict(venda)
                    try:
                        venda_detalhada = gestaoclick_api.buscar_pedido_detalhado(
                            str(venda.get("origem", "")),
                            str(venda.get("venda_id", "")),
                        )
                        venda = {**venda, **venda_detalhada}
                        for campo in ("endereco", "cidade", "estado", "cep", "loja_id"):
                            if str(dados_editados.get(campo, "")).strip():
                                venda[campo] = dados_editados[campo]
                    except Exception as exc:
                        venda["observacao"] = (
                            f"{venda.get('observacao', '')} | Falha ao buscar detalhes/endereco: {exc}"
                        ).strip()

                    if not str(venda.get("cliente", "")).strip():
                        venda["cliente"] = "Cliente nao informado"
                    if not str(venda.get("endereco", "")).strip():
                        venda["endereco"] = "Endereco nao informado no GestaoClick"
                        sem_endereco += 1
                    adicionar_entrega(rota_id, {key: str(value or "") for key, value in venda.items()})
                    total += 1
                st.success(f"{total} entrega(s) adicionada(s) a rota.")
                if sem_endereco:
                    st.warning(f"{sem_endereco} entrega(s) entraram sem endereco retornado pela API.")
                st.rerun()

    st.subheader("Entregas desta rota")
    entregas = listar_entregas_rota(rota_id)
    if not entregas:
        st.info("Esta rota ainda nao tem entregas.")
        return
    _render_editor_endereco_rota(entregas)
    st.dataframe(entregas, use_container_width=True, hide_index=True)
