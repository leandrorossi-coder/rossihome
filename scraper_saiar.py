"""
Scraper SAIAR - URLs directas de productos
Ejecutar: python scraper_saiar.py
Requiere: pip install requests beautifulsoup4 lxml
"""

import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import os

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'es-AR,es;q=0.9',
    'Referer': 'https://saiar.com.ar/',
}

PRODUCTOS_SAIAR = [
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

session = requests.Session()
session.headers.update(HEADERS)

def get_page(url, retries=3):
    for i in range(retries):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                return r.text
            print(f"  [!] Status {r.status_code}")
        except Exception as e:
            print(f"  [!] Error: {e}")
        time.sleep(2 ** i)
    return None

def scrape_product(url):
    html = get_page(url)
    if not html:
        return None
    soup = BeautifulSoup(html, 'lxml')
    sku = url.split('/product/')[-1]

    nombre = ''
    for tag in ['h1', 'h2']:
        el = soup.find(tag)
        if el and el.get_text(strip=True):
            nombre = el.get_text(strip=True)
            break

    descripcion = ''
    for sel in ['.product-description', '.description', '[class*="desc"]', 'article p']:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(' ', strip=True)
            if len(txt) > 20:
                descripcion = txt
                break

    specs = []
    for tabla in soup.find_all('table'):
        for tr in tabla.find_all('tr'):
            celdas = [td.get_text(strip=True) for td in tr.find_all(['td','th'])]
            if len(celdas) >= 2 and celdas[0] and celdas[1]:
                specs.append(f"{celdas[0]}: {celdas[1]}")
    if not specs:
        for li in soup.find_all('li'):
            txt = li.get_text(strip=True)
            if 8 < len(txt) < 150:
                specs.append(txt)

    imgs = []
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        if any(ext in src.lower() for ext in ['.jpg','.jpeg','.png','.webp']):
            full = src if src.startswith('http') else 'https://saiar.com.ar' + src
            if not any(x in full.lower() for x in ['logo','icon','banner','sprite']):
                imgs.append(full)
    imgs = list(dict.fromkeys(imgs))[:5]

    return {'url': url, 'sku': sku, 'nombre': nombre, 'descripcion': descripcion, 'caracteristicas': specs[:15], 'imagenes': imgs}

def descargar_imagen(url, ruta):
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200 and 'image' in r.headers.get('content-type',''):
            with open(ruta, 'wb') as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"    [!] {e}")
    return False

def main():
    print("=== Scraper SAIAR ===\n")
    os.makedirs('fotos_saiar', exist_ok=True)
    productos = []

    for i, url in enumerate(PRODUCTOS_SAIAR, 1):
        sku = url.split('/')[-1]
        print(f"[{i}/{len(PRODUCTOS_SAIAR)}] {sku}")
        p = scrape_product(url)
        if not p or not p['nombre']:
            print("  Sin datos")
            time.sleep(1)
            continue

        print(f"  {p['nombre']} — {len(p['imagenes'])} imágenes")
        fotos_locales = []
        for j, img_url in enumerate(p['imagenes'], 1):
            ext = img_url.split('.')[-1].split('?')[0][:4]
            ruta = f"fotos_saiar/SAIAR_{sku}_{j}.{ext}"
            if descargar_imagen(img_url, ruta):
                fotos_locales.append(ruta)
                print(f"  ✅ Foto {j}: {ruta}")
            time.sleep(0.3)

        p['fotos_locales'] = fotos_locales
        productos.append(p)
        time.sleep(1)

    with open('saiar_productos.json', 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)

    with open('saiar_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['SKU','Nombre','Descripcion','Imagen1','Imagen2','URL'])
        for p in productos:
            imgs = p.get('fotos_locales', [])
            w.writerow([p['sku'], p['nombre'], p.get('descripcion',''), imgs[0] if imgs else '', imgs[1] if len(imgs)>1 else '', p['url']])

    print(f"\nTotal: {len(productos)} productos")
    print("Fotos en carpeta: fotos_saiar/")
    print("Comprimí la carpeta fotos_saiar en ZIP y subíla a la app.")

if __name__ == '__main__':
    main()
