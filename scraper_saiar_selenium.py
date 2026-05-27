"""
Scraper SAIAR con Selenium - fotos + descripciones (sin precios)
Ejecutar: python scraper_saiar_selenium.py
Requiere: pip install selenium webdriver-manager
"""

import os, time, json, csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests

PRODUCTOS = [
    'https://saiar.com.ar/product/TECC055ESAK2',
    'https://saiar.com.ar/product/TECC085ESAK2',
    'https://saiar.com.ar/product/TEPC055ESARIK2',
    'https://saiar.com.ar/product/TEPC085ESARIK2',
    'https://saiar.com.ar/product/TEPC125ESARIK2',
    'https://saiar.com.ar/product/TCG050MSA',
    'https://saiar.com.ar/product/TCG080MSA',
    'https://saiar.com.ar/product/TPG050MSA',
    'https://saiar.com.ar/product/TPG080MSA',
    'https://saiar.com.ar/product/TPG120MSA',
    'https://saiar.com.ar/product/TPG150MSA',
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

def main():
    os.makedirs('fotos_saiar', exist_ok=True)
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1280,800')

    print("Iniciando Chrome...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    sess = requests.Session()
    sess.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    productos = []
    for i, url in enumerate(PRODUCTOS, 1):
        sku = url.split('/')[-1]
        print(f"\n[{i}/{len(PRODUCTOS)}] {sku}")
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
            print("  Sin nombre, saltando")
            continue

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
        print(f"  Specs: {len(specs)} items")

        imgs = []
        EXCLUIR = ['logo','icon','banner','sprite','flag','feature','caracteristica',
                   'icono','ventaja','beneficio','check','tick','star','rating',
                   'certif','iso','sello','award','fondo','background','bg-']

        def es_foto_producto(src):
            sl = src.lower()
            if not any(ext in sl for ext in ['.jpg','.jpeg','.png','.webp']):
                return False
            if any(x in sl for x in EXCLUIR):
                return False
            return True

        # 1. og:image — siempre tiene la foto principal del producto
        try:
            og = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')
            og_url = og.get_attribute('content') or ''
            if og_url and es_foto_producto(og_url):
                imgs.append(og_url)
                print(f"  og:image: {og_url[:60]}")
        except: pass

        # 2. Imagen principal del producto (antes de cualquier sección de features)
        if not imgs:
            main_sels = [
                '.product__image img', '.product-single__photo img',
                '[data-product-featured-image]', '[id*="product-image"] img',
                '.product-images img:first-child', '.product-gallery img:first-child',
                '[class*="hero"] img', '[class*="main-image"] img',
            ]
            for sel in main_sels:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    src = el.get_attribute('src') or el.get_attribute('data-src') or ''
                    if src and es_foto_producto(src):
                        imgs.append(src)
                        break
                except: pass

        # 3. Galería del producto (excluir secciones de features/beneficios explícitamente)
        if not imgs:
            galeria_sels = [
                '[class*="gallery"] img', '[class*="carousel"] img',
                '[class*="slider"] img', '[class*="product-image"] img',
                '[class*="swiper"] img', 'figure img',
            ]
            for sel in galeria_sels:
                try:
                    found = driver.find_elements(By.CSS_SELECTOR, sel)
                    for img in found:
                        src = img.get_attribute('src') or img.get_attribute('data-src') or ''
                        # Verificar que la imagen no está dentro de sección de features
                        try:
                            parent_class = img.find_element(By.XPATH, './ancestor::*[contains(@class,"feature") or contains(@class,"benefit") or contains(@class,"ventaja") or contains(@class,"caracteristica")]')
                            continue  # está dentro de sección de features, saltar
                        except: pass
                        if es_foto_producto(src):
                            imgs.append(src)
                    if imgs: break
                except: pass

        # 4. Fallback: todas las imágenes de la página que parezcan fotos de producto
        if not imgs:
            for img in driver.find_elements(By.TAG_NAME, 'img'):
                src = img.get_attribute('src') or img.get_attribute('data-src') or ''
                if not es_foto_producto(src): continue
                # Intentar obtener dimensiones reales via JS
                try:
                    w = driver.execute_script("return arguments[0].naturalWidth", img) or 0
                    h = driver.execute_script("return arguments[0].naturalHeight", img) or 0
                    # Excluir iconos cuadrados ≤ 400px
                    if w > 0 and h > 0:
                        if w == h and w <= 400: continue
                        if w < 150 or h < 150: continue
                except: w, h = 0, 0
                imgs.append(src)
                if len(imgs) >= 3: break

        imgs = list(dict.fromkeys(imgs))[:5]
        print(f"  {len(imgs)} imágenes")

        fotos_locales = []
        for j, img_url in enumerate(imgs, 1):
            ext = img_url.split('.')[-1].split('?')[0][:4]
            ruta = f"fotos_saiar/SAIAR_{sku}_{j}.{ext}"
            if descargar(img_url, ruta, sess):
                fotos_locales.append(ruta)
                print(f"  ✅ Foto {j} guardada")

        productos.append({
            'sku': sku, 'nombre': nombre,
            'descripcion': descripcion,
            'caracteristicas': specs,
            'imagenes': imgs,
            'fotos_locales': fotos_locales,
            'url': url
        })

    driver.quit()

    with open('saiar_productos.json', 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)
    with open('saiar_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
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
    print("Fotos en: fotos_saiar/")

if __name__ == '__main__':
    main()
