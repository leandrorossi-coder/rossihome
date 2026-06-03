"""
Scraper de productos Sherman - termotanquesherman.com.ar
Ejecutar desde tu PC: python scraper_sherman.py

Requiere: pip install requests beautifulsoup4 lxml
"""

import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import re
import os

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

BASE_URL = 'https://termotanquesherman.com.ar'

CATEGORIAS = [
    '/collection/categories/termotanques-residenciales-a-gas',
    '/collection/categories/termotanques',
    '/collection/categories/termotanques-electricos',
    '/collection/categories/termotanques-a-gas',
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


def get_product_urls_from_category(cat_url):
    html = get_page(BASE_URL + cat_url)
    if not html:
        return []
    soup = BeautifulSoup(html, 'lxml')
    urls = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/product/' in href:
            full = href if href.startswith('http') else BASE_URL + href
            urls.add(full)
    return list(urls)


def scrape_product(url):
    html = get_page(url)
    if not html:
        return None
    soup = BeautifulSoup(html, 'lxml')

    producto = {
        'url': url,
        'sku': url.split('/product/')[-1].split('?')[0],
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
    for sel in ['.product-description', '.description', '[class*="desc"]', 'article p']:
        el = soup.select_one(sel)
        if el:
            producto['descripcion'] = el.get_text(' ', strip=True)
            break

    # Características / specs (tablas o listas)
    specs = []
    for tabla in soup.find_all('table'):
        for tr in tabla.find_all('tr'):
            celdas = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if len(celdas) >= 2:
                specs.append(': '.join(celdas[:2]))
    if not specs:
        for li in soup.find_all('li'):
            txt = li.get_text(strip=True)
            if txt and len(txt) > 5:
                specs.append(txt)
    producto['caracteristicas'] = specs[:20]

    # Imágenes
    imgs = []
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            full = src if src.startswith('http') else BASE_URL + src
            if 'logo' not in full.lower() and 'icon' not in full.lower():
                imgs.append(full)
    producto['imagenes'] = list(dict.fromkeys(imgs))[:5]

    return producto


def main():
    print("=== Scraper Sherman ===\n")

    # Recolectar URLs de productos
    product_urls = set()
    for cat in CATEGORIAS:
        print(f"Buscando productos en: {cat}")
        urls = get_product_urls_from_category(cat)
        print(f"  Encontrados: {len(urls)}")
        product_urls.update(urls)
        time.sleep(1)

    # Agregar URLs conocidas de búsqueda
    product_urls.update([
        BASE_URL + '/product/TPGP120MSH13',
        BASE_URL + '/product/TECC055ESHK2',
    ])

    print(f"\nTotal productos únicos: {len(product_urls)}")
    print("Scrapeando detalles...\n")

    productos = []
    for i, url in enumerate(sorted(product_urls), 1):
        print(f"[{i}/{len(product_urls)}] {url.split('/product/')[-1]}")
        p = scrape_product(url)
        if p and p['nombre']:
            productos.append(p)
            print(f"  OK: {p['nombre']}")
            print(f"  Imágenes: {len(p['imagenes'])}")
        else:
            print(f"  [!] Sin datos")
        time.sleep(1.5)

    # Guardar JSON
    with open('sherman_productos.json', 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado: sherman_productos.json ({len(productos)} productos)")

    # Guardar CSV
    with open('sherman_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['SKU', 'Nombre', 'Descripcion', 'Caracteristicas', 'Imagen1', 'Imagen2', 'URL'])
        for p in productos:
            imgs = p['imagenes']
            w.writerow([
                p['sku'],
                p['nombre'],
                p['descripcion'],
                ' | '.join(p['caracteristicas']),
                imgs[0] if len(imgs) > 0 else '',
                imgs[1] if len(imgs) > 1 else '',
                p['url'],
            ])
    print(f"Guardado: sherman_productos.csv")
    print("\nListo!")


if __name__ == '__main__':
    main()
