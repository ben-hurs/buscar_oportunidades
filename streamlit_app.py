import streamlit as st
import asyncio
import os
import json
import pandas as pd
import logging
import time
from datetime import timedelta
from busca_por_link import buscar_processos_por_nome
from buscar_detalhes import coletar_todos_detalhes
from busca_mpt import buscar_investigado_mpt

# Carrega a base de multas do IBAMA
ibama_df = pd.read_csv("ibama multas.csv", dtype=str)

# === Configuração geral do app ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
st.set_page_config(page_title="Consulta Judicial", layout="wide")
st.title("🔎 Consulta de Processos por Nome da Parte")
st.markdown("Pesquise processos nos tribunais **TJSP, TJAL e TJCE** usando o nome da parte ou empresa.")

# Função auxiliar
def limpar_valor(valor):
    try:
        if isinstance(valor, str):
            return float(valor.replace('R$', '').replace('.', '').replace(',', '.').strip())
        return float(valor)
    except:
        return 0.0

# === Layout da Interface ===
col1, col2 = st.columns(2)

with col1:
    nome_parte = st.text_input("Nome da empresa ou parte", placeholder="Ex: Natura, Coca Cola, etc")
    buscar_processos = st.button("Buscar processos e extrair detalhes")

with col2:
    cnpj_input = st.text_input("CNPJ para consulta IBAMA", placeholder="00.000.000/0001-00")
    consultar_ibama = st.button("Consultar IBAMA")

# === Consulta IBAMA ===
if consultar_ibama and cnpj_input:
    try:
        cnpj_limpo = cnpj_input.replace(".", "").replace("-", "").replace("/", "").strip()
        coluna_cnpj = None
        possiveis_nomes = ['CPF_CNPJ', 'CPF/CNPJ', 'CNPJ', 'CPF ou CNPJ', 'CPF_CNPJ_INFRATOR']
        for nome in possiveis_nomes:
            if nome in ibama_df.columns:
                coluna_cnpj = nome
                break
        if coluna_cnpj is None:
            st.warning("Não foi possível identificar a coluna de CNPJ no arquivo do IBAMA.")
        else:
            ibama_df["__cnpj_limpo__"] = ibama_df[coluna_cnpj].astype(str).str.replace(r"\D", "", regex=True)
            ibama_filtrado = ibama_df[ibama_df["__cnpj_limpo__"] == cnpj_limpo]
            if not ibama_filtrado.empty:
                st.success(f"⚠️ {len(ibama_filtrado)} multa(s) do IBAMA encontradas para este CNPJ.")
                st.dataframe(ibama_filtrado.drop(columns="__cnpj_limpo__"), use_container_width=True)
                st.download_button(
                    label="📥 Baixar multas IBAMA (CSV)",
                    data=ibama_filtrado.drop(columns="__cnpj_limpo__").to_csv(index=False),
                    file_name=f"ibama_{cnpj_limpo}.csv",
                    mime="text/csv"
                )
            else:
                st.info("✅ Nenhuma multa encontrada no IBAMA para este CNPJ.")
    except Exception as e_ibama:
        st.warning(f"⚠️ Erro ao buscar dados do IBAMA: {str(e_ibama)}")
        st.warning(f"Colunas disponíveis no arquivo: {list(ibama_df.columns)}")

# === Inicialização do Session State ===
if "detalhes" not in st.session_state:
    st.session_state.detalhes = None
if "erros" not in st.session_state:
    st.session_state.erros = None
if "links" not in st.session_state:
    st.session_state.links = None
if "tempos" not in st.session_state:
    st.session_state.tempos = {}

# === Busca de Processos ===
if buscar_processos and nome_parte:
    async def run_busca():
        os.makedirs("data", exist_ok=True)
        inicio_total = time.time()

        inicio_links = time.time()
        with st.spinner("🔄 Buscando links dos processos..."):
            links = await buscar_processos_por_nome(nome_parte)
        tempo_links = time.time() - inicio_links

        inicio_detalhes = time.time()
        with st.spinner("📄 Coletando detalhes dos processos..."):
            detalhes, erros = await coletar_todos_detalhes(nome_parte)
        tempo_detalhes = time.time() - inicio_detalhes
        tempo_total = time.time() - inicio_total

        with st.spinner("⚖️ Buscando investigações no MPT..."):
            df_mpt = buscar_investigado_mpt(nome_parte)
            st.session_state.df_mpt = df_mpt

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
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_busca())
    except Exception as e:
        logging.error(f"Erro ao iniciar o loop de eventos: {e}")
        st.error(f"Erro ao buscar processos: {str(e)}")


