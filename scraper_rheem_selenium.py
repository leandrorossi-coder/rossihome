"""
Scraper RHEEM Tienda Oficial - tienda.rheem.com.ar (SPA)
Ejecutar: python scraper_rheem_selenium.py
Requiere: pip install selenium webdriver-manager
"""

import os, time, json, csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests

BASE = 'https://tienda.rheem.com.ar/product/'

# SKUs a scrapear — combinados de lo detectado + naming convention RHEEM Argentina
SKUS = [
    # Eléctrico Colgar
    'TEC085RH', 'TEC125RH',
    # Eléctrico Pie
    'TEP085RH', 'TEP125RH', 'TEP155RH',
    # Gas Natural Pie
    'TGNP080RH', 'TGNP120RH', 'TGNP150RH',
    # Gas Natural Colgar
    'TGNC080RH',
    # Functional Eléctrico Colgar
    'TECC085ERHK2',
    # Functional Eléctrico Pie
    'TEPC085ERHK2', 'TEPC125ERHK2',
    # Functional Gas Natural Pie
    'TPG080GNRH', 'TPG120GNRH', 'TPG150GNRH',
    # Alta Potencia
    'APG160NRH07', 'APG160LRH07',
    # Comerciales Gas
    'RHCTP250N', 'RHCTP250L', 'RHCTP300N', 'RHCTP300L',
    # Comerciales Eléctrico
    'COM255E', 'COM255EAR',
]

EXCLUIR = ['logo','sprite','flag','certif','iso','9001','14001','sello','award',
           'banner','hero','slide','background','icon','favicon','whatsapp','social',
           'placeholder','spinner','loading','cart','checkout']

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

