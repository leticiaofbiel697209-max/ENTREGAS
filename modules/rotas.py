from datetime import date

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

    st.subheader("Entregas desta rota")
    entregas = listar_entregas_rota(rota_id)
    if not entregas:
        st.info("Esta rota ainda nao tem entregas.")
        return
    st.dataframe(entregas, use_container_width=True, hide_index=True)
