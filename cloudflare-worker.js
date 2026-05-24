export default {
  async fetch(request, env, ctx) {
    const SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxaFHEannPGvJYj0QFBPpqNsu9dp8xZ5R0oz9I_GIXB2CJ0mBOlKPshjLUINKYSyKF7/exec';

    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    const jsonHeaders = { ...corsHeaders, 'Content-Type': 'application/json' };

    try {
      if (request.method === 'POST') {
        const body = await request.text();
        let parsed = {};
        try { parsed = JSON.parse(body); } catch(e) {}

        if (parsed.action === 'scrape') {
          return await handleScrape(parsed.url, jsonHeaders);
        }

        if (parsed.action === 'guardar') {
          return await handleGuardar(parsed, body, SCRIPT_URL, jsonHeaders);
        }

        // Cualquier otro POST — proxy directo
        const resp = await fetch(SCRIPT_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
          redirect: 'follow',
        });
        const text = await resp.text();
        try { JSON.parse(text); return new Response(text, { headers: jsonHeaders }); }
        catch(e) { return new Response(JSON.stringify({ ok: false, error: 'Auth required' }), { headers: jsonHeaders }); }

      } else {
        const resp = await fetch(SCRIPT_URL + '?api=1', {
          method: 'GET', redirect: 'follow',
          headers: { 'Accept': 'application/json' },
        });
        const text = await resp.text();
        try { JSON.parse(text); return new Response(text, { headers: jsonHeaders }); }
        catch(e) { return new Response(JSON.stringify({ ok: false, error: 'Auth required' }), { headers: jsonHeaders }); }
      }
    } catch(e) {
      return new Response(JSON.stringify({ ok: false, error: e.message }), { headers: jsonHeaders });
    }
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// GUARDAR CON MERGE DE PRODUCTOS
// ─────────────────────────────────────────────────────────────────────────────

async function handleGuardar(parsed, originalBody, SCRIPT_URL, jsonHeaders) {
  const productosDirty = parsed.productosDirty === true;
  const productosEntrantes = parsed.productos || [];

  // Si productos no fueron modificados en este dispositivo,
  // consultamos Drive para no pisar productos que otro dispositivo haya agregado
  if (!productosDirty) {
    try {
      const driveResp = await fetch(SCRIPT_URL + '?api=1', {
        method: 'GET',
        redirect: 'follow',
        headers: { 'Accept': 'application/json' },
      });
      if (driveResp.ok) {
        const driveText = await driveResp.text();
        const driveData = JSON.parse(driveText);
        const driveProds = driveData?.datos?.productos || [];

        if (driveProds.length > productosEntrantes.length) {
          // Drive tiene más productos — usar los de Drive para no perderlos
          parsed.productos = driveProds;
        }
      }
    } catch(e) {
      // Si falla el GET, usamos los productos entrantes (mejor que cortar el guardado)
    }
  }

  // Reensamblar el body con los productos correctos
  const bodyFinal = JSON.stringify(parsed);

  const resp = await fetch(SCRIPT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: bodyFinal,
    redirect: 'follow',
  });
  const text = await resp.text();
  try { JSON.parse(text); return new Response(text, { headers: jsonHeaders }); }
  catch(e) { return new Response(JSON.stringify({ ok: false, error: 'Auth required' }), { headers: jsonHeaders }); }
}

// ─────────────────────────────────────────────────────────────────────────────
// SCRAPING
// ─────────────────────────────────────────────────────────────────────────────

const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  'Accept-Language': 'es-AR,es;q=0.9,en;q=0.7',
  'Accept-Encoding': 'gzip, deflate, br',
  'Cache-Control': 'no-cache',
  'Pragma': 'no-cache',
  'Sec-Fetch-Dest': 'document',
  'Sec-Fetch-Mode': 'navigate',
  'Sec-Fetch-Site': 'none',
  'Upgrade-Insecure-Requests': '1',
};

