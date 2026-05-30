"""
Scraper WINCO - winco.com.ar/products/
Auto-descubre todos los productos y descarga:
  - Todas las fotos
  - Videos (YouTube embed o MP4 directo)
  - Manuales (PDF)
  - Descripción técnica
  - Código original (SKU)

Uso:
    python scraper_winco.py

Requiere:
    pip install playwright requests yt-dlp
    playwright install chromium
"""

import os, time, json, pathlib, re, subprocess
from playwright.sync_api import sync_playwright
import requests

BASE = 'https://winco.com.ar'
PRODUCTS_URL = BASE + '/products/'

# Categorías confirmadas del sitio (slug → nombre display)
CATEGORIAS = [
    ('audio',            'Audio'),
    ('climatizacion',    'Climatización'),
    ('cocina',           'Cocina'),
    ('cuidado-personal', 'Cuidado Personal'),
    ('desayuno',         'Desayuno'),
    ('herramientas',     'Herramientas'),
    ('hogar',            'Hogar'),
]

EXCLUIR_IMG = [
    'logo','sprite','flag','certif','iso','sello','award',
    'banner','hero','slide','background','icon','favicon',
    'whatsapp','social','placeholder','spinner','loading',
    'og.png','og.jpg','data:image','woocommerce-placeholder',
]

def es_valida_img(src):
    if not src or src.startswith('data:'): return False
    sl = src.lower()
    return (any(ext in sl for ext in ['.jpg','.jpeg','.png','.webp']) and
            not any(x in sl for x in EXCLUIR_IMG))

def descargar_binario(url, ruta, sess, tipos_validos=('image',)):
    try:
        r = sess.get(url, timeout=60, stream=True)
        ct = r.headers.get('content-type','')
        if r.status_code == 200 and any(t in ct for t in tipos_validos):
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

# ── Descubrir links de productos ─────────────────────────────────────────────

def es_link_producto(href):
    """URL de producto: cualquier link de winco con ?slug="""
    if not href or 'winco.com.ar' not in href: return False
    return '?slug=' in href

def es_link_categoria(href):
    """URL de categoría: /products/categoria/ (sin ?slug=)"""
    if not href or 'winco.com.ar' not in href: return False
    if '?slug=' in href: return False          # producto, no categoría
    if '?category=' in href: return False      # filtro, no categoría directa
    path = href.split('?')[0].replace('https://winco.com.ar','').rstrip('/')
    partes = [p for p in path.split('/') if p]
    # Exactamente /products/categoria
    return len(partes) == 2 and partes[0] == 'products'

def get_cat_name(cat_url):
    path = cat_url.split('?')[0].replace('https://winco.com.ar','').rstrip('/')
    partes = [p for p in path.split('/') if p]
    return partes[-1] if partes else cat_url

def get_todos_product_links(page):
    print("Descubriendo productos...")
    links_prod = set()
    links_cat  = set()

    def cargar_y_scrollear(url, etiqueta):
        cargar(page, url, espera=5.0)
        try: page.wait_for_selector('a[href*="?slug="]', timeout=10000)
        except: pass

        antes = len(links_prod)
        sin_cambio = 0
        for ronda in range(60):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2.5)
            hrefs = page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
            for h in hrefs:
                if es_link_producto(h): links_prod.add(h)
            nuevos = len(links_prod) - antes
            print(f"  [{etiqueta} scroll {ronda+1}] total: {len(links_prod)}")
            if len(links_prod) == antes: sin_cambio += 1
            else: sin_cambio = 0; antes = len(links_prod)
            if sin_cambio >= 3: break

    # Página principal con scroll
    cargar_y_scrollear(PRODUCTS_URL, 'Todas')

    # Cada categoría como respaldo
    for cat_slug, cat_nombre in CATEGORIAS:
        antes = len(links_prod)
        cargar_y_scrollear(f"{BASE}/products/{cat_slug}/", cat_nombre)
        if len(links_prod) == antes:
            # Intentar con query param
            cargar_y_scrollear(f"{PRODUCTS_URL}?category={cat_slug}", cat_nombre)

    print(f"\nTotal productos encontrados: {len(links_prod)}\n")
    return sorted(links_prod)

# ── Extractores por campo ─────────────────────────────────────────────────────

