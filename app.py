import streamlit as st
from dotenv import load_dotenv

from modules import configuracoes, dashboard, entregador, historico, rotas
from services.db import init_db
from services.rotas_service import autenticar_admin, autenticar_entregador


load_dotenv()
init_db()

st.set_page_config(
    page_title="Gestao de Entregas Novaprint",
    page_icon=":truck:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def aplicar_estilos() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        [data-testid="stMetricValue"] {font-size: 2rem;}
        div.stButton > button {
            width: 100%;
            min-height: 3rem;
            border-radius: 0.65rem;
            font-weight: 700;
        }
        div[data-testid="stForm"] {
            border: 1px solid rgba(49, 51, 63, .16);
            border-radius: .8rem;
            padding: 1rem;
        }
        .delivery-card {
            border: 1px solid rgba(49, 51, 63, .18);
            border-radius: .8rem;
            padding: 1rem;
            margin-bottom: .75rem;
            background: rgba(250, 250, 250, .85);
        }
        .small-muted {color: #6b7280; font-size: .9rem;}
        @media (max-width: 700px) {
            .block-container {padding-left: .75rem; padding-right: .75rem;}
            [data-testid="stSidebar"] {min-width: 17rem; max-width: 17rem;}
            h1 {font-size: 1.6rem;}
            h2 {font-size: 1.25rem;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def logout() -> None:
    for key in ["logado", "perfil", "usuario", "entregador_id", "entregador_nome"]:
        st.session_state.pop(key, None)
    st.rerun()


def tela_login() -> None:
    st.title("Gestao de Entregas")
    st.caption("Novaprint + GestaoClick")

    tab_admin, tab_entregador = st.tabs(["ADMIN", "ENTREGADOR"])

    with tab_admin:
        with st.form("login_admin"):
            usuario = st.text_input("Usuario")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar como ADMIN")

        if entrar:
            if autenticar_admin(usuario, senha):
                st.session_state["logado"] = True
                st.session_state["perfil"] = "ADMIN"
                st.session_state["usuario"] = usuario.strip()
                st.rerun()
            st.error("Usuario ou senha invalidos.")

    with tab_entregador:
        with st.form("login_entregador"):
            nome = st.text_input("Nome do entregador")
            codigo = st.text_input("Codigo de acesso", type="password")
            entrar = st.form_submit_button("Entrar como ENTREGADOR")

        if entrar:
            dados = autenticar_entregador(nome, codigo)
            if dados:
                st.session_state["logado"] = True
                st.session_state["perfil"] = "ENTREGADOR"
                st.session_state["usuario"] = dados["nome"]
                st.session_state["entregador_id"] = dados["id"]
                st.session_state["entregador_nome"] = dados["nome"]
                st.rerun()
            st.error("Entregador nao encontrado ou codigo invalido.")

    st.info(
        "Configure ADMIN_USER, ADMIN_PASSWORD e, para entregadores, cadastre o codigo de acesso em Configuracoes."
    )


def menu_admin() -> None:
    with st.sidebar:
        st.subheader("Menu")
        pagina = st.radio(
            "Selecione",
            ["Dashboard", "Rotas", "Painel do entregador", "Historico", "Configuracoes"],
            label_visibility="collapsed",
        )
        st.divider()
        st.write(f"Perfil: **{st.session_state['perfil']}**")
        if st.button("Sair"):
            logout()

    paginas = {
        "Dashboard": dashboard.render,
        "Rotas": rotas.render,
        "Painel do entregador": entregador.render,
        "Historico": historico.render,
        "Configuracoes": configuracoes.render,
    }
    paginas[pagina]()


def menu_entregador() -> None:
    with st.sidebar:
        st.subheader("Entrega")
        st.write(st.session_state.get("entregador_nome", "Entregador"))
        if st.button("Sair"):
            logout()
    entregador.render()


def main() -> None:
    aplicar_estilos()
    if not st.session_state.get("logado"):
        tela_login()
        return

    if st.session_state.get("perfil") == "ADMIN":
        menu_admin()
    else:
        menu_entregador()


if __name__ == "__main__":
    main()
