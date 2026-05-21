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

        // Proxy a Google Apps Script
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
    // Intentar Tiendanube API primero si la URL es de una tienda conocida
    const tiendanubeRes = await intentarTiendanubeAPI(url, headers);
    if (tiendanubeRes) return tiendanubeRes;

    // Fetch HTML normal
    const resp = await fetch(url, { headers: FETCH_HEADERS, redirect: 'follow' });

    if (!resp.ok) {
      return json({ ok: false, error: `El sitio respondió HTTP ${resp.status}. Puede tener protección anti-bot.` }, headers);
    }

    const html = await resp.text();
    const finalUrl = resp.url || url;

    // Detectar plataforma y extraer productos
    const productos = extraerProductos(html, finalUrl);
    const debug = {
      platform: detectarPlataforma(html),
      htmlLen: html.length,
      tieneJsonLD: html.includes('application/ld+json'),
    };

    if (!productos.length) {
      return json({
        ok: false,
        error: `No se encontraron productos. Plataforma detectada: ${debug.platform}. El sitio puede usar JavaScript para cargar los productos (SPA/React/Vue), lo cual no es posible scrapear desde el Worker.`,
        debug
      }, headers);
    }

    return json({ ok: true, productos, total: productos.length, debug }, headers);

  } catch(e) {
    return json({ ok: false, error: e.message }, headers);
  }
}

// Intenta la API REST de Tiendanube
async function intentarTiendanubeAPI(url, headers) {
  try {
    const u = new URL(url);
    // Tiendanube usa su propia API pública sin auth para listar productos
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
  // 1. JSON-LD
  const jsonldProds = extraerJsonLD(html, baseUrl);
  if (jsonldProds.length) return jsonldProds.slice(0, 100);

  // 2. Shopify (JSON en window.productData o similar)
  const shopifyProds = extraerShopify(html, baseUrl);
  if (shopifyProds.length) return shopifyProds.slice(0, 100);

  // 3. WooCommerce HTML
  const wooProds = extraerWooCommerce(html, baseUrl);
  if (wooProds.length) return wooProds.slice(0, 100);

  // 4. Tiendanube HTML (fallback si la API falló)
  const tnProds = extraerTiendanubeHTML(html, baseUrl);
  if (tnProds.length) return tnProds.slice(0, 100);

  // 5. PrestaShop / genérico
  const genericProds = extraerGenerico(html, baseUrl);
  return genericProds.slice(0, 100);
}

// ── JSON-LD ──────────────────────────────────────────────────────────────────
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

// ── Shopify ──────────────────────────────────────────────────────────────────
function extraerShopify(html, baseUrl) {
  const prods = [];
  // Shopify embeds product JSON in script tags
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
  // Also try window.ShopifyAnalytics
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

// ── WooCommerce ──────────────────────────────────────────────────────────────
function extraerWooCommerce(html, baseUrl) {
  const prods = [];
  const patterns = [
    /<li[^>]*class="[^"]*\bproduct\b[^"]*"[^>]*>([\s\S]*?)<\/li>/gi,
    /<article[^>]*class="[^"]*\bproduct\b[^"]*"[^>]*>([\s\S]*?)<\/article>/gi,
    /<div[^>]*class="[^"]*\bproduct[-_](?:item|card|thumb)\b[^"]*"[^>]*>([\s\S]*?)<\/div>/gi,
  ];
  for (const re of patterns) {
    const matches = [...html.matchAll(re)];
    if (matches.length < 2) continue;
    for (const m of matches) {
      const bloque = m[1];
      const nombre = (
        textoClase(bloque, 'woocommerce-loop-product__title') ||
        textoClase(bloque, 'product-title') ||
        textoClase(bloque, 'product_title') ||
        textoClase(bloque, 'product-name') ||
        textoTag(bloque, 'h2') ||
        textoTag(bloque, 'h3')
      );
      if (!nombre || nombre.length < 2) continue;
      const precioBloque = textoClase(bloque, 'woocommerce-Price-amount') || textoClase(bloque, 'price') || '';
      pushProd(prods, {
        nombre: limpiar(nombre),
        precio: precioTexto(precioBloque) || precioHtml(bloque),
        descripcion: limpiar(textoClase(bloque, 'description') || '').slice(0, 200),
        foto: imgSrc(bloque, baseUrl),
        url: href(bloque, baseUrl),
      });
    }
    if (prods.length > 0) break;
  }
  return prods;
}

// ── Tiendanube HTML ──────────────────────────────────────────────────────────
function extraerTiendanubeHTML(html, baseUrl) {
  const prods = [];
  // Tiendanube patterns
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

// ── Genérico: cualquier elemento con nombre+precio ───────────────────────────
function extraerGenerico(html, baseUrl) {
  const prods = [];
  // Buscar cualquier bloque repetido que tenga precio
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
  // 1.234,56 → 1234.56
  if (/\d\.\d{3},\d/.test(raw)) return parseFloat(raw.replace(/\./g, '').replace(',', '.'));
  // 1,234.56 → 1234.56
  if (/\d,\d{3}\.\d/.test(raw)) return parseFloat(raw.replace(/,/g, ''));
  // 1.234 (solo miles) → 1234
  if (/^\d{1,3}(\.\d{3})+$/.test(raw)) return parseFloat(raw.replace(/\./g, ''));
  // 1234,56 → 1234.56
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