def extraer_nombre(page):
    for sel in ['h1.product_title','h1.entry-title','h1','h2.product-name']:
        try:
            for el in page.locator(sel).all():
                t = el.inner_text().strip()
                if 5 < len(t) < 250: return t
        except: pass
    return ''

def extraer_codigo(page, url=''):
    """Extrae el código W-xxxx del producto."""
    # 1. Desde la URL: slug termina en -wNNNN (ej: afeitadora-afeita-barba-w831)
    slug = url.rstrip('/').split('/')[-1].split('?slug=')[-1]
    m = re.search(r'-(w\d+[a-z]*)$', slug, re.IGNORECASE)
    if m: return m.group(1).upper()

    # 2. Campo SKU estándar de WooCommerce
    for sel in ['.sku','[class*="sku"]','span.sku','[itemprop="sku"]']:
        try:
            el = page.query_selector(sel)
            if el:
                t = el.inner_text().strip()
                # Filtrar textos inválidos (nav links, etc.)
                if t and len(t) < 30 and re.match(r'^W\d+', t, re.IGNORECASE):
                    return t.upper()
        except: pass

    # 3. Buscar W-code en el nombre del producto
    try:
        nombre = extraer_nombre(page)
        m = re.search(r'\b(W\d+[A-Z0-9]*)\b', nombre, re.IGNORECASE)
        if m: return m.group(1).upper()
    except: pass

    return ''

def extraer_precio(page):
    for sel in ['.price ins .amount','.price .amount','.woocommerce-Price-amount','p.price .amount','[class*="price"]']:
        try:
            for el in page.locator(sel).all():
                t = re.sub(r'[^\d]', '', el.inner_text().strip())
                if t.isdigit() and int(t) > 0: return int(t)
        except: pass
    return 0

def extraer_descripcion(page):
    """Extrae la descripción técnica / ficha del producto."""
    for sel in [
        '.woocommerce-product-details__short-description',
        '#tab-description',
        '.product-description',
        '[class*="description"]',
        '.entry-content',
    ]:
        try:
            el = page.query_selector(sel)
            if el:
                t = el.inner_text().strip()
                # Limpiar texto: eliminar líneas vacías múltiples
                t = re.sub(r'\n{3,}', '\n\n', t)
                if len(t) > 20: return t
        except: pass
    return ''

def extraer_imagenes(page):
    """Todas las fotos del producto en máxima resolución."""
    urls, seen = [], set()
    try:
        srcs = page.evaluate("""() => {
            const imgs = [];
            // Galería WooCommerce: data-large_image tiene full-size
            document.querySelectorAll('.woocommerce-product-gallery img, .product-gallery img, [class*="gallery"] img, .product-images img').forEach(img => {
                const src = img.getAttribute('data-large_image') || img.getAttribute('data-src') || img.currentSrc || img.src || '';
                if(src && !src.startsWith('data:')) imgs.push(src);
            });
            // Links de galería → full-size directamente
            document.querySelectorAll('.woocommerce-product-gallery a, [class*="gallery"] a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if(href && /[.](jpe?g|png|webp)([?]|$)/i.test(href)) imgs.push(href);
            });
            if(!imgs.length) {
                document.querySelectorAll('.product img, article img, main img').forEach(img => {
                    const src = img.getAttribute('data-large_image') || img.getAttribute('data-src') || img.currentSrc || img.src || '';
                    if(src && !src.startsWith('data:')) imgs.push(src);
                });
            }
            return [...new Set(imgs)];
        }""")
        for src in srcs:
            if es_valida_img(src) and src not in seen:
                seen.add(src); urls.append(src)
    except: pass
    return urls

def extraer_videos(page):
    """Extrae URLs de videos: YouTube embeds y MP4 directos."""
    videos = []
    try:
        data = page.evaluate("""() => {
            const results = [];
            // YouTube iframes
            document.querySelectorAll('iframe[src*="youtube"], iframe[src*="youtu.be"]').forEach(el => {
                results.push({tipo: 'youtube', url: el.src});
            });
            // Videos HTML5 directos
            document.querySelectorAll('video source, video[src]').forEach(el => {
                const src = el.getAttribute('src') || '';
                if(src) results.push({tipo: 'mp4', url: src});
            });
            // Links a videos
            document.querySelectorAll('a[href*=".mp4"], a[href*="youtube"], a[href*="youtu.be"]').forEach(a => {
                results.push({tipo: 'link', url: a.href});
            });
            return results;
        }""")
        videos = data
    except: pass
    return videos

