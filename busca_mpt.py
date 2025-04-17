import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException, TimeoutException, NoSuchElementException
)
from webdriver_manager.chrome import ChromeDriverManager

def buscar_investigado_mpt(termo_busca):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-notifications")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    regioes = [
        {"url": "https://www.prt1.mpt.mp.br/servicos/investigados", "regiao": "1ª Região (Rio de Janeiro)"},
        {"url": "https://www.prt2.mpt.mp.br/servicos/investigados", "regiao": "2ª Região (São Paulo)"},
        {"url": "https://www.prt3.mpt.mp.br/servicos/investigados", "regiao": "3ª Região (Minas Gerais)"},
    ]

    todos_dados = []

    for regiao in regioes:
        try:
            driver.get(regiao["url"])
            time.sleep(2)

            try:
                popup = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "popup") or contains(@id, "cookie")]'))
                )
                try:
                    close_button = popup.find_element(By.XPATH, './/button[contains(text(), "Fechar") or contains(@class, "close")]')
                    close_button.click()
                except:
                    pass
                WebDriverWait(driver, 10).until(EC.invisibility_of_element(popup))
            except TimeoutException:
                pass

            search_input = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, '//input[@placeholder="investigado..."]'))
            )

            search_input.clear()
            for char in termo_busca:
                search_input.send_keys(char)
                time.sleep(0.1)
            search_input.send_keys(u'\ue007')  # ENTER

            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//table/tbody/tr"))
            )

            data = []
            page_count = 0
            max_pages = 100

            while True:
                rows = WebDriverWait(driver, 20).until(
                    EC.presence_of_all_elements_located((By.XPATH, "//table/tbody/tr"))
                )
                for row in rows:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) == 4:
                        data.append([
                            cols[0].text, cols[1].text, cols[2].text, cols[3].text, regiao["regiao"]
                        ])

                page_count += 1
                if page_count >= max_pages:
                    break

                next_buttons = driver.find_elements(By.XPATH, '//li[@class="next"]/a')
                if next_buttons:
                    try:
                        driver.execute_script("arguments[0].click();", next_buttons[0])
                        WebDriverWait(driver, 30).until(EC.staleness_of(rows[0]))
                        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, "//table/tbody/tr")))
                    except:
                        break
                else:
                    break

            todos_dados.extend(data)

        except Exception:
            continue

    driver.quit()

    if todos_dados:
        return pd.DataFrame(todos_dados, columns=["Investigado", "Procedimento", "Atualização", "Status", "Região"])
    else:
        return pd.DataFrame()
