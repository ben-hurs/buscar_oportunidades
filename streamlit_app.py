import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import nest_asyncio
nest_asyncio.apply()

import os
import pandas as pd
import logging
import time
from datetime import timedelta
from playwright.async_api import async_playwright
from busca_link_processos import buscar_processos_por_nome
from busca_detalhes_processos import coletar_detalhes_concorrente
import matplotlib.pyplot as plt

os.system("playwright install chromium")



nest_asyncio.apply()

# === Configuração geral do app ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
st.set_page_config(page_title="Consulta Judicial", layout="wide")
st.title("🔎 Consulta de Processos por Nome da Parte")
st.markdown("Pesquise processos nos tribunais **TJSP, TJAL e TJCE** usando o nome da parte ou empresa.")

def limpar_valor(valor):
    try:
        if isinstance(valor, str):
            return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
        return float(valor)
    except:
        return 0.0

# === Layout da Interface ===
nome_parte = st.text_input("Nome da empresa ou parte", placeholder="Ex: Natura, Coca Cola, etc")
buscar_processos = st.button("Buscar processos e extrair detalhes")

# === Inicialização do Session State ===
for key in ["detalhes", "erros", "links", "tempos"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "tempos" else {}

# === Busca de Processos ===
if buscar_processos and nome_parte:
    async def run_busca():
        os.makedirs("data", exist_ok=True)
        inicio_total = time.time()

        # Busca de links
        inicio_links = time.time()
        with st.spinner("Buscando links dos processos..."):
            links = await buscar_processos_por_nome(nome_parte)
        tempo_links = time.time() - inicio_links

        # Coleta de detalhes
        inicio_detalhes = time.time()
        with st.spinner("📄 Coletando detalhes dos processos..."):
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(locale="pt-BR", timezone_id="America/Sao_Paulo")
                detalhes = await coletar_detalhes_concorrente(context, links, limite_concorrencia=5)
                await browser.close()
                erros = []

        tempo_detalhes = time.time() - inicio_detalhes
        tempo_total = time.time() - inicio_total

        st.session_state.tempos = {
            "total": tempo_total,
            "links": tempo_links,
            "detalhes": tempo_detalhes,
            "processos_encontrados": len(links),
            "processos_coletados": len(detalhes)
        }

        st.session_state.links = links
        st.session_state.detalhes = detalhes
        st.session_state.erros = erros

    try:
        asyncio.run(run_busca())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_busca())
    except Exception as e:
        logging.error(f"Erro ao buscar processos: {e}")
        st.error(f"Erro ao buscar processos: {str(e)}")

# === Visualização dos Resultados ===
if st.session_state.detalhes:
    if st.session_state.get('tempos'):
        tempos = st.session_state.tempos
        col1, col2, col3, col4 = st.columns(4)

        def format_tempo(segundos):
            try:
                return str(timedelta(seconds=int(segundos)))[:7]
            except:
                return "00:00"

        with col1:
            st.metric("⏱ Tempo Total", format_tempo(tempos.get("total", 0)))
        with col2:
            st.metric("🔗 Tempo Links", format_tempo(tempos.get("links", 0)))
        with col3:
            st.metric("📄 Tempo Detalhes", format_tempo(tempos.get("detalhes", 0)))
        with col4:
            try:
                velocidade = int(tempos['processos_coletados'] / (tempos['detalhes'] / 60)) if tempos['detalhes'] > 0 else 0
                st.metric("⚡ Velocidade (proc/min)", f"{velocidade}")
            except:
                st.metric("⚡ Velocidade (proc/min)", "0")

    df = pd.json_normalize(st.session_state.detalhes)
    df["valor_acao_float"] = df["valor_acao"].apply(limpar_valor)

    if st.session_state.links:
        links_df = pd.json_normalize(st.session_state.links)
        links_df = links_df.rename(columns={"partes": "partes_links"})
        df = df.merge(links_df[["numero", "partes_links"]], left_on="numero_processo", right_on="numero", how="left")
        df = df.drop(columns=["numero"])


        if not df["partes_links"].empty:
            todas_partes = [p for sublist in df["partes_links"] if isinstance(sublist, list) for p in sublist if isinstance(p, dict)]
            if todas_partes:
                partes_df = pd.DataFrame(todas_partes)
                tipo_options = sorted(partes_df["tipo"].dropna().unique())
                nome_options = sorted(partes_df["nome"].dropna().unique())

                with st.sidebar:
                    st.header("🔎 Filtros")
                    tipos_selecionados = st.multiselect("Tipo de participação", options=tipo_options, default=tipo_options)
                    nomes_selecionados = st.multiselect("Nome da parte", options=nome_options, default=nome_options)

                def parte_match(partes):
                    if not isinstance(partes, list):
                        return False
                    for p in partes:
                        if isinstance(p, dict) and p.get("tipo") in tipos_selecionados and p.get("nome") in nomes_selecionados:
                            return True
                    return False

                df = df[df["partes_links"].apply(parte_match)]

    nome_formatado = nome_parte.lower().replace(" ", "_")
    df.to_csv(f"data/detalhes_{nome_formatado}.csv", index=False)

    st.success(f"✅ {len(df)} processos filtrados para '{nome_parte}'")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Qtd x Classe")
        classe = df["classe"].value_counts().reset_index().head(10)
        classe.columns = ["classe", "quantidade"]
        st.bar_chart(classe, x="classe", y="quantidade", horizontal=True)
    with col2:
        st.subheader("Qtd x Assunto")
        assunto = df["assunto"].value_counts().reset_index().head(10)
        assunto.columns = ["assunto", "quantidade"]
        st.bar_chart(assunto, x="assunto", y="quantidade", horizontal=True)
    with col3:
        st.subheader("Qtd x Vara")
        vara = df["vara"].value_counts().reset_index().head(10)
        vara.columns = ["vara", "quantidade"]
        st.bar_chart(vara, x="vara", y="quantidade", horizontal=True)

    col4, col5, col6 = st.columns(3)
    with col4:
        st.subheader("Valor x Classe")
        valor_classe = df.groupby("classe")["valor_acao_float"].sum().reset_index().head(10)
        st.bar_chart(valor_classe, x="classe", y="valor_acao_float", horizontal=True)
    with col5:
        st.subheader("Valor x Assunto")
        valor_assunto = df.groupby("assunto")["valor_acao_float"].sum().reset_index().head(10)
        st.bar_chart(valor_assunto, x="assunto", y="valor_acao_float", horizontal=True)
    with col6:
        st.subheader("Valor x Vara")
        valor_vara = df.groupby("vara")["valor_acao_float"].sum().reset_index().head(10)
        st.bar_chart(valor_vara, x="vara", y="valor_acao_float", horizontal=True)

    st.dataframe(df, use_container_width=True)
    st.download_button(
        "📥 Baixar CSV com detalhes",
        data=df.to_csv(index=False),
        file_name=f"detalhes_{nome_formatado}.csv",
        mime="text/csv"
    )

# Erros
if st.session_state.erros:
    df_erros = pd.DataFrame(st.session_state.erros)
    st.warning(f"⚠️ {len(df_erros)} erros durante a coleta")
    st.dataframe(df_erros, use_container_width=True)
    st.download_button(
        "📥 Baixar CSV com erros",
        data=df_erros.to_csv(index=False),
        file_name=f"erros_{nome_parte.lower().replace(' ', '_')}.csv",
        mime="text/csv"
    )