def esperar_contenido(driver, timeout=12):
    """Espera a que la SPA renderice el h1 principal."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, 'h1'))
        )
        time.sleep(2)  # margen extra para imágenes lazy
    except:
        time.sleep(4)

def get_all_product_urls(driver):
    """Visita la home y recolecta todas las URLs /product/"""
    urls = set()
    for url in ['https://tienda.rheem.com.ar/', 'https://tienda.rheem.com.ar/collection/categories/termotanques-']:
        try:
            driver.get(url)
            esperar_contenido(driver)
            for a in driver.find_elements(By.TAG_NAME, 'a'):
                href = (a.get_attribute('href') or '').rstrip('/')
                if '/product/' in href and 'tienda.rheem.com.ar' in href:
                    urls.add(href)
        except: pass
    return urls

def scrape_product(driver, url, sess, carpeta, marca):
    sku = url.rstrip('/').split('/')[-1].split('?')[0]
    print(f"  SKU: {sku}")
    driver.get(url)
    esperar_contenido(driver)

    nombre = ''
    for sel in ['h1', '[class*="product-title"]', '[class*="product-name"]',
                '[class*="title"]', 'h2']:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                t = el.text.strip()
                if len(t) > 8:
                    nombre = t
                    break
            if nombre: break
        except: pass

    if not nombre:
        # Intentar con JS por si el texto no está en el DOM visible
        try:
            nombre = driver.execute_script(
                "var h = document.querySelector('h1'); return h ? h.textContent.trim() : '';"
            ) or ''
        except: pass

    genericos = ['termotanques','residenciales','gas','eléctricos','electricos',
                 'comerciales','inicio','home','tienda','shop','ingresar',
                 'productos destacados','login']
    if not nombre or nombre.lower().strip() in genericos or len(nombre) < 6:
        print(f"  Sin nombre válido ('{nombre}') — saltando")
        return None

    descripcion = ''
    for sel in ['[class*="description"]','[class*="desc"]','p']:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                txt = el.text.strip()
                if len(txt) > 30:
                    descripcion = txt
                    break
            if descripcion: break
        except: pass

    specs = []
    try:
        for fila in driver.find_elements(By.CSS_SELECTOR, 'table tr'):
            celdas = fila.find_elements(By.CSS_SELECTOR, 'td, th')
            if len(celdas) >= 2:
                k = celdas[0].text.strip(); v = celdas[1].text.strip()
                if k and v: specs.append(f"{k}: {v}")
    except: pass
    if not specs:
        try:
            for li in driver.find_elements(By.CSS_SELECTOR, 'li'):
                txt = li.text.strip()
                if 8 < len(txt) < 150: specs.append(txt)
            specs = specs[:15]
        except: pass

    print(f"  ✓ {nombre}")

    imgs = []

    # Estrategia 1: imagen del área de producto (fuera del header) vía JS
    try:
        src_list = driver.execute_script("""
            var header = document.querySelector('header, nav, .header, #header, #masthead');
            var hBottom = header ? header.getBoundingClientRect().bottom + window.scrollY : 120;
            var footer = document.querySelector('footer, .footer, #footer, #colophon');
            var fTop = footer ? footer.getBoundingClientRect().top + window.scrollY : 999999;
            return Array.from(document.querySelectorAll('img'))
                .map(function(img){
                    var rect = img.getBoundingClientRect();
                    var top = rect.top + window.scrollY;
                    var src = img.getAttribute('data-src') || img.getAttribute('data-large_image') || img.src || '';
                    var w = img.naturalWidth || 0;
                    var h = img.naturalHeight || 0;
                    return {src:src, top:top, area:w*h};
                })
                .filter(function(x){ return x.top > hBottom && x.top < fTop && x.area > 30000 && x.src; })
                .sort(function(a,b){ return b.area - a.area; })
                .map(function(x){ return x.src; });
        """)
        for src in (src_list or []):
            if es_valida(src): imgs.append(src)
        if imgs: print(f"  Contenido: {imgs[0][:80]}")
    except Exception as e:
        print(f"  JS error: {e}")

    # Estrategia 2: og:image
    if not imgs:
        try:
            og = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')
            og_url = og.get_attribute('content') or ''
            if og_url and es_valida(og_url):
                nombre_og = og_url.split('/')[-1].split('?')[0].lower()
                # Descartar si el nombre del archivo no tiene números (probable logo genérico)
                if any(c.isdigit() for c in nombre_og) or sku.lower() in og_url.lower():
                    imgs.append(og_url)
                    print(f"  og:image: {og_url[:80]}")
                else:
                    print(f"  og:image descartado (genérico): {og_url[:60]}")
        except: pass

    # Estrategia 3: cualquier imagen >=200px en la página
    if not imgs:
        try:
            for img in driver.find_elements(By.TAG_NAME, 'img'):
                src = img.get_attribute('src') or img.get_attribute('data-src') or ''
                if not es_valida(src): continue
                try:
                    w = driver.execute_script("return arguments[0].naturalWidth", img) or 0
                    h = driver.execute_script("return arguments[0].naturalHeight", img) or 0
                except: w = h = 0
                if w >= 200 and h >= 200: imgs.append(src)
            if imgs: print(f"  Fallback tamaño: {imgs[0][:80]}")
        except: pass

    if not imgs: print("  ⚠ Sin imagen")
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
            print(f"  ❌ No descargada")

    return {'sku':sku, 'nombre':nombre, 'descripcion':descripcion,
            'caracteristicas':specs, 'imagenes':imgs,
            'fotos_locales':fotos_locales, 'url':url}

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

    # Recolectar URLs dinámicas + hardcodeadas
    print("Buscando productos en la tienda...")
    dinamicas = get_all_product_urls(driver)
    print(f"  {len(dinamicas)} URLs encontradas dinámicamente")

    skus_hardcode = set(SKUS)
    urls_hardcode = {BASE + s for s in skus_hardcode}
    todas = dinamicas | urls_hardcode
    print(f"  Total URLs a intentar: {len(todas)}")

    productos = []
    saltados = []
    for i, url in enumerate(sorted(todas), 1):
        print(f"\n[{i}/{len(todas)}] {url.split('/')[-1]}")
        try:
            p = scrape_product(driver, url, sess, carpeta, 'RHEEM')
            if p: productos.append(p)
            else: saltados.append(url)
        except Exception as e:
            print(f"  Error: {e}")
            saltados.append(url)
        time.sleep(1)

    driver.quit()

    print(f"\n{'='*50}")
    print(f"✅ {len(productos)} productos con foto | ⚠ {len(saltados)} sin nombre/foto")
    sin_foto = [p for p in productos if not p['fotos_locales']]
    if sin_foto:
        print(f"  ({len(sin_foto)} productos sin foto descargada)")

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

    print("Fotos: fotos_rheem/  |  JSON: rheem_productos.json")

if __name__ == '__main__':
    main()
