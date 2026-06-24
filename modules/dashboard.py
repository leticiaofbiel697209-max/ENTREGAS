import streamlit as st

from services.rotas_service import indicadores_dashboard, historico_dataframe


def render() -> None:
    st.title("Dashboard")

    indicadores = indicadores_dashboard()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Pendentes", indicadores["pendentes"])
    col2.metric("Em rota", indicadores["em_rota"])
    col3.metric("Concluidas hoje", indicadores["concluidas_hoje"])
    col4.metric("Falhas", indicadores["falhas"])
    col5.metric("Ocorrencias", indicadores["ocorrencias"])

    st.divider()
    st.subheader("Ultimas movimentacoes")
    df = historico_dataframe()
    if df.empty:
        st.info("Ainda nao ha entregas registradas.")
        return
    st.dataframe(df.head(20), use_container_width=True, hide_index=True)
