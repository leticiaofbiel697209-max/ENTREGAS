from datetime import date

import pandas as pd
import streamlit as st

from services import gestaoclick_api
from services.rotas_service import (
    adicionar_entrega,
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


def _form_entrega(rota_id: int, dados: dict[str, str], prefixo: str) -> None:
    with st.form(f"form_entrega_{prefixo}"):
        col1, col2 = st.columns(2)
        venda_id = col1.text_input("ID da venda", value=dados.get("venda_id", ""))
        numero_venda = col2.text_input("Numero da venda", value=dados.get("numero_venda", ""))
        cliente = st.text_input("Cliente", value=dados.get("cliente", ""))
        telefone = st.text_input("Telefone", value=dados.get("telefone", ""))
        endereco = st.text_area("Endereco", value=dados.get("endereco", ""))
        col3, col4, col5 = st.columns([2, 1, 1])
        cidade = col3.text_input("Cidade", value=dados.get("cidade", ""))
        estado = col4.text_input("Estado", value=dados.get("estado", ""))
        cep = col5.text_input("CEP", value=dados.get("cep", ""))
        observacao = st.text_area("Observacao", value=dados.get("observacao", ""))
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
        ["Digitar manualmente", "Buscar endereco da venda", "Buscar endereco do cliente"],
        horizontal=True,
    )

    dados = _dados_vazios()
    prefixo = "manual"

    if origem == "Buscar endereco da venda":
        venda_id = st.text_input("Informe o ID da venda no GestaoClick")
        if st.button("Buscar venda"):
            if not venda_id.strip():
                st.error("Informe o ID da venda.")
            else:
                try:
                    st.session_state["dados_venda_gc"] = gestaoclick_api.buscar_endereco_venda(venda_id.strip())
                    st.success("Venda localizada.")
                except Exception as exc:
                    st.error(f"Nao foi possivel buscar a venda: {exc}")
        dados.update(st.session_state.get("dados_venda_gc", {}))
        prefixo = "venda"

    elif origem == "Buscar endereco do cliente":
        cliente_id = st.text_input("Informe o ID do cliente no GestaoClick")
        if st.button("Buscar cliente"):
            if not cliente_id.strip():
                st.error("Informe o ID do cliente.")
            else:
                try:
                    st.session_state["dados_cliente_gc"] = gestaoclick_api.buscar_endereco_cliente(cliente_id.strip())
                    st.success("Cliente localizado.")
                except Exception as exc:
                    st.error(f"Nao foi possivel buscar o cliente: {exc}")
        dados.update(st.session_state.get("dados_cliente_gc", {}))
        prefixo = "cliente"

    _form_entrega(rota_id, dados, prefixo)

    st.divider()
    st.subheader("Selecionar vendas do GestaoClick")
    st.caption("Lista vendas com situacao em andamento ou pronta entrega.")
    try:
        config_gc = gestaoclick_api.status_configuracao()
        st.caption(
            f"Integracao: URL {config_gc['url']} | Token "
            f"{'configurado' if config_gc['token_configurado'] else 'nao configurado'}"
        )
    except Exception:
        st.caption("Integracao: configuracao do GestaoClick nao localizada.")

    col_buscar, col_limpar = st.columns([2, 1])
    if col_buscar.button("Buscar vendas disponiveis"):
        try:
            st.session_state["vendas_disponiveis_gc"] = gestaoclick_api.listar_vendas_por_situacoes()
            if not st.session_state["vendas_disponiveis_gc"]:
                st.warning("Nenhuma venda em andamento ou pronta entrega foi encontrada.")
            else:
                st.success(f"{len(st.session_state['vendas_disponiveis_gc'])} venda(s) encontrada(s).")
        except Exception as exc:
            st.error(f"Nao foi possivel buscar as vendas: {exc}")

    if col_limpar.button("Limpar lista"):
        st.session_state.pop("vendas_disponiveis_gc", None)
        st.rerun()

    vendas_disponiveis = st.session_state.get("vendas_disponiveis_gc", [])
    if vendas_disponiveis:
        tabela = pd.DataFrame(vendas_disponiveis)
        tabela.insert(0, "selecionar", False)
        colunas = [
            "selecionar",
            "venda_id",
            "numero_venda",
            "cliente",
            "telefone",
            "endereco",
            "cidade",
            "estado",
            "cep",
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
                "numero_venda": "Venda",
                "cliente": "Cliente",
                "situacao": "Situacao",
            },
            disabled=[coluna for coluna in tabela.columns if coluna != "selecionar"],
            key="editor_vendas_gc",
        )

        selecionadas = editada[editada["selecionar"]].drop(columns=["selecionar"]).to_dict("records")
        if st.button("Adicionar selecionadas na rota", disabled=not selecionadas):
            total = 0
            ignoradas = 0
            for venda in selecionadas:
                if not str(venda.get("cliente", "")).strip() or not str(venda.get("endereco", "")).strip():
                    ignoradas += 1
                    continue
                adicionar_entrega(rota_id, {key: str(value or "") for key, value in venda.items()})
                total += 1
            st.success(f"{total} entrega(s) adicionada(s) a rota.")
            if ignoradas:
                st.warning(f"{ignoradas} venda(s) foram ignoradas por falta de cliente ou endereco.")
            st.rerun()

    st.subheader("Entregas desta rota")
    entregas = listar_entregas_rota(rota_id)
    if not entregas:
        st.info("Esta rota ainda nao tem entregas.")
        return
    st.dataframe(entregas, use_container_width=True, hide_index=True)
