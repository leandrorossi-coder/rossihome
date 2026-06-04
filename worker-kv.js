export default {
  async fetch(request, env, ctx) {
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    const json = (data) => new Response(JSON.stringify(data), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

    try {
      const url = new URL(request.url);
      if (url.searchParams.get('debug') === 'winco') {
        const wfA = await env.RH_KV.get('rh_winco_fotos_a', 'json');
        const wfB = await env.RH_KV.get('rh_winco_fotos_b', 'json');
        return json({ ok: true, wfA_keys: Object.keys(wfA||{}).length, wfB_keys: Object.keys(wfB||{}).length });
      }

      if (request.method === 'GET') {
        const [main, productos, wfA, wfB] = await Promise.all([
          env.RH_KV.get('rh_main', 'json'),
          env.RH_KV.get('rh_productos', 'json'),
          env.RH_KV.get('rh_winco_fotos_a', 'json'),
          env.RH_KV.get('rh_winco_fotos_b', 'json'),
        ]);
        const wincoFotos = { ...(wfA || {}), ...(wfB || {}) };
        const productosConFotos = (productos || []).map(p => {
          if (p.proveedor === 'Winco' && wincoFotos[p.codigoOriginal]) {
            return { ...p, fotos: [wincoFotos[p.codigoOriginal]], fotoPrincipal: 0 };
          }
          return p;
        });
        const datos = { ...(main || {}), productos: productosConFotos };
        return json({ ok: true, datos });
      }

      if (request.method === 'POST') {
        const body = await request.text();
        let parsed = {};
        try { parsed = JSON.parse(body); } catch(e) {}

        if (parsed.action === 'scrape') {
          return await handleScrape(parsed.url, { ...corsHeaders, 'Content-Type': 'application/json' });
        }

        if (parsed.action === 'guardar') {
          const { action, productos, productosDirty, ...main } = parsed;

          const writes = [env.RH_KV.put('rh_main', JSON.stringify(main))];
          if (productosDirty || productos?.length > 0) {
            // Separar fotos Winco de los productos para no superar límite de 25MB por clave
            const wincoFotosNew = {};
            const productosSinWincoFotos = (productos || []).map(p => {
              if (p.proveedor === 'Winco' && p.fotos && p.fotos.length > 0) {
                wincoFotosNew[p.codigoOriginal] = p.fotos[0];
                return { ...p, fotos: [] };
              }
              return p;
            });
            writes.push(env.RH_KV.put('rh_productos', JSON.stringify(productosSinWincoFotos)));

            if (Object.keys(wincoFotosNew).length > 0) {
              const [exA, exB] = await Promise.all([
                env.RH_KV.get('rh_winco_fotos_a', 'json'),
                env.RH_KV.get('rh_winco_fotos_b', 'json'),
              ]);
              const merged = { ...(exA || {}), ...(exB || {}), ...wincoFotosNew };
              const entries = Object.entries(merged);
              const half = Math.ceil(entries.length / 2);
              writes.push(env.RH_KV.put('rh_winco_fotos_a', JSON.stringify(Object.fromEntries(entries.slice(0, half)))));
              writes.push(env.RH_KV.put('rh_winco_fotos_b', JSON.stringify(Object.fromEntries(entries.slice(half)))));
            }
          }

          await Promise.all(writes);
          return json({ ok: true });
        }

        return json({ ok: false, error: 'Acción desconocida' });
      }

    } catch(e) {
      return json({ ok: false, error: e.message });
    }
  }
};

// ── SCRAPING (igual que antes) ────────────────────────────────────────────────

const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  'Accept-Language': 'es-AR,es;q=0.9,en;q=0.7',
  'Accept-Encoding': 'gzip, deflate, br',
  'Cache-Control': 'no-cache',
  'Pragma': 'no-cache',
};

