"""
Scraper RHEEM Argentina - www.rheem.com.ar
Ejecutar: python scraper_rheem_ar.py
Requiere: pip install selenium webdriver-manager requests
"""

import os, time, json, csv, re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests

CHROMEDRIVER_PATH = '/opt/node22/bin/chromedriver'
CHROME_BINARY     = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

BASE_URL = 'https://www.rheem.com.ar'

# Secciones de termotanques a explorar
SECCIONES = [
    '/termotanques/',
    '/termotanques/electrico/',
    '/termotanques/gas/',
    '/termotanques/electricoesteatita/',
    '/termotanques/electricocolumna/',
    '/termotanques/gascolumna/',
    '/termotanques/gaspie/',
    '/termotanques/alta-potencia/',
    '/termotanques/comerciales/',
    '/productos/',
]

EXCLUIR = ['logo','sprite','flag','certif','iso','9001','14001','sello','award',
           'banner','hero','slide','background','icon','favicon','whatsapp','social',
           'placeholder','spinner','loading','cart','checkout','menu','nav','footer',
           'header','base64','data:image']

def es_valida(src):
    if not src or src.startswith('data:'):
        return False
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

def esperar_carga(driver, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        time.sleep(2)
    except:
        time.sleep(4)

def get_imgs_producto(driver):
    """Extrae imágenes del área de contenido (fuera del header/footer)."""
    imgs = []

    # Estrategia 1: JS - imágenes en el área de contenido
    try:
        src_list = driver.execute_script("""
            var header = document.querySelector('header, nav, .header, #header, #masthead, .site-header');
            var hBottom = header ? header.getBoundingClientRect().bottom + window.scrollY : 150;
            var footer = document.querySelector('footer, .footer, #footer, #colophon, .site-footer');
            var fTop = footer ? footer.getBoundingClientRect().top + window.scrollY : 999999;

            return Array.from(document.querySelectorAll('img'))
                .map(function(img){
                    var rect = img.getBoundingClientRect();
                    var top = rect.top + window.scrollY;
                    var src = img.getAttribute('data-src') ||
                               img.getAttribute('data-lazy-src') ||
                               img.getAttribute('data-large_image') ||
                               img.currentSrc ||
                               img.src || '';
                    var w = img.naturalWidth || img.width || 0;
                    var h = img.naturalHeight || img.height || 0;
                    return {src:src, top:top, area:w*h, w:w, h:h};
                })
                .filter(function(x){
                    return x.top > hBottom && x.top < fTop && x.area > 20000 && x.src &&
                           !x.src.startsWith('data:');
                })
                .sort(function(a,b){ return b.area - a.area; })
                .map(function(x){ return x.src; });
        """)
        for src in (src_list or []):
            if es_valida(src) and src not in imgs:
                imgs.append(src)
    except Exception as e:
        print(f"  JS error: {e}")

    # Estrategia 2: og:image
    if not imgs:
        try:
            og = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')
            og_url = og.get_attribute('content') or ''
            if og_url and es_valida(og_url):
                imgs.append(og_url)
                print(f"  og:image: {og_url[:80]}")
        except: pass

    # Estrategia 3: imágenes con srcset (responsive)
    if not imgs:
        try:
            for img in driver.find_elements(By.TAG_NAME, 'img'):
                src = (img.get_attribute('data-src') or
                       img.get_attribute('srcset') or
                       img.get_attribute('src') or '')
                if ',' in src:  # srcset con múltiples tamaños → tomar el último (mayor)
                    src = src.strip().split(',')[-1].strip().split(' ')[0]
                if es_valida(src) and src not in imgs:
                    try:
                        w = driver.execute_script("return arguments[0].naturalWidth", img) or 0
                        h = driver.execute_script("return arguments[0].naturalHeight", img) or 0
                    except:
                        w = h = 0
                    if w >= 200 and h >= 200:
                        imgs.append(src)
        except: pass

    return list(dict.fromkeys(imgs))[:5]

def get_nombre(driver):
    for sel in ['h1', '.product-title', '.entry-title', '[class*="product-name"]',
                '[class*="title"]', 'h2']:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                t = el.text.strip()
                if len(t) > 6:
                    return t
        except: pass
    try:
        return driver.execute_script(
            "var h=document.querySelector('h1'); return h?h.textContent.trim():'';"
        ) or ''
    except:
        return ''

def get_specs(driver):
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
            for li in driver.find_elements(By.CSS_SELECTOR,
                    '[class*="spec"] li, [class*="feature"] li, .product-attributes li, ul li'):
                txt = li.text.strip()
                if 8 < len(txt) < 200: specs.append(txt)
            specs = list(dict.fromkeys(specs))[:15]
        except: pass
    return specs

def get_product_urls(driver):
    """Navega las secciones y recolecta URLs de productos."""
    urls = set()
    visited = set()

    for sec in SECCIONES:
        url = BASE_URL + sec
        if url in visited: continue
        visited.add(url)
        try:
            print(f"  Explorando: {url}")
            driver.get(url)
            esperar_carga(driver)

            # Recolectar enlaces a productos
            for a in driver.find_elements(By.TAG_NAME, 'a'):
                href = (a.get_attribute('href') or '').rstrip('/')
                if not href or 'rheem.com.ar' not in href:
                    continue
                # Excluir URLs de sección/categoría genéricas
                path = href.replace('https://www.rheem.com.ar','').replace('http://www.rheem.com.ar','')
                parts = [p for p in path.split('/') if p]
                # Una URL de producto suele tener 2+ partes y terminar en un slug específico
                if len(parts) >= 2 and not any(x in path for x in
                        ['#','?','mailto','tel','wp-','login','cart','wp-content',
                         'contacto','nosotros','distribuidores','soporte','garantia']):
                    urls.add(href)
        except Exception as e:
            print(f"  Error explorando {url}: {e}")

    return urls

def sku_desde_url(url):
    """Extrae un identificador del último segmento de la URL."""
    return url.rstrip('/').split('/')[-1].replace('-',' ').title()

def scrape_product(driver, url, sess, carpeta):
    driver.get(url)
    esperar_carga(driver)

    nombre = get_nombre(driver)

    genericos = ['termotanques','residenciales','gas','eléctricos','electricos',
                 'comerciales','inicio','home','tienda','shop','ingresar',
                 'productos','rheem','argentina','login','404']
    if not nombre or nombre.lower().strip() in genericos or len(nombre) < 5:
        print(f"  Sin nombre válido ('{nombre}') — saltando")
        return None

    slug = url.rstrip('/').split('/')[-1]
    print(f"  ✓ {nombre} [{slug}]")

    descripcion = ''
    for sel in ['[class*="description"]','[class*="desc"]','[class*="content"] p','p']:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                txt = el.text.strip()
                if len(txt) > 40:
                    descripcion = txt
                    break
            if descripcion: break
        except: pass

    specs = get_specs(driver)
    imgs = get_imgs_producto(driver)

    if imgs:
        print(f"  {len(imgs)} imagen(es): {imgs[0][:80]}")
    else:
        print("  ⚠ Sin imagen")

    fotos_locales = []
    for j, img_url in enumerate(imgs, 1):
        ext = img_url.split('?')[0].split('.')[-1][:4].lower()
        if ext not in ['jpg','jpeg','png','webp']: ext = 'jpg'
        ruta = f"{carpeta}/RHEEM_{slug}_{j}.{ext}"
        if descargar(img_url, ruta, sess):
            fotos_locales.append(ruta)
            print(f"  ✅ Foto {j}: {ruta}")
        else:
            print(f"  ❌ No descargada: {img_url[:60]}")

    return {
        'sku': slug,
        'nombre': nombre,
        'descripcion': descripcion,
        'caracteristicas': specs,
        'imagenes': imgs,
        'fotos_locales': fotos_locales,
        'url': url
    }

def main():
    carpeta = 'fotos_rheem_ar'
    os.makedirs(carpeta, exist_ok=True)

    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1280,900')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    # Sin headless para evitar detección de bots
    # opts.add_argument('--headless=new')  # descomantá si no necesitás ver el browser

    opts.binary_location = CHROME_BINARY
    print("Iniciando Chrome...")
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    sess = requests.Session()
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.rheem.com.ar/'
    })

    print("\nBuscando productos en www.rheem.com.ar...")
    todas_urls = get_product_urls(driver)
    print(f"  {len(todas_urls)} URLs candidatas encontradas")

    # Mostrar las URLs encontradas para revisión
    for u in sorted(todas_urls):
        print(f"    {u}")

    productos = []
    saltados = []
    lista_urls = sorted(todas_urls)

    for i, url in enumerate(lista_urls, 1):
        print(f"\n[{i}/{len(lista_urls)}] {url.split('/')[-1]}")
        try:
            p = scrape_product(driver, url, sess, carpeta)
            if p:
                productos.append(p)
            else:
                saltados.append(url)
        except Exception as e:
            print(f"  Error: {e}")
            saltados.append(url)
        time.sleep(1.5)

    driver.quit()

    print(f"\n{'='*55}")
    print(f"✅ {len(productos)} productos con nombre | ⚠ {len(saltados)} saltados")
    sin_foto = [p for p in productos if not p['fotos_locales']]
    if sin_foto:
        print(f"  {len(sin_foto)} productos sin foto descargada:")
        for p in sin_foto: print(f"    - {p['nombre']} ({p['url']})")

    with open('rheem_ar_productos.json', 'w', encoding='utf-8') as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)

    with open('rheem_ar_productos.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['SKU','Nombre','Descripcion','Caracteristicas','Foto1','Foto2','URL'])
        for p in productos:
            imgs = p['fotos_locales']
            w.writerow([p['sku'], p['nombre'], p['descripcion'],
                        ' | '.join(p['caracteristicas']),
                        imgs[0] if imgs else '', imgs[1] if len(imgs)>1 else '', p['url']])

    print(f"Fotos: {carpeta}/  |  JSON: rheem_ar_productos.json  |  CSV: rheem_ar_productos.csv")

if __name__ == '__main__':
    main()
