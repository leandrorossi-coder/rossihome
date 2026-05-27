"""
Scraper RHEEM Tienda Oficial - tienda.rheem.com.ar
Fotos + descripciones de termotanques
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

# Categorías en la tienda oficial RHEEM Argentina
CATEGORIAS = [
    'https://tienda.rheem.com.ar/termotanques/',
    'https://tienda.rheem.com.ar/termotanques-a-gas/',
    'https://tienda.rheem.com.ar/termotanques-electricos/',
    'https://tienda.rheem.com.ar/termotanques-comerciales/',
]

EXCLUIR = ['logo','sprite','flag','certif','iso','9001','14001','sello','award',
           'banner','hero','slide','background','icon','favicon','whatsapp',
           'social','placeholder','spinner','loading','cart','checkout']

def es_valida(src):
    sl = src.lower()
    return (any(ext in sl for ext in ['.jpg','.jpeg','.png','.webp']) and
            not any(x in sl for x in EXCLUIR))

def descargar(url, ruta, session):
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200 and 'image' in r.headers.get('content-type',''):
            with open(ruta, 'wb') as f:
                f.write(r.content)
            return True
    except: pass
    return False

def get_product_urls(driver, cat_url):
    driver.get(cat_url)
    time.sleep(4)
    urls = set()
    # En tiendas WooCommerce/Shopify los links de producto tienen /product/ o /?p= o similar
    for a in driver.find_elements(By.TAG_NAME, 'a'):
        href = (a.get_attribute('href') or '').rstrip('/')
        if 'tienda.rheem.com.ar' not in href:
            continue
        # Excluir carrito, mi cuenta, etc.
        excluir_paths = ['/cart','/carrito','/checkout','/mi-cuenta','/account',
                         '/contacto','/contact','/blog','/sobre','/nosotros',
                         '#','mailto:','tel:','/page/','/categoria','/category']
        if any(x in href.lower() for x in excluir_paths):
            continue
        # Solo URLs más profundas que la categoría (páginas de producto)
        cat_depth = len([s for s in cat_url.rstrip('/').split('/') if s])
        href_depth = len([s for s in href.split('/') if s and 'tienda.rheem.com.ar' not in s])
        if href_depth >= cat_depth and href != cat_url.rstrip('/'):
            urls.add(href)
    return list(urls)

def scrape_product(driver, url, sess, carpeta, marca):
    sku = url.rstrip('/').split('/')[-1].split('?')[0]
    print(f"  URL: {url}")
    driver.get(url)
    time.sleep(4)

    # Verificar que es una página de producto real
    nombre = ''
    # WooCommerce usa h1.product_title o .entry-title
    for sel in ['h1.product_title', '.product_title', 'h1.entry-title',
                'h1', 'h2', '[class*="product-name"]', '[class*="product-title"]']:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            t = el.text.strip()
            if len(t) > 5:
                nombre = t
                break
        except: pass

    if not nombre:
        print("  Sin nombre — saltando")
        return None
    # Filtrar páginas de categoría o genéricas
    genericos = ['termotanques','residenciales','gas','eléctricos','electricos',
                 'comerciales','inicio','home','tienda','shop']
    if nombre.lower().strip() in genericos:
        print(f"  Nombre genérico '{nombre}' — saltando")
        return None

    descripcion = ''
    for sel in ['.woocommerce-product-details__short-description',
                '[class*="short-description"]', '[class*="description"]',
                '.entry-content p', 'article p', 'p']:
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
    # WooCommerce tiene tabla de atributos en .woocommerce-product-attributes
    for sel in ['.woocommerce-product-attributes tr',
                '.shop_attributes tr', 'table.variations tr',
                'table tr']:
        try:
            filas = driver.find_elements(By.CSS_SELECTOR, sel)
            for fila in filas:
                celdas = fila.find_elements(By.CSS_SELECTOR, 'td, th')
                if len(celdas) >= 2:
                    k = celdas[0].text.strip()
                    v = celdas[1].text.strip()
                    if k and v:
                        specs.append(f"{k}: {v}")
            if specs:
                break
        except: pass
    if not specs:
        try:
            for li in driver.find_elements(By.CSS_SELECTOR, 'li'):
                txt = li.text.strip()
                if 8 < len(txt) < 150:
                    specs.append(txt)
            specs = specs[:15]
        except: pass

    print(f"  ✓ {nombre}")
    if descripcion: print(f"  Desc: {descripcion[:60]}...")
    print(f"  Specs: {len(specs)}")

    imgs = []

    # ESTRATEGIA 1: Galería de producto WooCommerce (muy confiable)
    try:
        for sel in [
            '.woocommerce-product-gallery__image img',
            '.woocommerce-product-gallery img',
            '.product-gallery img',
            'figure.woocommerce-product-gallery__wrapper img',
            '.wp-post-image',
            'img.wp-post-image',
            '[class*="product-image"] img',
            '[class*="product-photo"] img',
        ]:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            for img in found:
                # Preferir data-large_image si existe (WooCommerce)
                src = (img.get_attribute('data-large_image') or
                       img.get_attribute('data-src') or
                       img.get_attribute('src') or '')
                if src and es_valida(src):
                    imgs.append(src)
            if imgs:
                print(f"  Galería WooCommerce ({sel}): {imgs[0][:80]}")
                break
    except Exception as e:
        print(f"  Error galería: {e}")

    # ESTRATEGIA 2: og:image
    if not imgs:
        try:
            og = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')
            og_url = og.get_attribute('content') or ''
            if og_url and es_valida(og_url):
                imgs.append(og_url)
                print(f"  og:image: {og_url[:80]}")
        except: pass

    # ESTRATEGIA 3: Imagen más grande en el contenido principal (fuera del header)
    if not imgs:
        try:
            src_list = driver.execute_script("""
                var header = document.querySelector('header, nav, .header, .navbar, #header, #masthead');
                var headerBottom = header ? header.getBoundingClientRect().bottom + window.scrollY : 150;
                var footer = document.querySelector('footer, .footer, #footer, #colophon');
                var footerTop = footer ? footer.getBoundingClientRect().top + window.scrollY : 999999;
                var imgs = Array.from(document.querySelectorAll('img'));
                var result = [];
                imgs.forEach(function(img) {
                    var rect = img.getBoundingClientRect();
                    var top = rect.top + window.scrollY;
                    var src = img.getAttribute('data-large_image') || img.src || img.getAttribute('data-src') || '';
                    var w = img.naturalWidth || 0;
                    var h = img.naturalHeight || 0;
                    if (top > headerBottom && top < footerTop && w >= 200 && h >= 150 && src) {
                        result.push({src: src, area: w * h});
                    }
                });
                result.sort(function(a,b){ return b.area - a.area; });
                return result.slice(0,5).map(function(x){ return x.src; });
            """)
            for src in (src_list or []):
                if es_valida(src):
                    imgs.append(src)
            if imgs:
                print(f"  Fallback contenido: {imgs[0][:80]}")
        except Exception as e:
            print(f"  JS fallback error: {e}")

    if not imgs:
        print("  ⚠ Sin imagen encontrada")

    imgs = list(dict.fromkeys(imgs))[:5]
    print(f"  {len(imgs)} imágenes")

    fotos_locales = []
    for j, img_url in enumerate(imgs, 1):
        ext = img_url.split('.')[-1].split('?')[0][:4]
        if ext not in ['jpg','jpeg','png','webp']: ext = 'jpg'
        ruta = f"{carpeta}/{marca}_{sku}_{j}.{ext}"
        if descargar(img_url, ruta, sess):
            fotos_locales.append(ruta)
            print(f"  ✅ Foto {j}: {ruta}")
        else:
            print(f"  ❌ No se pudo descargar foto {j}")

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
    opts.add_argument('--window-size=1280,900')

    print("Iniciando Chrome...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    sess = requests.Session()
    sess.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    product_urls = set()
    for cat in CATEGORIAS:
        print(f"\nBuscando en: {cat}")
        try:
            urls = get_product_urls(driver, cat)
            print(f"  {len(urls)} URLs encontradas:")
            for u in sorted(urls):
                print(f"    {u}")
            product_urls.update(urls)
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(2)

    if not product_urls:
        print("\n⚠ No se encontraron URLs. Verificá que tienda.rheem.com.ar esté accesible.")
        driver.quit()
        return

    print(f"\nTotal a procesar: {len(product_urls)}")
    productos = []
    skipped = []
    for i, url in enumerate(sorted(product_urls), 1):
        print(f"\n[{i}/{len(product_urls)}] {url.split('/')[-1] or url}")
        try:
            p = scrape_product(driver, url, sess, carpeta, 'RHEEM')
            if p:
                productos.append(p)
            else:
                skipped.append(url)
        except Exception as e:
            print(f"  Error: {e}")
            skipped.append(url)
        time.sleep(1)

    driver.quit()

    print(f"\n{'='*50}")
    print(f"✅ {len(productos)} productos | ⚠ {len(skipped)} saltados")
    if skipped:
        print("Saltados:")
        for u in skipped: print(f"  {u}")

    with open('rheem_productos.json', 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)
    with open('rheem_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['SKU','Nombre','Descripcion','Caracteristicas','Foto1','Foto2','URL'])
        for p in productos:
            imgs = p['fotos_locales']
            w.writerow([p['sku'], p['nombre'], p['descripcion'],
                        ' | '.join(p['caracteristicas']),
                        imgs[0] if imgs else '', imgs[1] if len(imgs)>1 else '', p['url']])

    print(f"Fotos: fotos_rheem/  |  JSON: rheem_productos.json")

if __name__ == '__main__':
    main()
