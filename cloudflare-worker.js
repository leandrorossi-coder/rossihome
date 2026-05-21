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

        // ── Acción: scraping de proveedor ──
        if (parsed.action === 'scrape') {
          return await handleScrape(parsed.url, jsonHeaders);
        }

        // ── Default: proxy a Google Apps Script (backup) ──
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
        // GET: leer datos desde Google Drive
        const resp = await fetch(SCRIPT_URL + '?api=1', {
          method: 'GET',
          redirect: 'follow',
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

async function handleScrape(url, headers) {
  if (!url) {
    return new Response(JSON.stringify({ ok: false, error: 'URL requerida' }), { headers });
  }

  try {
    const resp = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'es-AR,es;q=0.9,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
      },
      redirect: 'follow',
    });

    if (!resp.ok) {
      return new Response(JSON.stringify({ ok: false, error: `HTTP ${resp.status} al acceder a ${url}` }), { headers });
    }

    const html = await resp.text();
    const productos = extraerProductos(html, resp.url || url);

    return new Response(JSON.stringify({ ok: true, productos, url: resp.url || url, total: productos.length }), { headers });
  } catch(e) {
    return new Response(JSON.stringify({ ok: false, error: e.message }), { headers });
  }
}

function extraerProductos(html, baseUrl) {
  const productos = [];

  // ── 1. JSON-LD (schema.org Product / ItemList) — más confiable ──
  const jsonldRe = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  for (const match of html.matchAll(jsonldRe)) {
    try {
      const data = JSON.parse(match[1]);
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        if (item['@type'] === 'Product') {
          pushProd(productos, {
            nombre: item.name || '',
            precio: precioDeOffers(item.offers),
            descripcion: limpiar(item.description || '').slice(0, 200),
            foto: primerImagen(item.image),
            url: item.url || baseUrl,
          });
        }
        if (item['@type'] === 'ItemList' && item.itemListElement) {
          for (const el of item.itemListElement) {
            const p = el.item || el;
            if (p['@type'] === 'Product') {
              pushProd(productos, {
                nombre: p.name || '',
                precio: precioDeOffers(p.offers),
                descripcion: limpiar(p.description || '').slice(0, 200),
                foto: primerImagen(p.image),
                url: p.url || baseUrl,
              });
            }
          }
        }
      }
    } catch(e) {}
  }
  if (productos.length > 0) return productos.slice(0, 100);

  // ── 2. WooCommerce / tiendas comunes (li.product, article.product) ──
  const bloques = extraerBloques(html, [
    /<li[^>]*class="[^"]*\bproduct\b[^"]*"[^>]*>([\s\S]*?)<\/li>/gi,
    /<article[^>]*class="[^"]*\bproduct\b[^"]*"[^>]*>([\s\S]*?)<\/article>/gi,
    /<div[^>]*class="[^"]*\bproduct[-_]item\b[^"]*"[^>]*>([\s\S]*?)<\/div>/gi,
    /<div[^>]*class="[^"]*\bitem[-_]product\b[^"]*"[^>]*>([\s\S]*?)<\/div>/gi,
  ]);

  for (const bloque of bloques) {
    const nombre = (
      textoTag(bloque, 'h2') ||
      textoTag(bloque, 'h3') ||
      textoClase(bloque, 'product-title') ||
      textoClase(bloque, 'woocommerce-loop-product__title') ||
      textoClase(bloque, 'product-name') ||
      textoClase(bloque, 'nombre')
    );
    if (!nombre || nombre.length < 2) continue;
    pushProd(productos, {
      nombre: limpiar(nombre),
      precio: precioHtml(bloque),
      descripcion: limpiar(textoClase(bloque, 'description') || textoClase(bloque, 'descripcion') || '').slice(0, 200),
      foto: imgSrc(bloque, baseUrl),
      url: href(bloque, baseUrl),
    });
  }
  if (productos.length > 0) return productos.slice(0, 100);

  // ── 3. Tiendanube / MercadoShops (data-* attributes) ──
  const tiendaNubeRe = /data-product[^>]*>([\s\S]*?)<\/(?:div|article|li)>/gi;
  for (const m of html.matchAll(tiendaNubeRe)) {
    const bloque = m[1];
    const nombre = textoClase(bloque, 'item-name') || textoClase(bloque, 'product-name') || textoTag(bloque, 'h2') || textoTag(bloque, 'h3');
    if (!nombre) continue;
    pushProd(productos, {
      nombre: limpiar(nombre),
      precio: precioHtml(bloque),
      descripcion: '',
      foto: imgSrc(bloque, baseUrl),
      url: href(bloque, baseUrl),
    });
  }

  return productos.slice(0, 100);
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function pushProd(arr, p) {
  if (p.nombre && p.nombre.length > 1) arr.push(p);
}

function extraerBloques(html, patterns) {
  for (const re of patterns) {
    const matches = [...html.matchAll(re)];
    if (matches.length >= 2) return matches.map(m => m[1]);
  }
  return [];
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
  return null;
}

function precioHtml(html) {
  const pats = [
    /class="[^"]*(?:price|precio|monto)[^"]*"[^>]*>\s*\$?\s*([\d.,']+)/i,
    /\$\s*([\d.,']+)/,
    /(?:precio|price)[^$\d]*([\d.,']+)/i,
  ];
  for (const p of pats) {
    const m = html.match(p);
    if (m) {
      // Argentina usa punto como miles y coma como decimal, o al revés
      let raw = m[1].replace(/\s/g, '');
      // Si tiene punto y coma: 1.234,56 → eliminar . y cambiar , por .
      if (/\d\.\d{3},\d/.test(raw)) raw = raw.replace(/\./g, '').replace(',', '.');
      // Si tiene coma como miles: 1,234.56 → eliminar ,
      else if (/\d,\d{3}\.\d/.test(raw)) raw = raw.replace(/,/g, '');
      // Solo puntos (miles argentinos): 1.234 → eliminar .
      else if (/^\d{1,3}(\.\d{3})+$/.test(raw)) raw = raw.replace(/\./g, '');
      // Solo coma como decimal: 1234,56 → cambiar por .
      else raw = raw.replace(',', '.');
      const val = parseFloat(raw);
      if (val > 0 && val < 100_000_000) return val;
    }
  }
  return 0;
}

function textoTag(html, tag) {
  const m = html.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i'));
  return m ? limpiar(m[1]) : '';
}

function textoClase(html, cls) {
  const m = html.match(new RegExp(`class="[^"]*\\b${cls}\\b[^"]*"[^>]*>([\\s\\S]*?)<\\/`, 'i'));
  return m ? limpiar(m[1]) : '';
}

function imgSrc(html, base) {
  // data-src (lazy load) primero, luego src
  const m = html.match(/<img[^>]+(?:data-src|src)=["']([^"']+)["']/i)
         || html.match(/<img[^>]+src=["']([^"']+)["']/i);
  if (!m) return null;
  return absoluta(m[1], base);
}

function href(html, base) {
  const m = html.match(/<a[^>]+href=["']([^"'#][^"']+)["']/i);
  return m ? absoluta(m[1], base) : base;
}

function absoluta(path, base) {
  if (!path) return null;
  if (path.startsWith('http')) return path;
  if (path.startsWith('//')) return 'https:' + path;
  const origin = new URL(base).origin;
  return origin + (path.startsWith('/') ? path : '/' + path);
}

function limpiar(s) {
  return s.replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ')
          .replace(/&#\d+;/g, '').replace(/\s+/g, ' ').trim();
}
