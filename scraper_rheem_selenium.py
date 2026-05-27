"""
Scraper RHEEM con Selenium - fotos + descripciones (sin precios)
Ejecutar: python scraper_rheem_selenium.py
Requiere: pip install selenium webdriver-manager
"""

import os, time, json, csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests

CATEGORIAS = [
    'https://www.rheem.com.ar/Termotanques/Residenciales/Gas',
    'https://www.rheem.com.ar/Termotanques/Residenciales/Electricos',
]

def descargar(url, ruta, session):
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200 and 'image' in r.headers.get('content-type',''):
            with open(ruta, 'wb') as f:
                f.write(r.content)
            return True
    except: pass
    return False

def get_product_urls(driver, cat_url):
    driver.get(cat_url)
    time.sleep(3)
    urls = set()
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = a.get_attribute('href') or ''
        if '/product/' in href or '/Termotanques/' in href and href != cat_url:
            urls.add(href)
    return list(urls)

def scrape_product(driver, url, sess, carpeta, marca):
    sku = url.rstrip('/').split('/')[-1].split('?')[0]
    print(f"  SKU: {sku}")
    driver.get(url)
    time.sleep(3)

    nombre = ''
    for sel in ['h1', 'h2', '[class*="title"]', '[class*="name"]']:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.text.strip():
                nombre = el.text.strip()
                break
        except: pass

    if not nombre:
        return None

    descripcion = ''
    for sel in ['[class*="description"]', '[class*="desc"]', 'article p', '.content p', 'p']:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                txt = el.text.strip()
                if len(txt) > 30:
                    descripcion = txt
                    break
            if descripcion:
                break
        except: pass

    specs = []
    try:
        filas = driver.find_elements(By.CSS_SELECTOR, 'table tr')
        for fila in filas:
            celdas = fila.find_elements(By.CSS_SELECTOR, 'td, th')
            if len(celdas) >= 2:
                k = celdas[0].text.strip()
                v = celdas[1].text.strip()
                if k and v:
                    specs.append(f"{k}: {v}")
    except: pass
    if not specs:
        try:
            items = driver.find_elements(By.CSS_SELECTOR, 'li')
            for li in items:
                txt = li.text.strip()
                if 8 < len(txt) < 150:
                    specs.append(txt)
            specs = specs[:15]
        except: pass

    print(f"  {nombre}")
    if descripcion: print(f"  Descripción: {descripcion[:60]}...")

    EXCLUIR_SIEMPRE = ['logo','sprite','flag','certif','iso','9001','14001','sello','award']

    def es_valida(src):
        sl = src.lower()
        return any(ext in sl for ext in ['.jpg','.jpeg','.png','.webp']) and \
               not any(x in sl for x in EXCLUIR_SIEMPRE)

    imgs = []

    # 1. Buscar imagen cuya URL contiene el código de producto (SKU) — más preciso
    sku_lower = sku.lower()
    for img in driver.find_elements(By.TAG_NAME, 'img'):
        src = img.get_attribute('src') or img.get_attribute('data-src') or ''
        if sku_lower in src.lower() and es_valida(src):
            imgs.append(src)
    if imgs:
        print(f"  SKU match: {imgs[0][:70]}")

    # 2. og:image — foto principal definida por el sitio
    if not imgs:
        try:
            og = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')
            og_url = og.get_attribute('content') or ''
            if og_url and es_valida(og_url):
                imgs.append(og_url)
                print(f"  og:image: {og_url[:70]}")
        except: pass

    # 3. Fallback: imagen más grande de la página medida con JS
    if not imgs:
        candidatas = []
        for img in driver.find_elements(By.TAG_NAME, 'img'):
            src = img.get_attribute('src') or img.get_attribute('data-src') or ''
            if not es_valida(src): continue
            try:
                w = driver.execute_script("return arguments[0].naturalWidth", img) or 0
                h = driver.execute_script("return arguments[0].naturalHeight", img) or 0
            except: w, h = 0, 0
            candidatas.append((w * h, src))
        candidatas.sort(reverse=True)
        imgs = [src for _, src in candidatas[:3] if src]

    imgs = list(dict.fromkeys(imgs))[:5]
    print(f"  {len(imgs)} imágenes")

    fotos_locales = []
    for j, img_url in enumerate(imgs, 1):
        ext = img_url.split('.')[-1].split('?')[0][:4]
        ruta = f"{carpeta}/{marca}_{sku}_{j}.{ext}"
        if descargar(img_url, ruta, sess):
            fotos_locales.append(ruta)
            print(f"  ✅ Foto {j} guardada")

    return {
        'sku': sku, 'nombre': nombre,
        'descripcion': descripcion,
        'caracteristicas': specs,
        'imagenes': imgs,
        'fotos_locales': fotos_locales,
        'url': url
    }

def main():
    carpeta = 'fotos_rheem'
    os.makedirs(carpeta, exist_ok=True)
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1280,800')

    print("Iniciando Chrome...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    sess = requests.Session()
    sess.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    product_urls = set()
    for cat in CATEGORIAS:
        print(f"Buscando en: {cat}")
        urls = get_product_urls(driver, cat)
        print(f"  {len(urls)} URLs encontradas")
        product_urls.update(urls)
        time.sleep(1)

    print(f"\nTotal productos: {len(product_urls)}")
    productos = []
    for i, url in enumerate(sorted(product_urls), 1):
        print(f"\n[{i}/{len(product_urls)}] {url.split('/')[-1]}")
        p = scrape_product(driver, url, sess, carpeta, 'RHEEM')
        if p:
            productos.append(p)
        time.sleep(1)

    driver.quit()

    with open('rheem_productos.json', 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)
    with open('rheem_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['SKU','Nombre','Descripcion','Caracteristicas','Foto1','Foto2','URL'])
        for p in productos:
            imgs = p['fotos_locales']
            w.writerow([
                p['sku'], p['nombre'], p['descripcion'],
                ' | '.join(p['caracteristicas']),
                imgs[0] if imgs else '',
                imgs[1] if len(imgs)>1 else '',
                p['url']
            ])

    print(f"\n✅ {len(productos)} productos guardados")
    print("Fotos en: fotos_rheem/")

if __name__ == '__main__':
    main()