async function handleScrape(url, headers) {
  if (!url) return new Response(JSON.stringify({ ok: false, error: 'URL requerida' }), { headers });
  try {
    const u = new URL(url);
    const storeRes = await intentarWooStoreAPI(u.origin, headers);
    if (storeRes) return storeRes;
    const wooRes = await intentarWooAPI(u.origin, headers);
    if (wooRes) return wooRes;
    const tnRes = await intentarTiendanubeAPI(url, headers);
    if (tnRes) return tnRes;
    const resp = await fetch(url, { headers: FETCH_HEADERS, redirect: 'follow' });
    if (!resp.ok) return new Response(JSON.stringify({ ok: false, error: `HTTP ${resp.status}` }), { headers });
    const html = await resp.text();
    const finalUrl = resp.url || url;
    const platform = detectarPlataforma(html);
    const productos = extraerProductos(html, finalUrl);
    if (!productos.length) return new Response(JSON.stringify({ ok: false, error: 'No se encontraron productos' }), { headers });
    return new Response(JSON.stringify({ ok: true, productos, total: productos.length, platform }), { headers });
  } catch(e) {
    return new Response(JSON.stringify({ ok: false, error: e.message }), { headers });
  }
}

async function intentarWooStoreAPI(origin, headers) {
  const productos = [];
  for (let page = 1; page <= 10; page++) {
    try {
      const resp = await fetch(`${origin}/wp-json/wc/store/v1/products?per_page=100&page=${page}`, { headers: { ...FETCH_HEADERS, 'Accept': 'application/json' }, redirect: 'follow' });
      if (!resp.ok) break;
      const ct = resp.headers.get('content-type') || '';
      if (!ct.includes('json')) break;
      const data = await resp.json();
      if (!Array.isArray(data) || !data.length) break;
      for (const p of data) {
        const nombre = limpiar(p.name || '');
        if (!nombre) continue;
        const precio = parsePrecioAR((p.prices?.price || p.price_html || '0').replace(/[^\d.,]/g, ''));
        productos.push({ nombre, precio, descripcion: limpiar(p.short_description || '').slice(0, 200), foto: p.images?.[0]?.src || null, url: p.permalink || origin, sku: p.sku || '', categoria: p.categories?.[0]?.name || '' });
      }
      if (data.length < 100) break;
    } catch(e) { break; }
  }
  if (!productos.length) return null;
  return new Response(JSON.stringify({ ok: true, productos, total: productos.length, platform: 'WooCommerce Store API' }), { headers });
}

async function intentarWooAPI(origin, headers) {
  const productos = [];
  for (let page = 1; page <= 5; page++) {
    try {
      const resp = await fetch(`${origin}/wp-json/wc/v3/products?per_page=100&page=${page}&status=publish`, { headers: { ...FETCH_HEADERS, 'Accept': 'application/json' }, redirect: 'follow' });
      if (!resp.ok) break;
      const ct = resp.headers.get('content-type') || '';
      if (!ct.includes('json')) break;
      const data = await resp.json();
      if (!Array.isArray(data) || !data.length) break;
      for (const p of data) {
        const nombre = limpiar(p.name || '');
        if (!nombre) continue;
        productos.push({ nombre, precio: parseFloat(p.price || p.regular_price || 0), descripcion: limpiar(p.short_description || p.description || '').slice(0, 200), foto: p.images?.[0]?.src || null, url: p.permalink || origin, sku: p.sku || '', categoria: p.categories?.[0]?.name || '' });
      }
      if (data.length < 100) break;
    } catch(e) { break; }
  }
  if (!productos.length) return null;
  return new Response(JSON.stringify({ ok: true, productos, total: productos.length, platform: 'WooCommerce API' }), { headers });
}

async function intentarTiendanubeAPI(url, headers) {
  try {
    const u = new URL(url);
    const resp = await fetch(`${u.origin}/api/v1/products?per_page=50`, { headers: { ...FETCH_HEADERS, 'Accept': 'application/json' }, redirect: 'follow' });
    if (!resp.ok) return null;
    const ct = resp.headers.get('content-type') || '';
    if (!ct.includes('json')) return null;
    const data = await resp.json();
    if (!Array.isArray(data) && !data.results) return null;
    const lista = Array.isArray(data) ? data : (data.results || []);
    const productos = lista.map(p => ({ nombre: p.name?.es || p.name || '', precio: parseFloat(p.variants?.[0]?.price || p.price || 0), descripcion: limpiar(p.description?.es || p.description || '').slice(0, 200), foto: p.images?.[0]?.src || null, url: p.canonical_url || url })).filter(p => p.nombre);
    if (!productos.length) return null;
    return new Response(JSON.stringify({ ok: true, productos, total: productos.length, platform: 'Tiendanube API' }), { headers });
  } catch(e) { return null; }
}