async function handleScrape(url, headers) {
  if (!url) return json({ ok: false, error: 'URL requerida' }, headers);

  try {
    const u = new URL(url);

    // 1. WooCommerce Store API (pública, sin auth, disponible en WooCommerce 3.6+)
    const storeRes = await intentarWooStoreAPI(u.origin, headers);
    if (storeRes) return storeRes;

    // 2. WooCommerce REST API v3 (requiere auth, pero probamos igual)
    const wooRes = await intentarWooAPI(u.origin, headers);
    if (wooRes) return wooRes;

    // 3. Tiendanube API
    const tnRes = await intentarTiendanubeAPI(url, headers);
    if (tnRes) return tnRes;

    // 4. Fetch HTML con headers de navegador real
    const htmlHeaders = { ...FETCH_HEADERS, 'Referer': 'https://www.google.com/', 'Sec-Fetch-Site': 'cross-site' };
    let resp = await fetch(url, { headers: htmlHeaders, redirect: 'follow' });

    // Si 403, intentar con URL alternativa /shop o /tienda
    if (!resp.ok && resp.status === 403) {
      const altUrl = u.origin + '/shop/';
      const resp2 = await fetch(altUrl, { headers: htmlHeaders, redirect: 'follow' });
      if (resp2.ok) resp = resp2;
    }

    if (!resp.ok) {
      return json({ ok: false, error: `HTTP ${resp.status}: el sitio bloquea scraping. Intentá con la URL de una categoría específica (ej: /categoria/sillas/).` }, headers);
    }

    const html = await resp.text();
    const finalUrl = resp.url || url;
    const platform = detectarPlataforma(html);
    const productos = extraerProductos(html, finalUrl);

    if (!productos.length) {
      const idx = html.indexOf('class="products ');
      const ulStart = idx > 0 ? html.indexOf('>', idx) + 1 : -1;
      const fragmento = ulStart > 0 ? html.slice(ulStart, ulStart + 4000) : html.slice(224000, 228000);
      const primerLi = html.indexOf('<li', ulStart > 0 ? ulStart : 224000);
      const liClase = primerLi > 0 ? html.slice(primerLi, primerLi + 300) : 'no li found';
      return json({
        ok: false,
        error: `ul.products en pos ${idx} | primer li en pos ${primerLi} | clase del li: ${liClase.slice(0,150)}`,
        debug: { htmlLen: html.length, htmlPreview: fragmento }
      }, headers);
    }

    return json({ ok: true, productos, total: productos.length, platform }, headers);

  } catch(e) {
    return json({ ok: false, error: e.message }, headers);
  }
}

// WooCommerce Store API — pública sin autenticación (WooCommerce Blocks / Headless)
async function intentarWooStoreAPI(origin, headers) {
  const productos = [];
  const apiHeaders = {
    ...FETCH_HEADERS,
    'Accept': 'application/json',
    'Referer': origin + '/',
    'Origin': origin,
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
  };
  for (let page = 1; page <= 10; page++) {
    try {
      const apiUrl = `${origin}/wp-json/wc/store/v1/products?per_page=100&page=${page}`;
      let resp = await fetch(apiUrl, { headers: apiHeaders, redirect: 'follow' });
      if (!resp.ok && resp.status === 403) {
        resp = await fetch(`${origin}/wp-json/wc/store/v1/products?per_page=20&page=${page}`, { headers: apiHeaders, redirect: 'follow' });
      }
      if (!resp.ok) break;
      const ct = resp.headers.get('content-type') || '';
      if (!ct.includes('json')) break;
      const data = await resp.json();
      if (!Array.isArray(data) || !data.length) break;
      for (const p of data) {
        const nombre = limpiar(p.name || '');
        if (!nombre) continue;
        const precioStr = limpiar(p.prices?.price || p.price_html || '0');
        const precio = parsePrecioAR(precioStr.replace(/[^\d.,]/g, ''));
        const foto = p.images?.[0]?.src || null;
        productos.push({
          nombre,
          precio,
          descripcion: limpiar(p.short_description || '').slice(0, 200),
          foto,
          url: p.permalink || origin,
          sku: p.sku || '',
          categoria: p.categories?.[0]?.name || '',
        });
      }
      if (data.length < 100) break;
    } catch(e) { break; }
  }
  if (!productos.length) return null;
  return json({ ok: true, productos, total: productos.length, platform: 'WooCommerce Store API' }, headers);
}

