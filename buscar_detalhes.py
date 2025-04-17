# buscar_detalhes.py - Versão Otimizada
import asyncio
import json
import os
import logging
import random
from playwright.async_api import async_playwright
from busca_por_link import carregar_links_json
from collections import OrderedDict
from datetime import datetime

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, 'scraping.log')),
        logging.StreamHandler()
    ]
)

MAX_CONCURRENT_BROWSERS = 2
MAX_TABS_PER_BROWSER = 2
REQUEST_TIMEOUT = 5000
DELAY_RANGE = (0.05, 0.15)

def random_delay():
    return random.uniform(*DELAY_RANGE)

async def get_text(page, selector, timeout=3000):
    try:
        element = await page.wait_for_selector(selector, timeout=timeout, state="attached")
        return await page.evaluate('(el) => el.textContent.trim()', element) if element else "Não encontrado"
    except Exception:
        return "Não encontrado"

async def extrair_movs_concurrently(page, lista):
    return await asyncio.gather(*[_extrair_mov(page, m) for m in lista])

async def _extrair_mov(page, m):
    try:
        data_el = await m.query_selector(".dataMovimentacao")
        desc_el = await m.query_selector(".descricaoMovimentacao")
        if data_el and desc_el:
            data = await page.evaluate('(el) => el.textContent.trim()', data_el)
            desc = await page.evaluate('(el) => el.textContent.trim()', desc_el)
            return {"data": data, "descricao": desc}
    except:
        return None

async def buscar_detalhes_por_link(page, processo):
    dados_base = {"numero": processo.get("numero"), "link": processo.get("link"), "tribunal": processo.get("tribunal", "Desconhecido"), "timestamp_coleta": datetime.now().isoformat(), "classe": "Não disponível", "assunto": "Não disponível", "foro": "Não disponível", "vara": "Não disponível", "juiz": "Não disponível", "data_distribuicao": "Não disponível", "numero_controle": "Não disponível", "area": "Não disponível", "valor_acao": "Não disponível", "partes": [], "movimentacoes": [] }

    try:
        await page.set_viewport_size({"width": 1366, "height": 768})
        await page.set_extra_http_headers({'Accept-Language': 'pt-BR', 'User-Agent': 'Mozilla/5.0'})

        await page.goto(processo["link"], timeout=REQUEST_TIMEOUT, wait_until="domcontentloaded")

        actions = []
        for sel in ["#botaoExpandirDadosSecundarios", "#linkpartes"]:
            if await page.query_selector(sel):
                actions.append(page.click(sel, timeout=3000))
        if actions:
            await asyncio.gather(*actions)

        selectors = {"classe": "#classeProcesso", "assunto": "#assuntoProcesso", "foro": "#foroProcesso", "vara": "#varaProcesso", "juiz": "#juizProcesso", "data_distribuicao": "#dataHoraDistribuicaoProcesso", "numero_controle": "#numeroControleProcesso", "area": "#areaProcesso", "valor_acao": "#valorAcaoProcesso"}
        resultados = await asyncio.gather(*[get_text(page, sel) for sel in selectors.values()])
        for k, v in zip(selectors.keys(), resultados):
            dados_base[k] = v

        seletor_partes = "#tableTodasPartes tbody tr" if await page.query_selector("#tableTodasPartes tbody tr") else "#tablePartesPrincipais tbody tr"
        partes_data = []
        for parte in await page.query_selector_all(seletor_partes):
            try:
                tipo, nome = await asyncio.gather(parte.query_selector(".tipoDeParticipacao"), parte.query_selector(".nomeParte, .nomeParteEAdvogado"))
                if tipo and nome:
                    partes_data.append({"tipo": await page.evaluate('(el) => el.textContent.trim()', tipo), "nome": await page.evaluate('(el) => el.textContent.trim()', nome)})
            except:
                continue
        dados_base["partes"] = partes_data

        movs1, movs2 = await asyncio.gather(page.query_selector_all("#tabelaTodasMovimentacoes tbody tr"), page.query_selector_all("#tabelaUltimasMovimentacoes tr"))
        movs_raw = await extrair_movs_concurrently(page, movs2 + movs1)
        movs_unicos = list(OrderedDict.fromkeys((m["data"], m["descricao"]) for m in movs_raw if m))
        dados_base["movimentacoes"] = [{"data": d, "descricao": desc} for d, desc in movs_unicos]

        return dados_base

    except Exception as e:
        logging.warning(f"❌ Erro ao processar {processo['numero']}: {str(e)}")
        return {"erro": str(e), **dados_base}

async def worker(context, queue, results, errors):
    while True:
        processo = await queue.get()
        if processo is None:
            break
        page = await context.new_page()
        try:
            resultado = await buscar_detalhes_por_link(page, processo)
            (errors if "erro" in resultado else results).append(resultado)
        except Exception as e:
            errors.append({"numero": processo.get("numero"), "link": processo.get("link"), "tribunal": processo.get("tribunal"), "erro": str(e)})
        finally:
            await page.close()
            queue.task_done()

async def coletar_todos_detalhes(nome_empresa):
    processos = await carregar_links_json(nome_empresa)
    if not processos:
        raise ValueError("Nenhum processo encontrado para coletar detalhes")

    logging.info(f"Coletando detalhes de {len(processos)} processos para '{nome_empresa}'")

    detalhes, erros = [], []
    queue = asyncio.Queue()

    async with async_playwright() as p:
        browsers = [await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]) for _ in range(MAX_CONCURRENT_BROWSERS)]
        contexts = [await browser.new_context(locale='pt-BR') for browser in browsers]

        workers = [asyncio.create_task(worker(context, queue, detalhes, erros))
                   for context in contexts for _ in range(MAX_TABS_PER_BROWSER)]

        for proc in processos:
            await queue.put(proc)

        await queue.join()

        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers)

        for browser in browsers:
            await browser.close()

    return detalhes, erros