def extraer_manuales(page):
    """Extrae links a PDFs (manuales, fichas técnicas)."""
    pdfs = []
    try:
        data = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || '';
                if(href.toLowerCase().includes('.pdf')) {
                    const texto = (a.innerText || a.title || '').trim();
                    results.push({url: href, nombre: texto || 'manual'});
                }
            });
            return results;
        }""")
        pdfs = data
    except: pass
    return pdfs

def extraer_categoria(url):
    # /products/categoria/?slug=xxx → 'Categoria'
    path = url.split('?')[0].replace('https://winco.com.ar','').rstrip('/')
    partes = [p for p in path.split('/') if p]
    if len(partes) >= 2 and partes[0] == 'products':
        return partes[1].replace('-',' ').title()
    return ''

# ── Descarga de video (yt-dlp) ───────────────────────────────────────────────

def descargar_video(video, carpeta_prod, slug, idx, sess):
    """Descarga un video. YouTube → yt-dlp. MP4 directo → requests."""
    url  = video.get('url','')
    tipo = video.get('tipo','')
    if not url: return None

    if 'youtube' in url or 'youtu.be' in url:
        # Extraer ID limpio
        yt_match = re.search(r'(?:embed/|watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
        if not yt_match: return None
        yt_url  = f"https://www.youtube.com/watch?v={yt_match.group(1)}"
        out_tpl = os.path.join(carpeta_prod, f"WINCO_{slug}_video_{idx}.%(ext)s")
        try:
            resultado = subprocess.run(
                ['yt-dlp', '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                 '--merge-output-format', 'mp4',
                 '-o', out_tpl, yt_url],
                capture_output=True, text=True, timeout=120
            )
            # Buscar el archivo generado
            for f in os.listdir(carpeta_prod):
                if f.startswith(f"WINCO_{slug}_video_{idx}"):
                    return os.path.join(carpeta_prod, f)
        except Exception as e:
            print(f"    yt-dlp error: {e}")
        return None

    elif tipo in ('mp4','link') and url.endswith('.mp4'):
        ruta = os.path.join(carpeta_prod, f"WINCO_{slug}_video_{idx}.mp4")
        if descargar_binario(url, ruta, sess, tipos_validos=('video','application/octet')):
            return ruta
    return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    base_carpeta = pathlib.Path.home() / 'Downloads' / 'winco_scraping'
    base_carpeta.mkdir(parents=True, exist_ok=True)
    print(f"Archivos → {base_carpeta}\n")

    sess = requests.Session()
    sess.headers['User-Agent'] = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    )

    productos  = []
    con_error  = []

    with sync_playwright() as pw:
        # Usar Chrome real instalado (bypasea Cloudflare)
        browser = pw.chromium.launch(
            channel='chrome',
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            viewport={'width':1280,'height':900},
            locale='es-AR',
        )
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        links = get_todos_product_links(page)
        if not links:
            print("No se encontraron productos. Verificar URL.")
            browser.close()
            return

        print(f"Scrapeando {len(links)} productos...\n")

        for i, url in enumerate(links, 1):
            # Extraer slug limpio de la URL (?slug=xxx o último segmento del path)
            raw_slug = url.rstrip('/').split('/')[-1]
            if raw_slug.startswith('?slug='): raw_slug = raw_slug[6:]
            raw_slug = raw_slug.split('?slug=')[-1]
            slug = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_slug)[:35]
            print(f"[{i}/{len(links)}] {slug}")

            try:
                cargar(page, url)

                nombre      = extraer_nombre(page)
                codigo      = extraer_codigo(page, url)
                precio      = extraer_precio(page)
                descripcion = extraer_descripcion(page)
                img_urls    = extraer_imagenes(page)
                vid_data    = extraer_videos(page)
                pdf_data    = extraer_manuales(page)
                categoria   = extraer_categoria(url)

                if not nombre:
                    print("  ⚠ Sin nombre — saltando")
                    con_error.append(url); continue

                print(f"  ✓ {nombre}")
                if codigo:      print(f"  Cód: {codigo}")
                if precio:      print(f"  $ {precio:,}")
                if descripcion: print(f"  Desc: {descripcion[:80].replace(chr(10),' ')}...")
                print(f"  {len(img_urls)} foto(s) · {len(vid_data)} video(s) · {len(pdf_data)} manual(es)")

                # Carpeta por producto
                carpeta_prod = str(base_carpeta / slug)
                os.makedirs(carpeta_prod, exist_ok=True)

                # ── Fotos ──
                fotos_locales = []
                for j, img_url in enumerate(img_urls, 1):
                    ext = img_url.split('?')[0].split('.')[-1][:4].lower()
                    if ext not in ('jpg','jpeg','png','webp'): ext = 'jpg'
                    ruta = os.path.join(carpeta_prod, f"WINCO_{slug}_{j}.{ext}")
                    if descargar_binario(img_url, ruta, sess):
                        fotos_locales.append(ruta)
                        print(f"    📷 {os.path.basename(ruta)}")
                    else:
                        print(f"    ❌ foto {img_url[:60]}")

                # ── Videos ──
                videos_locales = []
                for j, vid in enumerate(vid_data, 1):
                    print(f"    🎬 Descargando video {j}...")
                    ruta_vid = descargar_video(vid, carpeta_prod, slug, j, sess)
                    if ruta_vid:
                        videos_locales.append(ruta_vid)
                        print(f"    ✅ {os.path.basename(ruta_vid)}")
                    else:
                        print(f"    ❌ video {vid.get('url','')[:60]}")

                # ── Manuales (PDF) ──
                manuales_locales = []
                for j, pdf in enumerate(pdf_data, 1):
                    pdf_url  = pdf.get('url','')
                    pdf_nom  = pdf.get('nombre','manual')
                    pdf_nom  = re.sub(r'[^a-zA-Z0-9_\-]', '_', pdf_nom)[:30]
                    ruta_pdf = os.path.join(carpeta_prod, f"WINCO_{slug}_manual_{j}_{pdf_nom}.pdf")
                    if descargar_binario(pdf_url, ruta_pdf, sess, tipos_validos=('application/pdf','application/octet')):
                        manuales_locales.append(ruta_pdf)
                        print(f"    📄 {os.path.basename(ruta_pdf)}")
                    else:
                        print(f"    ❌ PDF {pdf_url[:60]}")

                # ── Guardar descripción en .txt ──
                if descripcion:
                    ruta_txt = os.path.join(carpeta_prod, f"WINCO_{slug}_descripcion.txt")
                    with open(ruta_txt, 'w', encoding='utf-8') as f:
                        f.write(f"{nombre}\n{'='*len(nombre)}\n\n{descripcion}\n")

                productos.append({
                    'nombre':          nombre,
                    'codigoOriginal':  codigo,
                    'precio':          precio,
                    'descripcion':     descripcion,
                    'categoria':       categoria,
                    'url':             url,
                    'fotos_locales':   fotos_locales,
                    'videos_locales':  videos_locales,
                    'manuales_locales':manuales_locales,
                })

            except Exception as e:
                print(f"  Error: {e}")
                con_error.append(url)

            time.sleep(1.2)

        browser.close()

    # ── Resumen ───────────────────────────────────────────────────────────────
    total_fotos    = sum(len(p['fotos_locales'])    for p in productos)
    total_videos   = sum(len(p['videos_locales'])   for p in productos)
    total_manuales = sum(len(p['manuales_locales']) for p in productos)

    print(f"\n{'='*60}")
    print(f"✅ {len(productos)} productos")
    print(f"   📷 {total_fotos} fotos")
    print(f"   🎬 {total_videos} videos")
    print(f"   📄 {total_manuales} manuales")
    if con_error: print(f"   ⚠  {len(con_error)} con error")

    json_path = str(pathlib.Path.home() / 'Downloads' / 'winco_productos.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)

    print(f"\nJSON → {json_path}")
    print(f"Archivos → {base_carpeta}/[producto]/")
    print("\nPróximos pasos:")
    print("  1. Importá el JSON: Proveedores → Winco Argentina → Importar lista")
    print("  2. Subí fotos: Proveedores → Winco Argentina → Cargar fotos")

if __name__ == '__main__':
    main()