// WooCommerce REST API pública
async function intentarWooAPI(origin, headers) {
  const productos = [];
  for (let page = 1; page <= 5; page++) {
    try {
      const apiUrl = `${origin}/wp-json/wc/v3/products?per_page=100&page=${page}&status=publish`;
      const resp = await fetch(apiUrl, {
        headers: { ...FETCH_HEADERS, 'Accept': 'application/json', 'Referer': origin+'/', 'Origin': origin },
        redirect: 'follow',
      });
      if (!resp.ok) break;
      const ct = resp.headers.get('content-type') || '';
      if (!ct.includes('json')) break;
      const data = await resp.json();
      if (!Array.isArray(data) || !data.length) break;

      for (const p of data) {
        const precio = parseFloat(p.price || p.regular_price || 0);
        const foto = p.images?.[0]?.src || null;
        const nombre = limpiar(p.name || '');
        if (!nombre) continue;
        productos.push({
          nombre,
          precio,
          descripcion: limpiar(p.short_description || p.description || '').slice(0, 200),
          foto,
          url: p.permalink || origin,
          sku: p.sku || '',
          categoria: p.categories?.[0]?.name || '',
        });
      }
      if (data.length < 100) break;
    } catch(e) { break; }
  }

  if (!productos.length) return null;
  return json({ ok: true, productos, total: productos.length, platform: 'WooCommerce API' }, headers);
}

// Tiendanube API
async function intentarTiendanubeAPI(url, headers) {
  try {
    const u = new URL(url);
    const apiUrl = `${u.origin}/api/v1/products?per_page=50`;
    const resp = await fetch(apiUrl, {
      headers: { ...FETCH_HEADERS, 'Accept': 'application/json' },
      redirect: 'follow',
    });
    if (!resp.ok) return null;
    const ct = resp.headers.get('content-type') || '';
    if (!ct.includes('json')) return null;
    const data = await resp.json();
    if (!Array.isArray(data) && !data.results) return null;

    const lista = Array.isArray(data) ? data : (data.results || []);
    const productos = lista.map(p => ({
      nombre: p.name?.es || p.name || '',
      precio: parseFloat(p.variants?.[0]?.price || p.price || 0),
      descripcion: limpiar(p.description?.es || p.description || '').slice(0, 200),
      foto: p.images?.[0]?.src || null,
      url: p.canonical_url || url,
    })).filter(p => p.nombre);

    if (!productos.length) return null;
    return json({ ok: true, productos, total: productos.length, debug: { platform: 'Tiendanube API' } }, headers);
  } catch(e) {
    return null;
  }
}

function detectarPlataforma(html) {
  if (html.includes('tiendanube') || html.includes('nuvemshop')) return 'Tiendanube';
  if (html.includes('woocommerce') || html.includes('WooCommerce')) return 'WooCommerce';
  if (html.includes('shopify') || html.includes('Shopify')) return 'Shopify';
  if (html.includes('mercadoshops') || html.includes('MercadoShops')) return 'MercadoShops';
  if (html.includes('prestashop') || html.includes('PrestaShop')) return 'PrestaShop';
  if (html.includes('jumpseller')) return 'Jumpseller';
  return 'Desconocida';
}

function extraerProductos(html, baseUrl) {
  const jsonldProds = extraerJsonLD(html, baseUrl);
  if (jsonldProds.length) return jsonldProds.slice(0, 100);

  const shopifyProds = extraerShopify(html, baseUrl);
  if (shopifyProds.length) return shopifyProds.slice(0, 100);

  const wooProds = extraerWooCommerce(html, baseUrl);
  if (wooProds.length) return wooProds.slice(0, 100);

  const tnProds = extraerTiendanubeHTML(html, baseUrl);
  if (tnProds.length) return tnProds.slice(0, 100);

  const genericProds = extraerGenerico(html, baseUrl);
  return genericProds.slice(0, 100);
}

function extraerJsonLD(html, baseUrl) {
  const prods = [];
  const re = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  for (const m of html.matchAll(re)) {
    try {
      const data = JSON.parse(m[1]);
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        if (item['@type'] === 'Product') pushProd(prods, fromJsonLDProduct(item, baseUrl));
        if (item['@type'] === 'ItemList') {
          for (const el of (item.itemListElement || [])) {
            const p = el.item || el;
            if (p['@type'] === 'Product') pushProd(prods, fromJsonLDProduct(p, baseUrl));
          }
        }
      }
    } catch(e) {}
  }
  return prods;
}

