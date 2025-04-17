# pgfn_consulta.py
import time
import json
import sys
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

def consultar_pgfn(cnpj):
    options = uc.ChromeOptions()
    options.headless = True
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        driver = uc.Chrome(options=options)
    except Exception as e:
        return {"status": "erro", "mensagem": f"Erro ao iniciar o navegador: {str(e)}"}

    try:
        driver.get("https://www.listadevedores.pgfn.gov.br/")
        time.sleep(5)

        input_cnpj = driver.find_element(By.ID, "identificacaoInput")
        input_cnpj.send_keys(cnpj)

        botao = driver.find_element(By.CLASS_NAME, "btn-warning")
        botao.click()

        time.sleep(10)

        try:
            mensagem = driver.find_element(By.CSS_SELECTOR, "p.total-mensagens")
            if "Nenhum registro foi encontrado" in mensagem.text:
                resultado = {"status": "sem divida"}
            else:
                linha = driver.find_element(By.CSS_SELECTOR, "tr.ng-star-inserted")
                colunas = linha.find_elements(By.TAG_NAME, "td")
                resultado = {
                    "status": "com divida",
                    "cnpj": colunas[1].text.strip(),
                    "nome": colunas[2].text.strip(),
                    "valor": colunas[3].text.strip()
                }
        except NoSuchElementException:
            resultado = {"status": "erro", "mensagem": "Elemento esperado não encontrado"}

    except Exception as e:
        resultado = {"status": "erro", "mensagem": str(e)}

    driver.quit()
    return resultado

if __name__ == "__main__":
    cnpj_input = sys.argv[1]
    resultado = consultar_pgfn(cnpj_input)
    print(json.dumps(resultado, ensure_ascii=False))
