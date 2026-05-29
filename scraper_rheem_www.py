"""
Scraper RHEEM - www.rheem.com.ar
URLs hardcodeadas de cada producto — sin exploración genérica del sitio.

Uso:
    python scraper_rheem_www.py
"""

import os, time, json, pathlib
from playwright.sync_api import sync_playwright
import requests

BASE = 'https://www.rheem.com.ar'

# URLs exactas de cada producto (SKU → path en el sitio)
PRODUCTOS = [
    # Eléctrico Colgar Performance
    ('TEC085RH',        '/Termotanques/Residenciales/Electricos/Performance/TEC085RH'),
    ('TEC125RH',        '/Termotanques/Residenciales/Electricos/Performance/TEC125RH'),
    # Eléctrico Pie Performance
    ('TEP085RH',        '/Termotanques/Residenciales/Electricos/Performance/TEP085RH'),
    ('TEP125RH',        '/Termotanques/Residenciales/Electricos/Performance/TEP125RH'),
    ('TEP155RH',        '/Termotanques/Residenciales/Electricos/Performance/TEP155RH'),
    # Eléctrico Colgar Functional
    ('TECC085ERHK2',    '/Termotanques/Residenciales/Electricos/Functional/TECC085ERHK2'),
    # Eléctrico Pie Functional
    ('TEPC085ERHK2',    '/Termotanques/Residenciales/Electricos/Functional/TEPC085ERHK2'),
    ('TEPC125ERHK2',    '/Termotanques/Residenciales/Electricos/Functional/TEPC125ERHK2'),
    # Gas Natural Pie Performance
    ('TGNP080RH',       '/Termotanques/Residenciales/Gas/Performance/TGNP080RH'),
    ('TGNP120RH',       '/Termotanques/Residenciales/Gas/Performance/TGNP120RH'),
    ('TGNP150RH',       '/Termotanques/Residenciales/Gas/Performance/TGNP150RH'),
    # Gas Natural Colgar Performance
    ('TGNC080RH',       '/Termotanques/Residenciales/Gas/Performance/TGNC080RH'),
    # Gas Natural Pie Functional
    ('TPG080GNRH',      '/Termotanques/Residenciales/Gas/Functional/TPG080GNRH'),
    ('TPG120GNRH',      '/Termotanques/Residenciales/Gas/Functional/TPG120GNRH'),
    ('TPG150GNRH',      '/Termotanques/Residenciales/Gas/Functional/TPG150GNRH'),
    # Alta Potencia Confort
    ('APG160NRH07',     '/Termotanques/Residenciales/Gas/Confort/APG160NRH07'),
    ('APG160LRH07',     '/Termotanques/Residenciales/Gas/Confort/APG160LRH07'),
    # Híbrido
    ('TBCP200RHVB',     '/Termotanques/Residenciales/Hibridos/Ecosmart/TBCP200RHVB'),
    # Comerciales Eléctrico
    ('COM255E',         '/Termotanques/Comerciales/Electricos/Comerciales-electricos/COM255E'),
    ('COM255EAR',       '/Termotanques/Comerciales/Electricos/Comerciales-electricos/COM255EAR'),
    ('COM500ERH',       '/Termotanques/Comerciales/Electricos/Comerciales-electricos/COM500ERH'),
    # Comerciales Gas
    ('RHCTP250N',       '/Termotanques/Comerciales/Gas/Comerciales-a-gas/RHCTP250N'),
    ('RHCTP250L',       '/Termotanques/Comerciales/Gas/Comerciales-a-gas/RHCTP250L'),
    ('RHCTP300N',       '/Termotanques/Comerciales/Gas/Comerciales-a-gas/RHCTP300N'),
    ('RHCTP300L',       '/Termotanques/Comerciales/Gas/Comerciales-a-gas/RHCTP300L'),
    # Calefones
    ('R7-14L-GN-XI-TF-B', '/Calefones/Calefon-tiro-forzado/R7-14L-GN-XI-TF-B'),
    ('R7-14L-GN-XI-D',    '/Calefones/Calefon-tiro-natural/R7-14L-GN-XI-D'),
    # Calderas
    ('RBS24RH',         '/Calderas/Duales/RBS24RH'),
]

# Secciones donde pueden existir productos adicionales no listados arriba
BUSCAR_ADICIONALES_EN = [
    '/Calefones/',
    '/Calefones/Calefon-tiro-forzado/',
    '/Calefones/Calefon-tiro-natural/',
    '/Calderas/',
    '/Calderas/Duales/',
    '/Termotanques/Residenciales/Hibridos/Ecosmart/',
]

EXCLUIR_IMG = ['og.png','og.jpg','logo','sprite','flag','certif','iso','sello',
               'award','banner','hero','slide','background','icon','favicon',
               'whatsapp','social','placeholder','spinner','loading','history',
               'versus','data:image']

def es_valida(src):
    if not src or src.startswith('data:'): return False
    sl = src.lower()
    return (any(ext in sl for ext in ['.jpg','.jpeg','.png','.webp','.svg']) and
            not any(x in sl for x in EXCLUIR_IMG))

def descargar(url, ruta, sess):
    try:
        r = sess.get(url, timeout=20)
        ct = r.headers.get('content-type','')
        if r.status_code == 200 and ('image' in ct or 'svg' in ct):
            with open(ruta, 'wb') as f: f.write(r.content)
            return True
    except: pass
    return False

def cargar(page, url):
    page.goto(url, timeout=15000, wait_until='domcontentloaded')
    try: page.wait_for_load_state('networkidle', timeout=6000)
    except: pass
    time.sleep(1.5)

