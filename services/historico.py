from datetime import date, timedelta

import streamlit as st

from services.rotas_service import historico_dataframe, listar_entregadores


def render() -> None:
    st.title("Historico")

    entregadores = listar_entregadores()
    nomes = ["Todos"] + [item["nome"] for item in entregadores]
    status_opcoes = ["Todos", "PENDENTE", "EM ROTA", "ENTREGUE", "FALHA"]

    col1, col2, col3, col4 = st.columns(4)
    data_inicio = col1.date_input("Data inicial", value=date.today() - timedelta(days=30))
    data_fim = col2.date_input("Data final", value=date.today())
    entregador = col3.selectbox("Entregador", nomes)
    status = col4.selectbox("Status", status_opcoes)
    cliente = st.text_input("Cliente")

    df = historico_dataframe(
        data_inicio=data_inicio,
        data_fim=data_fim,
        entregador=None if entregador == "Todos" else entregador,
        cliente=cliente.strip() or None,
        status=None if status == "Todos" else status,
    )

    if df.empty:
        st.info("Nenhum registro encontrado para os filtros.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Baixar CSV",
        data=csv,
        file_name="historico_entregas.csv",
        mime="text/csv",
    )