# === Visualização dos Resultados ===
if st.session_state.detalhes:
    # Mostra métricas de tempo
    if st.session_state.get('tempos'):
        tempos = st.session_state.tempos
        col1, col2, col3, col4 = st.columns(4)
        
        # Função segura para formatar tempo
        def format_tempo(segundos):
            try:
                return str(timedelta(seconds=int(segundos)))[:7]
            except (TypeError, ValueError):
                return "00:00"
        
        # Tempo Total
        with col1:
            tempo_total = tempos.get("total", 0)
            st.metric("⏱ Tempo Total", 
                     format_tempo(tempo_total),
                     help="Tempo total da busca e coleta")
        
        # Tempo Busca Links
        with col2:
            tempo_links = tempos.get("links", 0)
            st.metric("🔗 Tempo Busca Links", 
                     format_tempo(tempo_links),
                     help="Tempo para encontrar os links dos processos")
        
        # Tempo Coleta Detalhes
        with col3:
            tempo_detalhes = tempos.get("detalhes", 0)
            st.metric("📄 Tempo Coleta Detalhes", 
                     format_tempo(tempo_detalhes),
                     help="Tempo para coletar detalhes de todos os processos")
        
        # Velocidade (proc/min)
        with col4:
            try:
                processos_coletados = tempos.get('processos_coletados', 0)
                velocidade = int(processos_coletados / (tempo_detalhes / 60)) if tempo_detalhes > 0 else 0
                st.metric("⚡ Velocidade (proc/min)", 
                         f"{velocidade}",
                         help="Processos coletados por minuto")
            except ZeroDivisionError:
                st.metric("⚡ Velocidade (proc/min)", 
                         "0",
                         help="Processos coletados por minuto")
    
    # Processa os dados como antes
    df = pd.json_normalize(st.session_state.detalhes)
    df["valor_acao_float"] = df["valor_acao"].apply(limpar_valor)

    # Adiciona informações de links se disponíveis
    if st.session_state.links:
        links_df = pd.json_normalize(st.session_state.links)
        links_df = links_df.rename(columns={"partes": "partes_links"})
        df = df.merge(links_df[["numero", "partes_links"]], on="numero", how="left")

        # Filtros na sidebar
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

    # Salva os resultados
    nome_formatado = nome_parte.lower().replace(" ", "_")
    df.to_csv(f"data/detalhes_{nome_formatado}.csv", index=False)

    # Quantidade de Processos encontrados
    st.success(f"✅ {len(df)} processos filtrados para '{nome_parte}'")

    # Visualizações gráficas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Quantidade x Classe")
        df_qtd_classe = df["classe"].value_counts().reset_index().head(10)
        df_qtd_classe.columns = ["classe", "quantidade"]
        st.bar_chart(df_qtd_classe, x="classe", y="quantidade", horizontal=True)

    with col2:
        st.subheader("Quantidade x Assunto")
        df_qtd_assunto = df["assunto"].value_counts().reset_index().head(10)
        df_qtd_assunto.columns = ["assunto", "quantidade"]
        st.bar_chart(df_qtd_assunto, x="assunto", y="quantidade", horizontal=True)

    with col3:
        st.subheader("Quantidade x Vara")
        df_qtd_vara = df["vara"].value_counts().reset_index().head(10)
        df_qtd_vara.columns = ["vara", "quantidade"]
        st.bar_chart(df_qtd_vara, x="vara", y="quantidade", horizontal=True)

    col4, col5, col6 = st.columns(3)
    with col4:
        st.subheader("Valor da Ação x Classe")
        df_valor_classe = df.groupby("classe")["valor_acao_float"].sum().reset_index().head(10)
        df_valor_classe.columns = ["classe", "valor"]
        st.bar_chart(df_valor_classe, x="classe", y="valor", horizontal=True)

    with col5:
        st.subheader("Valor da Ação x Assunto")
        df_valor_assunto = df.groupby("assunto")["valor_acao_float"].sum().reset_index().head(10)
        df_valor_assunto.columns = ["assunto", "valor"]
        st.bar_chart(df_valor_assunto, x="assunto", y="valor", horizontal=True)

    with col6:
        st.subheader("Valor da Ação x Vara")
        df_valor_vara = df.groupby("vara")["valor_acao_float"].sum().reset_index().head(10)
        df_valor_vara.columns = ["vara", "valor"]
        st.bar_chart(df_valor_vara, x="vara", y="valor", horizontal=True)

    # Resultados e download
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "📥 Baixar CSV com detalhes",
        data=df.to_csv(index=False),
        file_name=f"detalhes_{nome_formatado}.csv",
        mime="text/csv"
    )

    # Exibir dados do MPT
    if "df_mpt" in st.session_state and not st.session_state.df_mpt.empty:
        st.subheader("⚖️ Processos investigativos no MPT")
        st.dataframe(st.session_state.df_mpt, use_container_width=True)

        st.download_button(
            label="📥 Baixar dados do MPT",
            data=st.session_state.df_mpt.to_csv(index=False),
            file_name=f"mpt_{nome_parte.lower().replace(' ', '_')}.csv",
            mime="text/csv"
        )
    elif "df_mpt" in st.session_state:
        st.info("✅ Nenhuma investigação encontrada no MPT para este nome.")


# Mostra erros se houver
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