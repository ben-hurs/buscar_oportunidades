# pgfn_service.py
import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import undetected_chromedriver as uc
from fake_useragent import UserAgent

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_chrome_version():
    """Tenta detectar a versão instalada do Chrome"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as key:
            version = winreg.QueryValueEx(key, "version")[0]
            return int(version.split('.')[0])
    except:
        return None

def consultar_pgfn(cnpj, headless=True, timeout=30):
    """
    Consulta a lista de devedores da PGFN com tratamento de versão do Chrome
    
    Args:
        cnpj (str): CNPJ a ser consultado
        headless (bool): Se True, executa em modo headless
        timeout (int): Tempo máximo de espera em segundos
    
    Returns:
        dict: Resultado da consulta com status e detalhes
    """
    # Configurações do navegador
    options = uc.ChromeOptions()
    options.headless = headless
    
    # Configurações para evitar detecção
    ua = UserAgent()
    user_agent = ua.random
    options.add_argument(f'--user-agent={user_agent}')
    options.add_argument("--window-size=1920,1080")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    
    # Tenta detectar a versão do Chrome instalada
    chrome_version = get_chrome_version()
    
    try:
        # Configura o ChromeDriver com a versão correta
        driver = uc.Chrome(
            options=options,
            version_main=chrome_version if chrome_version else None,
            headless=headless,
            log_level=logging.INFO
        )
        
        # Configura propriedades para evitar detecção
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {"userAgent": user_agent}
        )
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        
        wait = WebDriverWait(driver, timeout)
        
        # Acessa o site
        logging.info("Acessando o site da PGFN...")
        driver.get("https://www.listadevedores.pgfn.gov.br/")
        time.sleep(2)  # Espera inicial
        
        # Preenche o CNPJ
        logging.info("Preenchendo CNPJ...")
        input_cnpj = wait.until(EC.presence_of_element_located((By.ID, "identificacaoInput")))
        input_cnpj.clear()
        
        # Digitação lenta para parecer humano
        for char in cnpj:
            input_cnpj.send_keys(char)
            time.sleep(0.1)
        
        # Clica no botão
        logging.info("Clicando no botão de consulta...")
        botao = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "btn-warning")))
        driver.execute_script("arguments[0].click();", botao)
        
        # Aguarda o resultado
        logging.info("Aguardando resultados...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Verifica mensagem de nenhum registro
                mensagem = driver.find_element(By.CSS_SELECTOR, "p.total-mensagens")
                if "Nenhum registro foi encontrado" in mensagem.text:
                    logging.info("Nenhuma dívida encontrada")
                    return {"status": "sem divida"}
                
                # Verifica resultados positivos
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
        return {"status": "erro", "mensagem": f"Erro durante a consulta: {str(e)}"}
        
    finally:
        if 'driver' in locals():
            try:
                driver.quit()
                logging.info("Navegador fechado")
            except Exception as e:
                logging.error(f"Erro ao fechar navegador: {str(e)}")