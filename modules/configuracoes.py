import streamlit as st

from services.rotas_service import excluir_entregador, listar_entregadores, salvar_entregador


def render() -> None:
    st.title("Configuracoes")
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
