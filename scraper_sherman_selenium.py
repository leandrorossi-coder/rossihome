"""
Scraper SHERMAN con Selenium - fotos + descripciones
Ejecutar: python scraper_sherman_selenium.py
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
    'https://termotanquesherman.com.ar/product/TECC055ESHK2',
    'https://termotanquesherman.com.ar/product/TECC085ESHK2',
    'https://termotanquesherman.com.ar/product/TEPC055ESHK2',
    'https://termotanquesherman.com.ar/product/TEPC085ESHK2',
    'https://termotanquesherman.com.ar/product/TPGP050MSH13',
    'https://termotanquesherman.com.ar/product/TPGP080MSH13',
    'https://termotanquesherman.com.ar/product/TPGP120MSH13',
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
    os.makedirs('fotos_sherman', exist_ok=True)
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

        # Nombre
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

        # Descripción
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

        # Características técnicas
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
        if descripcion:
            print(f"  Descripción: {descripcion[:60]}...")
        print(f"  Specs: {len(specs)} items")

        # Imágenes
        imgs = []
        galeria_sels = [
            '[class*="gallery"] img', '[class*="carousel"] img',
            '[class*="slider"] img', '[class*="product-image"] img',
            '[class*="swiper"] img', '[class*="photo"] img',
            '[class*="imagen"] img', 'figure img',
        ]
        for sel in galeria_sels:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                for img in found:
                    src = img.get_attribute('src') or img.get_attribute('data-src') or ''
                    if any(ext in src.lower() for ext in ['.jpg','.jpeg','.png','.webp']):
                        if not any(x in src.lower() for x in ['logo','icon','banner','sprite','flag']):
                            imgs.append(src)
                if imgs:
                    break
            except: pass
        if not imgs:
            candidatas = []
            for img in driver.find_elements(By.TAG_NAME, 'img'):
                src = img.get_attribute('src') or img.get_attribute('data-src') or ''
                w = img.get_attribute('width') or '0'
                h = img.get_attribute('height') or '0'
                try: size = int(w) * int(h)
                except: size = 0
                if any(ext in src.lower() for ext in ['.jpg','.jpeg','.png','.webp']):
                    if not any(x in src.lower() for x in ['logo','icon','banner','sprite','flag']):
                        candidatas.append((size, src))
            candidatas.sort(reverse=True)
            imgs = [src for _, src in candidatas[:5]]
        imgs = list(dict.fromkeys(imgs))[:5]
        print(f"  {len(imgs)} imágenes")

        fotos_locales = []
        for j, img_url in enumerate(imgs, 1):
            ext = img_url.split('.')[-1].split('?')[0][:4]
            ruta = f"fotos_sherman/SHERMAN_{sku}_{j}.{ext}"
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

    with open('sherman_productos.json', 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)
    with open('sherman_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
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
    print("Fotos en: fotos_sherman/")
    print("Comprimí fotos_sherman en ZIP y subíla a la app.")

if __name__ == '__main__':
    main()