def get_imgs(page):
    imgs = []
    try:
        src = page.evaluate("""() => {
            const header = document.querySelector('header, nav, .header, #header');
            const hBottom = header ? header.getBoundingClientRect().bottom + window.scrollY : 150;
            const footer = document.querySelector('footer, .footer, #footer');
            const fTop = footer ? footer.getBoundingClientRect().top + window.scrollY : 999999;
            const allImgs = Array.from(document.querySelectorAll('img'));
            // Primero buscar JPG/PNG (fondo blanco)
            for (const el of allImgs) {
                const rect = el.getBoundingClientRect();
                const top = rect.top + window.scrollY;
                if (top <= hBottom || top >= fTop) continue;
                const s = el.getAttribute('data-src') || el.currentSrc || el.src || '';
                const sl = s.toLowerCase();
                if (s && !s.startsWith('data:') && (sl.includes('.jpg') || sl.includes('.jpeg') || sl.includes('.png') || sl.includes('.webp'))) {
                    const w = el.naturalWidth || el.width || 0;
                    const h = el.naturalHeight || el.height || 0;
                    if (w * h > 10000) return s;
                }
            }
            // Fallback: SVG si no hay JPG/PNG
            for (const el of allImgs) {
                const rect = el.getBoundingClientRect();
                const top = rect.top + window.scrollY;
                if (top <= hBottom || top >= fTop) continue;
                const s = el.getAttribute('data-src') || el.currentSrc || el.src || '';
                if (s && !s.startsWith('data:') && s.toLowerCase().includes('.svg')) return s;
            }
            return null;
        }""")
        if src and es_valida(src):
            imgs.append(src)
    except: pass
    return imgs[:1]

def buscar_adicionales(page, skus_conocidos):
    """Busca productos en secciones específicas que no estén ya en la lista."""
    extras = []
    slugs_conocidos = {s.upper() for s, _ in skus_conocidos}
    categorias = {'electricos','gas','hibridos','comerciales','residenciales',
                  'comerciales-electricos','comerciales-a-gas','functional',
                  'performance','confort','ecosmart','calefones','calderas',
                  'duales','tiro-forzado','tiro-natural','termotanques'}

    for sec in BUSCAR_ADICIONALES_EN:
        try:
            cargar(page, BASE + sec)
            hrefs = page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
            for href in hrefs:
                if 'rheem.com.ar' not in href or 'tienda.rheem' in href: continue
                slug = href.rstrip('/').split('/')[-1]
                if slug.lower() in categorias: continue
                if slug.upper() in slugs_conocidos: continue
                path = href.replace('https://www.rheem.com.ar','')
                if len([p for p in path.split('/') if p]) >= 2:
                    extras.append((slug, path))
                    slugs_conocidos.add(slug.upper())
        except: pass
    return extras

def scrape_producto(page, sku, path, sess, carpeta):
    url = BASE + path
    cargar(page, url)

    nombre = ''
    for sel in ['h1','h2','.product-name','[class*="title"]']:
        try:
            for el in page.locator(sel).all():
                t = el.inner_text().strip()
                if 5 < len(t) < 200:
                    nombre = t; break
            if nombre: break
        except: pass

    if not nombre:
        print("  Sin nombre — saltando")
        return None

    print(f"  ✓ {nombre}")
    imgs = get_imgs(page)

    if imgs: print(f"  {len(imgs)} imagen(es)")
    else: print("  ⚠ Sin imagen")

    fotos_locales = []
    for j, img_url in enumerate(imgs, 1):
        ext = img_url.split('?')[0].split('.')[-1][:4].lower()
        if ext not in ['jpg','jpeg','png','webp','svg']: ext = 'jpg'
        ruta = os.path.join(carpeta, f"RHEEM_{sku}_{j}.{ext}")
        if descargar(img_url, ruta, sess):
            fotos_locales.append(ruta)
            print(f"  ✅ RHEEM_{sku}_{j}.{ext}")
        else:
            print(f"  ❌ {img_url[:60]}")

    return {'sku': sku, 'nombre': nombre, 'fotos_locales': fotos_locales, 'url': url}

def main():
    carpeta = str(pathlib.Path.home() / 'Downloads' / 'fotos_rheem_www')
    os.makedirs(carpeta, exist_ok=True)
    print(f"Fotos se guardarán en: {carpeta}\n")

    sess = requests.Session()
    sess.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    productos = []
    saltados  = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage'])
        page = browser.new_context().new_page()

        # Solo scrapear los productos hardcodeados
        print(f"Total: {len(PRODUCTOS)} productos a scrapear\n")

        for i, (sku, path) in enumerate(PRODUCTOS, 1):
            print(f"[{i}/{len(PRODUCTOS)}] {sku}")
            try:
                p = scrape_producto(page, sku, path, sess, carpeta)
                if p: productos.append(p)
                else: saltados.append(sku)
            except Exception as e:
                print(f"  Error: {e}")
                saltados.append(sku)
            time.sleep(1)

        browser.close()

    print(f"\n{'='*55}")
    print(f"✅ {len(productos)} productos scrapeados")
    if saltados:
        print(f"⚠  Sin resultado: {', '.join(saltados)}")

    with open(str(pathlib.Path.home() / 'Downloads' / 'rheem_productos.json'),
              'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)

    print(f"\nFotos guardadas en: {carpeta}")
    print("Zippeá esa carpeta y subila desde: Proveedores → RHEEM SA → Cargar fotos")

if __name__ == '__main__':
    main()
