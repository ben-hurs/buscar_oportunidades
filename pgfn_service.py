# pgfn_service.py
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def consultar_pgfn(cnpj, headless=True, timeout=30):
    """
    Consulta a lista de devedores da PGFN com Selenium + ChromeDriver padrão

    Args:
        cnpj (str): CNPJ a ser consultado
        headless (bool): Executa ou não em modo headless
        timeout (int): Tempo máximo de espera

    Returns:
        dict: Resultado da consulta
    """
    options = Options()
    if headless:
        options.add_argument("--headless=new")  # Compatível com Chrome 109+
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        logging.info("Acessando o site da PGFN...")
        driver.get("https://www.listadevedores.pgfn.gov.br/")
        time.sleep(3)

        wait = WebDriverWait(driver, timeout)
        input_cnpj = wait.until(EC.presence_of_element_located((By.ID, "identificacaoInput")))
        input_cnpj.clear()

        # Digitação suave
        for char in cnpj:
            input_cnpj.send_keys(char)
            time.sleep(0.1)

        botao = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "btn-warning")))
        botao.click()

        logging.info("Aguardando resultados...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                mensagem = driver.find_element(By.CSS_SELECTOR, "p.total-mensagens")
                if "Nenhum registro foi encontrado" in mensagem.text:
                    logging.info("Nenhuma dívida encontrada")
                    return {"status": "sem divida"}

                linha = driver.find_element(By.CSS_SELECTOR, "tr.ng-star-inserted")
                colunas = linha.find_elements(By.TAG_NAME, "td")
                if len(colunas) >= 4:
                    logging.info("Dívida encontrada")
                    return {
                        "status": "com divida",
                        "cnpj": colunas[1].text.strip(),
                        "nome": colunas[2].text.strip(),
                        "valor": colunas[3].text.strip()
                    }
            except NoSuchElementException:
                time.sleep(1)
                continue

        logging.warning("Timeout ao aguardar resultados")
        return {"status": "erro", "mensagem": "Timeout ao aguardar resultados"}

    except Exception as e:
        logging.error(f"Erro durante a consulta: {str(e)}")
        return {"status": "erro", "mensagem": str(e)}

    finally:
        driver.quit()
        logging.info("Navegador fechado")