function detectarPlataforma(html) {
  if (html.includes('tiendanube') || html.includes('nuvemshop')) return 'Tiendanube';
  if (html.includes('woocommerce') || html.includes('WooCommerce')) return 'WooCommerce';
  if (html.includes('shopify') || html.includes('Shopify')) return 'Shopify';
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
  return extraerGenerico(html, baseUrl).slice(0, 100);
}

function extraerJsonLD(html, baseUrl) {
  const prods = [];
  const re = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  for (const m of html.matchAll(re)) {
    try {
      const data = JSON.parse(m[1]);
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        if (item['@type'] === 'Product') pushProd(prods, { nombre: item.name || '', precio: precioDeOffers(item.offers), descripcion: limpiar(item.description || '').slice(0, 200), foto: primerImagen(item.image), url: item.url || baseUrl });
        if (item['@type'] === 'ItemList') for (const el of (item.itemListElement || [])) { const p = el.item || el; if (p['@type'] === 'Product') pushProd(prods, { nombre: p.name || '', precio: precioDeOffers(p.offers), descripcion: limpiar(p.description || '').slice(0, 200), foto: primerImagen(p.image), url: p.url || baseUrl }); }
      }
    } catch(e) {}
  }
  return prods;
}

function extraerShopify(html, baseUrl) {
  const prods = [];
  const m = html.match(/var\s+meta\s*=\s*(\{[\s\S]*?\});/);
  if (m) { try { const data = JSON.parse(m[1]); if (data.product) pushProd(prods, { nombre: data.product.title || '', precio: parseFloat(data.product.price || 0) / 100, descripcion: '', foto: data.product.featured_image || null, url: baseUrl }); } catch(e) {} }
  return prods;
}

function extraerWooCommerce(html, baseUrl) {
  const prods = [];
  const liRe = /<li[^>]*class="([^"]*\bproduct\b[^"]*)"[^>]*>/gi;
  for (const m of html.matchAll(liRe)) {
    if (/\bproducts\b/.test(m[1]) && !/\btype-product\b|\bpost-\d/.test(m[1])) continue;
    const bloque = html.slice(m.index + m[0].length, m.index + m[0].length + 4000);
    const nombre = textoClase(bloque, 'woocommerce-loop-product__title') || textoClase(bloque, 'product-title') || textoTag(bloque, 'h2') || textoTag(bloque, 'h3');
    if (!nombre || nombre.length < 2) continue;
    const bdi = bloque.match(/<bdi>([\s\S]*?)<\/bdi>/i);
    const precioStr = bdi ? limpiar(bdi[1]) : textoClase(bloque, 'woocommerce-Price-amount') || '';
    pushProd(prods, { nombre: limpiar(nombre), precio: precioTexto(precioStr) || precioHtml(bloque), foto: imgSrc(bloque, baseUrl), url: href(bloque, baseUrl), descripcion: '' });
    if (prods.length >= 100) break;
  }
  return prods;
}

function extraerTiendanubeHTML(html, baseUrl) {
  const prods = [];
  for (const re of [/<li[^>]*class="[^"]*\bitem\b[^"]*"[^>]*>([\s\S]*?)<\/li>/gi, /<article[^>]*class="[^"]*\bitem\b[^"]*"[^>]*>([\s\S]*?)<\/article>/gi]) {
    const matches = [...html.matchAll(re)];
    if (matches.length < 2) continue;
    for (const m of matches) {
      const b = m[1];
      const nombre = textoClase(b, 'item-name') || textoClase(b, 'item-info__name') || textoTag(b, 'h2') || textoTag(b, 'h3');
      if (!nombre || nombre.length < 2) continue;
      pushProd(prods, { nombre: limpiar(nombre), precio: precioHtml(b), descripcion: '', foto: imgSrc(b, baseUrl), url: href(b, baseUrl) });
    }
    if (prods.length > 0) break;
  }
  return prods;
}

