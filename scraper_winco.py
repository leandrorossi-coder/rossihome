"""
Scraper WINCO - winco.com.ar/products/
Auto-descubre todos los productos y descarga todas sus fotos.

Uso:
    python scraper_winco.py

Requiere:
    pip install playwright requests
    playwright install chromium
"""

import os, time, json, pathlib, re
from playwright.sync_api import sync_playwright
import requests

BASE = 'https://winco.com.ar'
PRODUCTS_URL = BASE + '/products/'

EXCLUIR_IMG = [
    'logo','sprite','flag','certif','iso','sello','award',
    'banner','hero','slide','background','icon','favicon',
    'whatsapp','social','placeholder','spinner','loading',
    'youtube','video','og.png','og.jpg','data:image',
    'woocommerce-placeholder',
]

def es_valida(src):
    if not src or src.startswith('data:'): return False
    sl = src.lower()
    return (any(ext in sl for ext in ['.jpg','.jpeg','.png','.webp']) and
            not any(x in sl for x in EXCLUIR_IMG))

def descargar(url, ruta, sess):
    try:
        r = sess.get(url, timeout=25, stream=True)
        ct = r.headers.get('content-type','')
        if r.status_code == 200 and 'image' in ct:
            with open(ruta, 'wb') as f:
                for chunk in r.iter_content(8192): f.write(chunk)
            return True
    except: pass
    return False

def cargar(page, url, espera=2.0):
    page.goto(url, timeout=25000, wait_until='domcontentloaded')
    try: page.wait_for_load_state('networkidle', timeout=8000)
    except: pass
    time.sleep(espera)

# ── Descubrir links de productos ────────────────────────────────────────────

def es_link_producto(href):
    """True si el href parece una página de producto individual (no categoría)."""
    if not href or 'winco.com.ar' not in href: return False
    path = href.replace('https://winco.com.ar','').rstrip('/')
    partes = [p for p in path.split('/') if p]
    # /products/categoria/producto  → 3 partes
    return len(partes) >= 3 and partes[0] == 'products'

def es_link_categoria(href):
    """True si el href parece una categoría de productos."""
    if not href or 'winco.com.ar' not in href: return False
    path = href.replace('https://winco.com.ar','').rstrip('/')
    partes = [p for p in path.split('/') if p]
    return len(partes) == 2 and partes[0] == 'products'

def get_todos_product_links(page):
    """Recorre /products/ y todas las categorías para obtener links de productos."""
    print("Descubriendo productos...")
    links_prod = set()
    links_cat  = set()

    # Paso 1: página principal de productos
    cargar(page, PRODUCTS_URL)
    hrefs = page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
    for h in hrefs:
        if es_link_producto(h):  links_prod.add(h.rstrip('/'))
        elif es_link_categoria(h): links_cat.add(h.rstrip('/'))

    print(f"  {len(links_cat)} categorías · {len(links_prod)} productos directos")

    # Paso 2: entrar a cada categoría (con paginación)
    for cat_url in sorted(links_cat):
        cat_name = cat_url.rstrip('/').split('/')[-1]
        pag_url  = cat_url
        pag      = 1
        while pag_url:
            cargar(page, pag_url, espera=1.5)
            hrefs = page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
            antes = len(links_prod)
            for h in hrefs:
                if es_link_producto(h): links_prod.add(h.rstrip('/'))
            nuevos = len(links_prod) - antes
            print(f"  [{cat_name} p{pag}] +{nuevos} productos (total {len(links_prod)})")

            # Paginación
            next_href = None
            for sel in ['a.next.page-numbers', 'a[rel="next"]', '.next a', 'a:text("›")', 'a:text("siguiente")']:
                try:
                    el = page.query_selector(sel)
                    if el:
                        next_href = el.get_attribute('href')
                        break
                except: pass
            pag_url = next_href if next_href and next_href != pag_url else None
            pag += 1

    print(f"\nTotal productos encontrados: {len(links_prod)}\n")
    return sorted(links_prod)

# ── Scraping de página de producto ──────────────────────────────────────────

def extraer_nombre(page):
    for sel in ['h1.product_title', 'h1.entry-title', 'h1', 'h2.product-name', '.product-name h1']:
        try:
            for el in page.locator(sel).all():
                t = el.inner_text().strip()
                if 5 < len(t) < 250: return t
        except: pass
    return ''

def extraer_codigo(page):
    """Busca el código/SKU original del producto."""
    # Intentar campo SKU estándar de WooCommerce
    for sel in [
        '.sku',
        '[class*="sku"]',
        '.product-meta .sku',
        'span.sku',
        '[itemprop="sku"]',
    ]:
        try:
            el = page.query_selector(sel)
            if el:
                t = el.inner_text().strip()
                if t and t.lower() not in ('n/a', '-', ''): return t
        except: pass

    # Buscar en texto de la página: "Código:", "Modelo:", "SKU:", "Ref:"
    try:
        html = page.content()
        for pattern in [
            r'(?:código|codigo|sku|modelo|ref\.?|referencia)[:\s]+([A-Z0-9\-_\.]+)',
        ]:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                cod = m.group(1).strip()
                if 2 < len(cod) < 40: return cod
    except: pass
    return ''

def extraer_precio(page):
    """Extrae precio numérico (ya incluye IVA según proveedor)."""
    for sel in [
        '.price ins .amount', '.price .amount', '.woocommerce-Price-amount',
        'p.price .amount', 'span.price', '[class*="price"]',
    ]:
        try:
            for el in page.locator(sel).all():
                t = el.inner_text().strip()
                t_clean = re.sub(r'[^\d,\.]', '', t).replace(',','.')
                # Tomar solo la parte entera si hay decimales
                t_clean = t_clean.split('.')[0] if '.' in t_clean else t_clean
                if t_clean.isdigit() and int(t_clean) > 0:
                    return int(t_clean)
        except: pass
    return 0

