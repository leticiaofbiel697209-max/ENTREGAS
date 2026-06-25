import json

import json

import streamlit as st

from services import gestaoclick_api
from services.rotas_service import (
    listar_entregadores,
    listar_entregas_entregador,
    obter_entrega,
    registrar_entrega_concluida,
    registrar_falha,
    registrar_ocorrencia,
)


def _entregador_atual_admin() -> int | None:
    entregadores = listar_entregadores()
    if not entregadores:
        st.info("Nenhum entregador cadastrado.")
        return None
    nomes = {item["nome"]: item["id"] for item in entregadores}
    selecionado = st.selectbox("Visualizar entregas de", list(nomes.keys()))
    return int(nomes[selecionado])


def _pode_operar(entrega: dict) -> bool:
    if st.session_state.get("perfil") == "ADMIN":
        return True
    return int(entrega["entregador_id"]) == int(st.session_state.get("entregador_id", 0))


def _form_entregue(entrega: dict) -> None:
    with st.form(f"entregue_{entrega['id']}"):
        recebido_por = st.text_input("Nome de quem recebeu")
        observacao = st.text_area("Observacao")
        confirmar = st.form_submit_button("Confirmar ENTREGUE")

    if confirmar:
        if not recebido_por.strip():
            st.error("Informe quem recebeu.")
            return

        api_retorno = {}
        origem_pedido = str(entrega.get("origem_pedido") or "").lower()
        if entrega.get("venda_id") and origem_pedido != "ordem_servico":
            try:
                api_retorno = gestaoclick_api.atualizar_status_venda(
                    entrega["venda_id"],
                    "ENTREGUE",
                    recebido_por=recebido_por.strip(),
                )
            except Exception as exc:
                api_retorno = {"erro": str(exc)}
        elif origem_pedido == "ordem_servico":
            api_retorno = {"info": "Origem ordem_servico: status atualizado apenas no controle de entregas."}

        registrar_entrega_concluida(
            entrega["id"],
            recebido_por,
            observacao,
            st.session_state.get("usuario", ""),
            json.dumps(api_retorno, ensure_ascii=False),
        )
        if api_retorno.get("erro"):
            st.warning("Entrega salva, mas o GestaoClick retornou erro. Veja o historico da API no banco.")
        else:
            st.success("Entrega concluida e GestaoClick atualizado.")
        st.rerun()


def _form_falha(entrega: dict) -> None:
    with st.form(f"falha_{entrega['id']}"):
        motivo = st.selectbox(
            "Motivo",
            ["Cliente ausente", "Endereco incorreto", "Recusou recebimento", "Outro"],
        )
        observacao = st.text_area("Observacao")
        confirmar = st.form_submit_button("Confirmar FALHA")

    if confirmar:
        registrar_falha(entrega["id"], motivo, observacao, st.session_state.get("usuario", ""))
        st.success("Falha registrada.")
        st.rerun()


def _form_ocorrencia(entrega: dict) -> None:
    with st.form(f"ocorrencia_{entrega['id']}"):
        descricao = st.text_area("Descreva a ocorrencia")
        confirmar = st.form_submit_button("Salvar OCORRENCIA")

    if confirmar:
        if not descricao.strip():
            st.error("Descreva a ocorrencia.")
            return
        registrar_ocorrencia(entrega["id"], descricao, st.session_state.get("usuario", ""))
        st.success("Ocorrencia registrada.")
        st.rerun()


def _card_entrega(entrega: dict) -> None:
    st.markdown(
        f"""
        <div class="delivery-card">
            <h3>{entrega['cliente']}</h3>
            <p><strong>Venda:</strong> {entrega.get('numero_venda') or entrega.get('venda_id') or '-'}</p>
            <p><strong>Endereco:</strong> {entrega['endereco']} - {entrega.get('cidade') or ''}/{entrega.get('estado') or ''}</p>
            <p><strong>Telefone:</strong> {entrega.get('telefone') or '-'}</p>
            <p><strong>Status:</strong> {entrega['status']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not _pode_operar(entrega):
        st.warning("Esta entrega nao pertence ao usuario logado.")
        return

    acao = st.radio(
        "Acao",
        ["ENTREGUE", "FALHA", "OCORRENCIA"],
        horizontal=True,
        key=f"acao_{entrega['id']}",
    )
    entrega_atual = obter_entrega(entrega["id"])
    if not entrega_atual:
        st.error("Entrega nao encontrada.")
        return

    if acao == "ENTREGUE":
        _form_entregue(entrega_atual)
    elif acao == "FALHA":
        _form_falha(entrega_atual)
    else:
        _form_ocorrencia(entrega_atual)


def render() -> None:
    st.title("Painel do entregador")

    if st.session_state.get("perfil") == "ADMIN":
        entregador_id = _entregador_atual_admin()
    else:
        entregador_id = st.session_state.get("entregador_id")

    if not entregador_id:
        return

    entregas = listar_entregas_entregador(int(entregador_id))
    if not entregas:
        st.info("Nao ha entregas atribuidas para este entregador.")
        return

    for entrega in entregas:
        _card_entrega(entrega)