function extraerGenerico(html, baseUrl) {
  const prods = [];
  let count = 0;
  for (const m of html.matchAll(/<(?:div|li|article)[^>]*>([\s\S]{50,600}?)<\/(?:div|li|article)>/gi)) {
    if (count++ > 200) break;
    const b = m[1];
    if (!b.includes('$') && !/precio|price/i.test(b)) continue;
    const precio = precioHtml(b);
    if (!precio) continue;
    const nombre = textoTag(b, 'h2') || textoTag(b, 'h3') || textoTag(b, 'h4');
    if (!nombre || nombre.length < 2) continue;
    pushProd(prods, { nombre: limpiar(nombre), precio, descripcion: '', foto: imgSrc(b, baseUrl), url: href(b, baseUrl) });
    if (prods.length >= 50) break;
  }
  return prods;
}

function pushProd(arr, p) { if (p && p.nombre && p.nombre.length > 1) arr.push(p); }
function precioDeOffers(offers) { if (!offers) return 0; const list = Array.isArray(offers) ? offers : [offers]; for (const o of list) { const p = parseFloat(o.price || o.lowPrice || 0); if (p > 0) return p; } return 0; }
function primerImagen(img) { if (!img) return null; if (typeof img === 'string') return img; if (Array.isArray(img)) return img[0] || null; if (typeof img === 'object') return img.url || img.contentUrl || null; return null; }
function precioHtml(html) { for (const p of [/class="[^"]*(?:price|precio)[^"]*"[^>]*>[\s\S]{0,60}?\$\s*([\d.,]+)/i, /\$\s*([\d.,]+)/, /(?:precio|price)[^\d$]*([\d.,]+)/i]) { const m = html.match(p); if (m) { const val = parsePrecioAR(m[1]); if (val > 0) return val; } } return 0; }
function precioTexto(txt) { if (!txt) return 0; const m = txt.match(/([\d.,]+)/); return m ? parsePrecioAR(m[1]) : 0; }
function parsePrecioAR(raw) { raw = (raw||'').replace(/\s/g, ''); if (/\d\.\d{3},\d/.test(raw)) return parseFloat(raw.replace(/\./g, '').replace(',', '.')); if (/\d,\d{3}\.\d/.test(raw)) return parseFloat(raw.replace(/,/g, '')); if (/^\d{1,3}(\.\d{3})+$/.test(raw)) return parseFloat(raw.replace(/\./g, '')); if (/^\d+,\d{1,2}$/.test(raw)) return parseFloat(raw.replace(',', '.')); return parseFloat(raw) || 0; }
function textoTag(html, tag) { const m = html.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i')); return m ? limpiar(m[1]) : ''; }
function textoClase(html, cls) { const m = html.match(new RegExp(`class="[^"]*\\b${cls.replace(/[-_]/g,'[-_]')}\\b[^"]*"[^>]*>([\\s\\S]*?)<\\/`, 'i')); return m ? limpiar(m[1]) : ''; }
function imgSrc(html, base) { const m = html.match(/<img[^>]+(?:data-src|data-lazy-src|src)=["']([^"']+\.(jpg|jpeg|png|webp|gif)[^"']*)["']/i) || html.match(/<img[^>]+src=["']([^"']+)["']/i); if (!m) return null; const src = m[1]; if (src.startsWith('data:')) return null; return absoluta(src, base); }
function href(html, base) { const m = html.match(/<a[^>]+href=["']([^"'#?][^"']*)["']/i); return m ? absoluta(m[1], base) : base; }
function absoluta(path, base) { if (!path) return null; if (path.startsWith('http')) return path; if (path.startsWith('//')) return 'https:' + path; try { return new URL(base).origin + (path.startsWith('/') ? path : '/' + path); } catch(e) { return path; } }
function limpiar(s) { return s.replace(/<[^>]+>/g, ' ').replace(/&amp;/g,'&').replace(/&nbsp;/g,' ').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&#\d+;/g,'').replace(/&[a-z]+;/g,'').replace(/\s+/g,' ').trim(); }
