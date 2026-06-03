"""
Scraper de productos RHEEM SA (RHEEM + SAIAR + SHERMAN)
Ejecutar desde tu PC: python scraper_rheem_marcas.py

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
    'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

MARCAS = [
    {
        'nombre': 'RHEEM',
        'base': 'https://www.rheem.com.ar',
        'categorias': [
            '/Termotanques/Residenciales/Gas',
            '/Termotanques/Residenciales/Electricos',
        ],
        'url_pattern': '/Termotanques/',
    },
    {
        'nombre': 'SAIAR',
        'base': 'https://saiar.com.ar',
        'categorias': [
            '/collection/categories/termotanques',
            '/collection/categories/termotanques-termotanques-electricos',
        ],
        'url_pattern': '/product/',
    },
    {
        'nombre': 'SHERMAN',
        'base': 'https://termotanquesherman.com.ar',
        'categorias': [
            '/collection/categories/termotanques-residenciales-a-gas',
            '/collection/categories/termotanques',
        ],
        'url_pattern': '/product/',
    },
]

session = requests.Session()
session.headers.update(HEADERS)


def get_page(url, retries=3):
    for i in range(retries):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                return r.text
            print(f"  [!] Status {r.status_code} en {url}")
        except Exception as e:
            print(f"  [!] Error: {e}")
        time.sleep(2 ** i)
    return None


def get_product_urls(base, cat_path, url_pattern):
    html = get_page(base + cat_path)
    if not html:
        return []
    soup = BeautifulSoup(html, 'lxml')
    urls = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if url_pattern in href and href != cat_path:
            full = href if href.startswith('http') else base + href
            urls.add(full)
    return list(urls)


def scrape_product(url):
    html = get_page(url)
    if not html:
        return None
    soup = BeautifulSoup(html, 'lxml')

    producto = {
        'url': url,
        'sku': url.rstrip('/').split('/')[-1].split('?')[0],
        'nombre': '',
        'descripcion': '',
        'caracteristicas': [],
        'imagenes': [],
    }

    # Nombre
    for tag in ['h1', 'h2']:
        el = soup.find(tag)
        if el and el.get_text(strip=True):
            producto['nombre'] = el.get_text(strip=True)
            break

    # Descripción
    for sel in ['.product-description', '.description', '[class*="desc"]', 'article p', '.content p']:
        el = soup.select_one(sel)
        if el:
            texto = el.get_text(' ', strip=True)
            if len(texto) > 20:
                producto['descripcion'] = texto
                break

    # Specs
    specs = []
    for tabla in soup.find_all('table'):
        for tr in tabla.find_all('tr'):
            celdas = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if len(celdas) >= 2 and celdas[0] and celdas[1]:
                specs.append(f"{celdas[0]}: {celdas[1]}")
    if not specs:
        for li in soup.find_all('li'):
            txt = li.get_text(strip=True)
            if 8 < len(txt) < 150:
                specs.append(txt)
    producto['caracteristicas'] = specs[:15]

    # Imágenes
    imgs = []
    base_url = '/'.join(url.split('/')[:3])
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-lazy') or ''
        if not src:
            continue
        if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            full = src if src.startswith('http') else base_url + src
            if not any(x in full.lower() for x in ['logo', 'icon', 'banner', 'sprite', 'flag']):
                imgs.append(full)
    producto['imagenes'] = list(dict.fromkeys(imgs))[:5]

    return producto


def descargar_imagen(url, ruta):
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
            with open(ruta, 'wb') as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"    [!] No se pudo descargar {url}: {e}")
    return False


def main():
    print("=== Scraper RHEEM SA (RHEEM + SAIAR + SHERMAN) ===\n")
    os.makedirs('fotos', exist_ok=True)

    todos_productos = []

    for marca in MARCAS:
        print(f"\n{'='*40}")
        print(f"Procesando: {marca['nombre']} ({marca['base']})")
        print('='*40)

        product_urls = set()
        for cat in marca['categorias']:
            print(f"  Buscando en: {cat}")
            urls = get_product_urls(marca['base'], cat, marca['url_pattern'])
            print(f"  Encontrados: {len(urls)}")
            product_urls.update(urls)
            time.sleep(1)

        print(f"  Total URLs: {len(product_urls)}")

        for i, url in enumerate(sorted(product_urls), 1):
            print(f"\n  [{i}/{len(product_urls)}] {url.split('/')[-1]}")
            p = scrape_product(url)
            if not p or not p['nombre']:
                print("    Sin datos")
                continue

            p['marca'] = marca['nombre']
            print(f"    Nombre: {p['nombre']}")
            print(f"    Imágenes: {len(p['imagenes'])}")

            # Descargar imágenes
            fotos_locales = []
            for j, img_url in enumerate(p['imagenes'], 1):
                ext = img_url.split('.')[-1].split('?')[0][:4]
                nombre_archivo = f"fotos/{marca['nombre']}_{p['sku']}_{j}.{ext}"
                if descargar_imagen(img_url, nombre_archivo):
                    fotos_locales.append(nombre_archivo)
                    print(f"    ✅ Foto {j}: {nombre_archivo}")
                time.sleep(0.3)

            p['fotos_locales'] = fotos_locales
            todos_productos.append(p)
            time.sleep(1)

    # Guardar JSON
    with open('rheem_marcas_productos.json', 'w', encoding='utf-8') as f:
        json.dump(todos_productos, f, ensure_ascii=False, indent=2)

    # Guardar CSV
    with open('rheem_marcas_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Marca', 'SKU', 'Nombre', 'Descripcion', 'Caracteristicas', 'Imagen1', 'Imagen2', 'URL'])
        for p in todos_productos:
            imgs = p.get('fotos_locales', p.get('imagenes', []))
            w.writerow([
                p.get('marca', ''),
                p['sku'],
                p['nombre'],
                p.get('descripcion', ''),
                ' | '.join(p.get('caracteristicas', [])),
                imgs[0] if len(imgs) > 0 else '',
                imgs[1] if len(imgs) > 1 else '',
                p['url'],
            ])

    print(f"\n{'='*40}")
    print(f"Total productos: {len(todos_productos)}")
    print(f"Guardado: rheem_marcas_productos.json")
    print(f"Guardado: rheem_marcas_productos.csv")
    print(f"Fotos en carpeta: fotos/")
    print("\nListo! Comprimí la carpeta 'fotos' en un ZIP y subíla a la app.")


if __name__ == '__main__':
    main()