def extraer_imagenes(page):
    """Extrae todas las URLs de imágenes del producto (excluye miniaturas duplicadas)."""
    urls = []
    seen = set()

    try:
        # Galería WooCommerce estándar
        srcs = page.evaluate("""() => {
            const imgs = [];
            // 1. Imágenes de la galería principal
            document.querySelectorAll('.woocommerce-product-gallery img, .product-gallery img, [class*="gallery"] img, .product-images img').forEach(img => {
                const src = img.getAttribute('data-large_image') || img.getAttribute('data-src') || img.currentSrc || img.src || '';
                if(src && !src.startsWith('data:')) imgs.push(src);
            });
            // 2. Links de la galería (apuntan a imagen full-size)
            document.querySelectorAll('.woocommerce-product-gallery a, [class*="gallery"] a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if(href && (href.includes('.jpg') || href.includes('.jpeg') || href.includes('.png') || href.includes('.webp')))
                    imgs.push(href);
            });
            // 3. Imágenes principales de producto
            if(!imgs.length) {
                document.querySelectorAll('.product img, article img, main img').forEach(img => {
                    const src = img.getAttribute('data-large_image') || img.getAttribute('data-src') || img.currentSrc || img.src || '';
                    if(src && !src.startsWith('data:')) imgs.push(src);
                });
            }
            return [...new Set(imgs)];
        }""")
        for src in srcs:
            if es_valida(src) and src not in seen:
                seen.add(src)
                urls.append(src)
    except: pass

    return urls

def extraer_categoria(url):
    """Extrae la categoría desde la URL: /products/categoria/producto → 'categoria'"""
    partes = url.replace('https://winco.com.ar','').rstrip('/').split('/')
    partes = [p for p in partes if p]
    return partes[1].replace('-',' ').title() if len(partes) >= 3 else ''

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    carpeta = str(pathlib.Path.home() / 'Downloads' / 'fotos_winco')
    os.makedirs(carpeta, exist_ok=True)
    print(f"Fotos → {carpeta}\n")

    sess = requests.Session()
    sess.headers['User-Agent'] = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )

    productos   = []
    sin_nombre  = []
    sin_foto    = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage',
                  '--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width':1280,'height':800},
            locale='es-AR',
        )
        page = ctx.new_page()
        # Evitar detección básica de bot
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        # Descubrir todos los productos
        links = get_todos_product_links(page)

        if not links:
            print("No se encontraron productos. Verificar URL o estructura del sitio.")
            browser.close()
            return

        print(f"Scrapeando {len(links)} productos...\n")

        for i, url in enumerate(links, 1):
            print(f"[{i}/{len(links)}] {url.split('/')[-1]}")
            try:
                cargar(page, url)

                nombre  = extraer_nombre(page)
                codigo  = extraer_codigo(page)
                precio  = extraer_precio(page)
                img_urls = extraer_imagenes(page)
                categoria = extraer_categoria(url)

                if not nombre:
                    print("  ⚠ Sin nombre — saltando")
                    sin_nombre.append(url)
                    continue

                print(f"  ✓ {nombre}")
                if codigo:  print(f"  Cód: {codigo}")
                if precio:  print(f"  $ {precio:,}")
                print(f"  {len(img_urls)} imagen(es)")

                # Descargar fotos
                fotos_locales = []
                slug = re.sub(r'[^a-zA-Z0-9_-]', '_', url.rstrip('/').split('/')[-1])[:30]
                for j, img_url in enumerate(img_urls, 1):
                    ext = img_url.split('?')[0].split('.')[-1][:4].lower()
                    if ext not in ['jpg','jpeg','png','webp']: ext = 'jpg'
                    ruta = os.path.join(carpeta, f"WINCO_{slug}_{j}.{ext}")
                    if descargar(img_url, ruta, sess):
                        fotos_locales.append(ruta)
                        print(f"    ✅ {os.path.basename(ruta)}")
                    else:
                        print(f"    ❌ {img_url[:70]}")

                if not fotos_locales:
                    sin_foto.append(nombre)

                productos.append({
                    'nombre':         nombre,
                    'codigoOriginal': codigo,
                    'precio':         precio,
                    'categoria':      categoria,
                    'url':            url,
                    'fotos_locales':  fotos_locales,
                })

            except Exception as e:
                print(f"  Error: {e}")
                sin_nombre.append(url)

            time.sleep(1.2)

        browser.close()

    # ── Resumen ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"✅ {len(productos)} productos scrapeados")
    if sin_nombre: print(f"⚠  Sin nombre ({len(sin_nombre)}): primeros 5 → {sin_nombre[:5]}")
    if sin_foto:   print(f"📷 Sin foto ({len(sin_foto)}): primeros 5 → {sin_foto[:5]}")

    json_path = str(pathlib.Path.home() / 'Downloads' / 'winco_productos.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)

    print(f"\nJSON guardado en: {json_path}")
    print(f"Fotos guardadas en: {carpeta}")
    print("\nPróximos pasos:")
    print("  1. Zippeá la carpeta fotos_winco")
    print("  2. Subí las fotos desde: Proveedores → Winco Argentina → Cargar fotos")
    print("  3. Importá el JSON desde: Proveedores → Winco Argentina → Importar lista")

if __name__ == '__main__':
    main()