function fromJsonLDProduct(item, baseUrl) {
  return {
    nombre: item.name || '',
    precio: precioDeOffers(item.offers),
    descripcion: limpiar(item.description || '').slice(0, 200),
    foto: primerImagen(item.image),
    url: item.url || baseUrl,
  };
}

function extraerShopify(html, baseUrl) {
  const prods = [];
  const re = /var\s+meta\s*=\s*(\{[\s\S]*?\});/;
  const m = html.match(re);
  if (m) {
    try {
      const data = JSON.parse(m[1]);
      if (data.product) {
        pushProd(prods, {
          nombre: data.product.title || '',
          precio: parseFloat(data.product.price || 0) / 100,
          descripcion: limpiar(data.product.description || '').slice(0, 200),
          foto: data.product.featured_image || null,
          url: baseUrl,
        });
      }
    } catch(e) {}
  }
  const re2 = /ShopifyAnalytics\.meta\.product\s*=\s*(\{[\s\S]*?\});/;
  const m2 = html.match(re2);
  if (m2) {
    try {
      const p = JSON.parse(m2[1]);
      pushProd(prods, { nombre: p.title||'', precio: parseFloat(p.price||0)/100, descripcion:'', foto:null, url:baseUrl });
    } catch(e) {}
  }
  return prods;
}

function extraerWooCommerce(html, baseUrl) {
  const prods = [];
  const liRe = /<li[^>]*class="([^"]*\bproduct\b[^"]*)"[^>]*>/gi;
  for (const m of html.matchAll(liRe)) {
    if (/\bproducts\b/.test(m[1]) && !/\btype-product\b|\bpost-\d/.test(m[1])) continue;
    const start = m.index + m[0].length;
    const bloque = html.slice(start, start + 4000);

    const nombre = (
      textoClase(bloque, 'woocommerce-loop-product__title') ||
      textoClase(bloque, 'product-title') ||
      textoClase(bloque, 'product_title') ||
      textoClase(bloque, 'product-name') ||
      textoTag(bloque, 'h2') ||
      textoTag(bloque, 'h3')
    );
    if (!nombre || nombre.length < 2) continue;

    const bdi = bloque.match(/<bdi>([\s\S]*?)<\/bdi>/i);
    const precioStr = bdi ? limpiar(bdi[1]) : (textoClase(bloque, 'woocommerce-Price-amount') || textoClase(bloque, 'price') || '');
    const precio = precioTexto(precioStr) || precioHtml(bloque);
    const foto = imgSrc(bloque, baseUrl);
    const link = href(bloque, baseUrl);

    pushProd(prods, { nombre: limpiar(nombre), precio, foto, url: link, descripcion: '' });
    if (prods.length >= 100) break;
  }
  return prods;
}

function extraerTiendanubeHTML(html, baseUrl) {
  const prods = [];
  const patterns = [
    /<li[^>]*class="[^"]*\bitem\b[^"]*"[^>]*>([\s\S]*?)<\/li>/gi,
    /<div[^>]*class="[^"]*\bitem-list[^"]*"[^>]*>([\s\S]*?)<\/div>/gi,
    /<article[^>]*class="[^"]*\bitem\b[^"]*"[^>]*>([\s\S]*?)<\/article>/gi,
  ];
  for (const re of patterns) {
    const matches = [...html.matchAll(re)];
    if (matches.length < 2) continue;
    for (const m of matches) {
      const bloque = m[1];
      const nombre = (
        textoClase(bloque, 'item-name') ||
        textoClase(bloque, 'item-info__name') ||
        textoClase(bloque, 'product-name') ||
        textoTag(bloque, 'h2') ||
        textoTag(bloque, 'h3')
      );
      if (!nombre || nombre.length < 2) continue;
      pushProd(prods, {
        nombre: limpiar(nombre),
        precio: precioHtml(bloque),
        descripcion: '',
        foto: imgSrc(bloque, baseUrl),
        url: href(bloque, baseUrl),
      });
    }
    if (prods.length > 0) break;
  }
  return prods;
}

