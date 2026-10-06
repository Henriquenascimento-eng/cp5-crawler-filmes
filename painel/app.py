"""
Dashboard — visualização dos dados coletados.
Consome os dados EXCLUSIVAMENTE pela API (FastAPI), nunca acessa o
MongoDB diretamente.
"""
import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Maiores Bilheterias — Dashboard", layout="wide")
st.title("🎬 Dashboard — Maiores Bilheterias de Todos os Tempos")


@st.cache_data(ttl=60)
def carregar_estatisticas():
    resp = requests.get(f"{API_BASE_URL}/estatisticas", timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=60)
def carregar_filmes(genero: str = None, ano: int = None):
    params = {}
    if genero:
        params["genero"] = genero
    if ano:
        params["ano"] = ano

    if params:
        resp = requests.get(f"{API_BASE_URL}/filmes/buscar", params=params, timeout=10)
    else:
        resp = requests.get(f"{API_BASE_URL}/filmes", params={"limit": 250}, timeout=10)

    resp.raise_for_status()
    return resp.json()["filmes"]


try:
    stats = carregar_estatisticas()
except requests.exceptions.RequestException:
    st.error(
        f"Não foi possível conectar à API em {API_BASE_URL}. "
        "Verifique se ela está rodando (veja o README)."
    )
    st.stop()

if stats.get("total_filmes", 0) == 0:
    st.warning(
        "Ainda não há dados coletados. Rode o crawler primeiro: "
        "`python coleta/crawler_wiki.py`"
    )
    st.stop()

# --- Indicadores ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total de filmes", stats["total_filmes"])
col2.metric("Bilheteria média", f"${stats['bilheteria_media']:,.0f}")
col3.metric("Duração média (min)", stats["duracao_media_min"])
col4.metric("Período", f"{stats['ano_mais_antigo']}–{stats['ano_mais_recente']}")

st.divider()

# --- Filtros ---
st.sidebar.header("Filtros")
generos_disponiveis = sorted(g["genero"] for g in stats["distribuicao_generos"])
genero_filtro = st.sidebar.selectbox("Gênero", ["Todos"] + generos_disponiveis)
ano_filtro = st.sidebar.number_input("Ano (0 = todos)", min_value=0, max_value=2100, value=0)

filmes = carregar_filmes(
    genero=None if genero_filtro == "Todos" else genero_filtro,
    ano=None if ano_filtro == 0 else int(ano_filtro),
)
df = pd.DataFrame(filmes)

# --- Gráficos ---
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Distribuição por gênero")
    df_generos = pd.DataFrame(stats["distribuicao_generos"])
    fig_generos = px.bar(df_generos, x="genero", y="quantidade")
    st.plotly_chart(fig_generos, use_container_width=True)

with col_b:
    st.subheader("Bilheteria x Ano de lançamento")
    if not df.empty:
        fig_dispersao = px.scatter(df, x="ano", y="bilheteria_mundial", hover_name="titulo")
        st.plotly_chart(fig_dispersao, use_container_width=True)

# --- Tabela ---
st.subheader("Filmes")
if not df.empty:
    colunas = [
        "posicao_ranking", "titulo", "ano", "bilheteria_mundial",
        "generos", "duracao_min", "diretor",
    ]
    colunas_existentes = [c for c in colunas if c in df.columns]
    st.dataframe(
        df[colunas_existentes].sort_values("posicao_ranking"),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Nenhum filme encontrado para esse filtro.")
