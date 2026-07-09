import streamlit as st

from services import gestaoclick_api
from services.db import obter_config, salvar_config
from services.rotas_service import excluir_entregador, listar_entregadores, salvar_entregador


def render() -> None:
    st.title("Configuracoes")
    st.subheader("GestaoClick")

    status_atual_id = obter_config("GESTAOCLICK_STATUS_ENTREGUE_ID", "")
    if status_atual_id:
        st.success(f"Status real de entrega configurado: ID {status_atual_id}")
    else:
        st.warning("Status real de entrega ainda nao configurado. O app nao vai confirmar entrega sem este ID.")

    if st.button("Buscar situacoes de vendas no GestaoClick"):
        try:
            st.session_state["situacoes_vendas_gc"] = gestaoclick_api.listar_situacoes_vendas()
            st.success("Situacoes carregadas.")
        except Exception as exc:
            st.error(f"Nao foi possivel buscar as situacoes: {exc}")

    situacoes = st.session_state.get("situacoes_vendas_gc", [])
    if situacoes:
        opcoes = {
            f"{item.get('id')} - {item.get('nome')}": item.get("id", "")
            for item in situacoes
            if item.get("id")
        }
        escolha = st.selectbox(
            "Escolha a situacao REAL que deve ser usada quando a entrega for confirmada",
            list(opcoes.keys()),
        )
        if st.button("Salvar situacao real de entrega"):
            salvar_config("GESTAOCLICK_STATUS_ENTREGUE_ID", str(opcoes[escolha]))
            st.success(f"Situacao de entrega salva: {escolha}")
            st.rerun()

    st.divider()
    st.subheader("Entregadores")

    with st.form("form_entregador"):
        nome = st.text_input("Nome")
        codigo = st.text_input("Codigo de acesso", type="password")
        salvar = st.form_submit_button("Salvar entregador")

    if salvar:
        if not nome.strip() or not codigo.strip():
            st.error("Informe nome e codigo de acesso.")
        else:
            salvar_entregador(nome, codigo)
            st.success("Entregador salvo.")
            st.rerun()

    entregadores = listar_entregadores()
    if not entregadores:
        st.info("Nenhum entregador cadastrado.")
        return

    for item in entregadores:
        col_nome, col_status, col_btn = st.columns([3, 2, 1])
        col_nome.write(item["nome"])
        col_status.caption("Codigo cadastrado" if item.get("codigo_acesso") else "Sem codigo")
        if col_btn.button("Excluir", key=f"excluir_entregador_{item['id']}"):
            excluir_entregador(item["id"])
            st.success("Entregador excluido.")
            st.rerun()
