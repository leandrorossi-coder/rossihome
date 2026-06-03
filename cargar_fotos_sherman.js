(function(){
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.accept = 'image/*';
  input.onchange = async function(){
    const files = [...input.files];
    const MAPEO = {
      'TECC055': ['ELECTRICO','COLGAR','55'],
      'TECC085': ['ELECTRICO','COLGAR','85'],
      'TEPC055': ['ELECTRICO','PIE','55'],
      'TEPC085': ['ELECTRICO','PIE','85'],
      'TPGP050': ['GAS','PIE','50'],
      'TPGP080': ['GAS','PIE','80'],
      'TPGP120': ['GAS','PIE','120'],
    };
    const fotosPorSku = {};
    for(const file of files){
      const sku = Object.keys(MAPEO).find(k => file.name.toUpperCase().includes(k));
      if(!sku) continue;
      const b64 = await new Promise(r=>{
        const fr = new FileReader();
        fr.onload = e => r(e.target.result);
        fr.readAsDataURL(file);
      });
      fotosPorSku[sku] = fotosPorSku[sku] || [];
      fotosPorSku[sku].push(b64);
    }
    let prods = JSON.parse(localStorage.getItem('rh_productos')||'[]');
    let n = 0;
    for(const [sku, fotos] of Object.entries(fotosPorSku)){
      const kws = MAPEO[sku];
      const p = prods.find(x => kws.every(k => (x.nombre||'').toUpperCase().includes(k)) && (x.proveedor||'').toUpperCase().includes('RHEEM'));
      if(p){ p.fotos = fotos; p.fotoPrincipal = 0; n++; console.log('✅', p.nombre); }
    }
    localStorage.setItem('rh_productos', JSON.stringify(prods));
    if(typeof syncCloud==='function') await syncCloud();
    alert('✅ ' + n + ' productos actualizados. Recargá la página.');
  };
  input.click();
})();