function extraerGenerico(html, baseUrl) {
  const prods = [];
  const blockRe = /<(?:div|li|article)[^>]*>([\s\S]{50,600}?)<\/(?:div|li|article)>/gi;
  let count = 0;
  for (const m of html.matchAll(blockRe)) {
    if (count > 200) break;
    count++;
    const bloque = m[1];
    if (!bloque.includes('$') && !/precio|price/i.test(bloque)) continue;
    const precio = precioHtml(bloque);
    if (!precio) continue;
    const nombre = textoTag(bloque, 'h2') || textoTag(bloque, 'h3') || textoTag(bloque, 'h4');
    if (!nombre || nombre.length < 2) continue;
    pushProd(prods, {
      nombre: limpiar(nombre),
      precio,
      descripcion: '',
      foto: imgSrc(bloque, baseUrl),
      url: href(bloque, baseUrl),
    });
    if (prods.length >= 50) break;
  }
  return prods;
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function json(data, headers) {
  return new Response(JSON.stringify(data), { headers });
}

function pushProd(arr, p) {
  if (p && p.nombre && p.nombre.length > 1) arr.push(p);
}

function precioDeOffers(offers) {
  if (!offers) return 0;
  const list = Array.isArray(offers) ? offers : [offers];
  for (const o of list) {
    const p = parseFloat(o.price || o.lowPrice || 0);
    if (p > 0) return p;
  }
  return 0;
}

function primerImagen(img) {
  if (!img) return null;
  if (typeof img === 'string') return img;
  if (Array.isArray(img)) return img[0] || null;
  if (typeof img === 'object') return img.url || img.contentUrl || null;
  return null;
}

function precioHtml(html) {
  const pats = [
    /class="[^"]*(?:price|precio|monto|valor)[^"]*"[^>]*>[\s\S]{0,60}?\$\s*([\d.,]+)/i,
    /\$\s*([\d.,]+)/,
    /(?:precio|price)[^\d$]*([\d.,]+)/i,
  ];
  for (const p of pats) {
    const m = html.match(p);
    if (m) {
      const val = parsePrecioAR(m[1]);
      if (val > 0) return val;
    }
  }
  return 0;
}

function precioTexto(txt) {
  if (!txt) return 0;
  const m = txt.match(/([\d.,]+)/);
  if (!m) return 0;
  return parsePrecioAR(m[1]);
}

function parsePrecioAR(raw) {
  raw = raw.replace(/\s/g, '');
  if (/\d\.\d{3},\d/.test(raw)) return parseFloat(raw.replace(/\./g, '').replace(',', '.'));
  if (/\d,\d{3}\.\d/.test(raw)) return parseFloat(raw.replace(/,/g, ''));
  if (/^\d{1,3}(\.\d{3})+$/.test(raw)) return parseFloat(raw.replace(/\./g, ''));
  if (/^\d+,\d{1,2}$/.test(raw)) return parseFloat(raw.replace(',', '.'));
  return parseFloat(raw) || 0;
}

function textoTag(html, tag) {
  const m = html.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'));
  return m ? limpiar(m[1]) : '';
}

function textoClase(html, cls) {
  const escaped = cls.replace(/[-_]/g, '[-_]');
  const m = html.match(new RegExp(`class="[^"]*\\b${escaped}\\b[^"]*"[^>]*>([\\s\\S]*?)<\\/`, 'i'));
  return m ? limpiar(m[1]) : '';
}

function imgSrc(html, base) {
  const m = html.match(/<img[^>]+(?:data-src|data-lazy-src|src)=["']([^"']+\.(jpg|jpeg|png|webp|gif)[^"']*)["']/i)
         || html.match(/<img[^>]+src=["']([^"']+)["']/i);
  if (!m) return null;
  const src = m[1];
  if (src.startsWith('data:')) return null;
  return absoluta(src, base);
}

function href(html, base) {
  const m = html.match(/<a[^>]+href=["']([^"'#?][^"']*)["']/i);
  return m ? absoluta(m[1], base) : base;
}

function absoluta(path, base) {
  if (!path) return null;
  if (path.startsWith('http')) return path;
  if (path.startsWith('//')) return 'https:' + path;
  try {
    const origin = new URL(base).origin;
    return origin + (path.startsWith('/') ? path : '/' + path);
  } catch(e) { return path; }
}

function limpiar(s) {
  return s
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&#\d+;/g, '').replace(/&[a-z]+;/g, '')
    .replace(/\s+/g, ' ').trim();
}
