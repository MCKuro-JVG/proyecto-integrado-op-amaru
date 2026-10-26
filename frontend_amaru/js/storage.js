/* Recuperación conservadora del estado DEMO. No borra claves ni datos originales. */
(() => {
  'use strict';
  const KEY = 'opticas-amaru.demo.v2';
  let writable = true;
  let lastRaw = null;
  let pending = [];
  const text = (v, fallback = '') => typeof v === 'string' ? v : typeof v === 'number' ? String(v) : fallback;
  const object = v => v && typeof v === 'object' && !Array.isArray(v);
  const validDate = v => typeof v === 'string' && Number.isFinite(Date.parse(v));
  const stamp = () => new Date().toISOString();
  function tell(message) { if (!pending.includes(message)) pending.push(message); }
  function preserve(raw) {
    const key = KEY + '.respaldo.' + Date.now();
    localStorage.setItem(key, raw);
    return key;
  }
  function normalize(input, seed) {
    if (!object(input) || Number(input.version || 1) > 2) throw new Error('El formato guardado no se puede adaptar automáticamente.');
    const defaults = seed();
    const aliases = { clients:'clientes', orders:'pedidos', documents:'documentos', requests:'solicitudes', quotes:'cotizaciones', warranties:'garantias', recipes:'recetas', inventory:'inventario' };
    if (!Object.keys(aliases).some(k => Object.hasOwn(input,k) || Object.hasOwn(input,aliases[k]))) throw new Error('No hay colecciones reconocibles en los datos guardados.');
    const d = {...input,version:2};
    for (const [key, alias] of Object.entries(aliases)) {
      const value = input[key] ?? input[alias];
      d[key] = (Array.isArray(value) ? value : object(value) ? Object.values(value) : []).filter(object).map((r,i) => ({...r,id:text(r.id ?? r.folio,`RECUPERADO-${key}-${i+1}`)}));
    }
    d.clients = d.clients.map(c=>({...c,name:text(c.name ?? c.nombre,'Cliente DEMO recuperado'),rut:text(c.rut),phone:text(c.phone ?? c.telefono),email:text(c.email ?? c.correo),type:text(c.type,'Particular'),consent:c.consent===true}));
    const state = s => ({'Listo para retiro':'Disponible para retiro','Lista para retiro':'Disponible para retiro','Entregada':'Entregado','Pendiente':'Registrada'}[s] || text(s,'Registrada'));
    const person = id => d.clients.find(c=>c.id===text(id));
    d.orders = d.orders.map(o=>({...o,clientId:text(o.clientId ?? o.clienteId),product:text(o.product ?? o.producto,'Producto DEMO pendiente de descripción'),status:state(o.status ?? o.estado),created:validDate(o.created)?o.created:stamp(),history:(Array.isArray(o.history)?o.history:[]).filter(object).map(h=>({...h,at:validDate(h.at)?h.at:stamp(),status:state(h.status),by:text(h.by,'Registro DEMO recuperado')}))}));
    d.requests = d.requests.map(r=>({...r,type:text(r.type,'contacto'),name:text(r.name ?? r.nombre,'Visitante DEMO'),phone:text(r.phone ?? r.telefono),email:text(r.email ?? r.correo),service:text(r.service,'Consulta'),reason:text(r.reason ?? r.motivo),status:text(r.status,'Nueva'),day:text(r.day),slot:text(r.slot),history:(Array.isArray(r.history)?r.history:[]).filter(object)}));
    d.recipes = d.recipes.map(r=>({...r,clientId:text(r.clientId),issued:validDate(r.issued)?r.issued:null,fileName:text(r.fileName,'Referencia sin archivo')}));
    d.quotes = d.quotes.map(q=>({...q,clientId:text(q.clientId),product:text(q.product,'Propuesta DEMO recuperada'),status:text(q.status,'Borrador'),total:Number.isFinite(Number(q.total))?Number(q.total):0}));
    d.warranties = d.warranties.map(w=>({...w,orderId:text(w.orderId),reason:text(w.reason),status:text(w.status,'En revisión'),decision:text(w.decision)}));
    d.inventory = d.inventory.map(i=>({...i,name:text(i.name,'Referencia DEMO recuperada'),category:text(i.category,'Sin categoría'),stock:Number.isFinite(Number(i.stock))?Math.max(0,Math.trunc(Number(i.stock))):0}));
    d.settings = {...(object(input.settings)?input.settings:{}),warranty:text(input.settings?.warranty,defaults.settings.warranty),signatureMode:input.settings?.signatureMode==='acceptance'?'acceptance':'drawing'};
    d.documents = d.documents.map(doc=>{
      const o=d.orders.find(o=>o.id===text(doc.orderId));
      const c=person(doc.clientId ?? o?.clientId);
      const confirmed=doc.status==='Confirmado' && validDate(doc.confirmedAt);
      return {...doc,orderId:text(doc.orderId),clientId:text(doc.clientId ?? o?.clientId),customer:{...(object(doc.customer)?doc.customer:{}),name:text(doc.customer?.name,c?.name || 'Cliente DEMO pendiente de identificación'),rut:text(doc.customer?.rut,c?.rut || '')},product:text(doc.product,o?.product || 'Producto pendiente de descripción'),status:confirmed?'Confirmado':'Borrador',created:validDate(doc.created)?doc.created:stamp(),confirmedAt:confirmed?doc.confirmedAt:null,warranty:text(doc.warranty,defaults.settings.warranty),notes:text(doc.notes),mode:doc.mode==='acceptance'?'acceptance':'drawing',signature:typeof doc.signature==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(doc.signature)?doc.signature:''};
    });
    return d;
  }
  function read(seed) {
    try {
      lastRaw = localStorage.getItem(KEY);
      if (lastRaw === null) { const d=seed();localStorage.setItem(KEY,JSON.stringify(d));writable=true;return d; }
      let parsed;
      try { parsed=JSON.parse(lastRaw); } catch { throw new Error('El JSON guardado está incompleto o dañado.'); }
      const d=normalize(parsed,seed);
      if(JSON.stringify(d)!==JSON.stringify(parsed)) {
        const backup=preserve(lastRaw);
        localStorage.setItem(KEY,JSON.stringify(d));
        tell('Se adaptaron datos anteriores sin borrar el original. Copia recuperable: '+backup+'.');
      }
      writable=true;
      return d;
    } catch (error) {
      writable=false;
      tell(error.message+' Los datos originales permanecen intactos. Se muestra un escenario temporal de solo lectura; las operaciones no se guardarán. Puedes descargar el original para recuperarlo.');
      return seed();
    }
  }
  function write(d) {
    if(!writable) throw new Error('El escenario temporal es de solo lectura. No se guardó la operación; conserva o descarga tus datos originales para recuperarlos.');
    localStorage.setItem(KEY,JSON.stringify(d));
  }
  function notify() {
    if(!pending.length)return;
    const el=document.getElementById('storage-alert');if(!el)return;
    el.hidden=false;el.replaceChildren();
    const p=document.createElement('p');p.textContent=pending.join(' ');el.append(p);
    const b=document.createElement('button');b.type='button';b.className='button compact';b.textContent='Descargar respaldo de datos originales';
    b.addEventListener('click',()=>{
      try {
        const keys=Object.keys(localStorage).filter(k=>k.startsWith(KEY+'.respaldo.'));
        const saved=Object.fromEntries(keys.map(k=>[k,localStorage.getItem(k)]));
        const blob=new Blob([JSON.stringify({original:lastRaw,respaldos:saved},null,2)],{type:'application/json'});
        const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='amaru_datos_originales.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      } catch(error) { p.textContent+=' No se pudo descargar: '+error.message; }
    });el.append(b);
  }
  window.AmaruStorage = {read,write,notify};
})();
