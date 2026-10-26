/* Cliente del backend: sesión Django, CSRF y MariaDB. No almacena datos personales en el navegador. */
'use strict';
(() => {
const screen=document.getElementById('screen'),page=document.body.dataset.page;
const params=new URLSearchParams(location.search);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let session,csrf='',signature='',review=null;
const states=['Registrada','En fabricación','Control de calidad','Disponible para retiro'];
const names={clientes:'Clientes',recetas:'Recetas ópticas',cotizaciones:'Cotizaciones',ordenes:'Pedidos y órdenes',recepcion:'Entrega de lentes',documentos:'Documentos',solicitudes:'Agendamientos y contactos',garantias:'Garantías y reparaciones',inventario:'Inventario'};
const endpoints={clientes:'clients',recetas:'prescriptions',cotizaciones:'quotes',ordenes:'orders',recepcion:'orders',documentos:'receipts',solicitudes:'inquiries',garantias:'warranties',inventario:'inventory'};
const has=p=>session.permissions.includes('gestion.'+p);
const btn=(label,action,id='')=>`<button class="button primary" type="button" data-op="${action}" data-id="${esc(id)}">${label}</button>`;
const link=(text,url)=>`<a class="button soft" href="${esc(url)}">${text}</a>`;
const note=t=>`<div class="notice">${esc(t)}</div>`;
const head=(title,description='')=>`<div class="page-heading"><div><div class="eyebrow">Ópticas Amaru · Aplicación académica</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div></div>`;
const panel=(title,body)=>`<section class="panel"><div class="panel-head"><h2>${esc(title)}</h2></div><div class="panel-body">${body}</div></section>`;
const input=(key,label,type='text',value='',attrs='required')=>`<div class="field"><label for="${key}">${label}</label><input id="${key}" name="${key}" type="${type}" value="${esc(value)}" ${attrs}></div>`;
const select=(key,label,options,value='')=>`<div class="field"><label for="${key}">${label}</label><select name="${key}" id="${key}">${options.map(o=>{const [v,t]=Array.isArray(o)?o:[o,o];return `<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(t)}</option>`;}).join('')}</select></div>`;
const area=(key,label,value='')=>`<div class="field wide"><label for="${key}">${label}</label><textarea name="${key}" id="${key}" required maxlength="2000">${esc(value)}</textarea></div>`;
const check=(key,label)=>`<label class="check"><input type="checkbox" name="${key}">${label}</label>`;
const form=(id,body,label='Guardar en el servidor')=>`<form data-form="${id}"><div class="form-grid">${body}</div><div class="form-actions"><button class="button primary" type="submit">${label}</button></div><p class="form-feedback" role="status"></p></form>`;
const badge=s=>`<span class="badge ${s==='Entregada'?'green':'amber'}">${esc(s)}</span>`;
const table=(headers,rows)=>rows.length?`<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map((c,i)=>`<td data-label="${headers[i]}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<div class="empty">Todavía no hay registros. Los datos de la demostración anterior no se importan automáticamente.</div>';
const currency=v=>Number(v).toLocaleString('es-CL',{style:'currency',currency:'CLP',maximumFractionDigits:0});
const date=v=>v?new Date(v.length===10?v+'T12:00:00':v).toLocaleString('es-CL'):'—';
function message(t){const n=document.querySelector('.toast');n.hidden=false;n.textContent=t;setTimeout(()=>n.hidden=true,6000);}
function dialog(title,body){document.getElementById('dialog-title').textContent=title;document.getElementById('dialog-content').innerHTML=body;document.getElementById('app-dialog').showModal();}
function close(){document.getElementById('app-dialog').close();}
async function api(path,options={}){
 const headers={'Accept':'application/json','X-CSRFToken':csrf,...options.headers};
 if(options.body&&!(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
 const r=await fetch('/api/'+path,{...options,headers,credentials:'same-origin'});
 const body=r.headers.get('content-type')?.includes('json')?await r.json():null;
 if(!r.ok)throw new Error(body?Object.entries(body).map(([k,v])=>(k==='detail'?'':k+': ')+(Array.isArray(v)?v.join(' '):typeof v==='object'?JSON.stringify(v):v)).join(' '):'El servidor no pudo completar la operación ('+r.status+').');
 return body;
}
async function list(path){return api(path+(path.includes('?')?'&':'?')+'page='+(params.get('pagina')||1));}
function pages(result){return `<p>${esc(result.count)} registros · Página ${esc(params.get('pagina')||1)}</p><div class="actions">${result.previous?link('← Anterior',location.pathname+'?pagina='+(Number(params.get('pagina')||1)-1)):''}${result.next?link('Siguiente →',location.pathname+'?pagina='+(Number(params.get('pagina')||1)+1)):''}</div>`;}
function loginForm(){screen.innerHTML=head('Acceso a Ópticas Amaru','Inicia sesión con una cuenta creada por el administrador. No se utilizan perfiles ficticios como mecanismo de acceso.')+panel('Autenticación',form('login',input('username','Usuario o correo','text','','required autocomplete="username"')+input('password','Contraseña','password','','required autocomplete="current-password"'),'Iniciar sesión'));}
function error(e){screen.innerHTML=head('No se pudo cargar esta sección')+note(e.message)+btn('Reintentar','reload');}
async function render(){
 try{
 const publicPages=['index','catalogo','formulario_remoto'];
 if(!publicPages.includes(page)&&!session.authenticated){loginForm();return;}
 if(!publicPages.includes(page)&&!['consulta','recepcion','documentos'].includes(page)&&!session.permissions.some(p=>p.startsWith('gestion.view_'))){screen.innerHTML=head('Acceso restringido')+link('Ir a mis pedidos','consulta.html');return;}
 if(page==='index'){screen.innerHTML=head('Una mirada clara. Una atención más cerca.','Conoce la propuesta de Ópticas Amaru y solicita orientación.')+`<section class="hero"><div><h2>Tu atención, conectada.</h2><p>Desde la primera consulta hasta el retiro de tus lentes.</p><div class="actions">${link('Solicitar atención','formulario_remoto.html')}${link('Productos y servicios','catalogo.html')}${link('Mis pedidos','consulta.html')}</div></div><img src="/static/interfaz/img/atencion_optica.svg" alt="Atención óptica" style="max-width:100%;width:400px"></section>`+note('Catálogo académico y horarios de referencia. Las solicitudes quedan registradas para revisión, sin envío automático de correos.');}
 else if(page==='catalogo'){
 const data=await list('products/');screen.innerHTML=head('Productos y servicios','Catálogo académico. La disponibilidad comercial debe confirmarse con la óptica.')+`<div class="cards">${data.results.map(p=>panel(p.name,`<img src="${esc(p.image_url||'/static/interfaz/img/atencion_optica.svg')}" alt="${p.image_url?esc(p.name):'Ilustración académica de atención óptica'}" style="width:100%;max-height:220px;object-fit:contain">`+`<p>${esc(p.description)}</p><p>${esc(p.crystal)} · ${esc(p.color)}</p>`+link('Consultar','formulario_remoto.html?tipo=contacto'))).join('')}</div>`+pages(data)+panel('Servicios','<p>Orientación de lentes, ajustes y revisión de taller, atención en terreno sujeta a evaluación.</p>'+link('Solicitar información','formulario_remoto.html'));
 }
 else if(page==='formulario_remoto')requestForm();
 else if(page==='consulta'){
 const data=await list('orders/');screen.innerHTML=head('Mis pedidos','El servidor limita los registros a tu cuenta autenticada.')+ordersTable(data.results,true)+pages(data);
 }
 else if(page==='dashboard'){
 const results=await Promise.all(['clients/','orders/','receipts/','inquiries/'].map(p=>api(p).catch(()=>null)));
 screen.innerHTML=head('Resumen de atención','Información persistida en la base de datos del servidor.')+`<div class="stats dashboard-stats">${results.map((r,i)=>`<article class="stat"><div>${['Clientes','Órdenes de trabajo','Entregas registradas','Solicitudes de atención'][i]}</div><strong>${r?r.count:'Sin permiso'}</strong></article>`).join('')}</div>`+(results[1]?panel('Pedidos recientes',ordersTable(results[1].results)):note('No tienes acceso a las órdenes.'))+link('Bitácora','/auditoria/');
 }
 else if(page==='detalle_cliente'){
 const c=await api('clients/'+params.get('cliente')+'/');screen.innerHTML=head(c.name,c.rut)+panel('Ficha de cliente',`<p>${esc(c.phone)} · ${esc(c.email)}</p><p>${esc(c.category)} · Contacto posventa: ${c.consent?'Autorizado':'No autorizado'}</p><p>Estado: ${c.active?'Activo':'Inactivo'}</p>`+btn('Editar ficha','client-edit',c.id))+link('Clientes','clientes.html');
 }
 else if(page==='recepcion'&&params.get('pedido'))await delivery();
 else if(endpoints[page])await modulePage();
 else screen.innerHTML=head('Módulo no disponible');
 }catch(e){error(e);}finally{document.documentElement.dataset.amaruReady='true';}
}
function requestForm(){const kind=params.get('tipo')||'agenda';screen.innerHTML=head('Agendar / contactar','No necesitas una cuenta de cliente para dejar tu solicitud.')+form('inquiry',select('kind','Tipo de solicitud',[['agenda','Atención'],['contacto','Contacto'],['lentes','Orientación de lentes']],kind)+input('name','Nombre completo')+input('phone','Teléfono','tel','','required pattern="[+0-9 ()-]{8,30}"')+input('email','Correo','email')+input('service','Tipo de atención','text','Orientación de lentes')+input('day','Fecha solicitada','date','','min="'+new Date().toLocaleDateString('sv-SE')+'"')+select('slot','Horario académico',['09:00','10:00','11:00','15:00','16:00'])+area('reason','Motivo de consulta')+check('contact_authorized','Autorizo el contacto para gestionar esta solicitud.'),'Registrar solicitud')+note('Las fechas son solicitudes pendientes de revisión. No se envían correos ni mensajes automáticamente.');screen.querySelector('form').dataset.key=crypto.randomUUID();}
function ordersTable(rows,own=false){return table(['Orden','Cliente','Producto','Estado','Acción'],rows.map(o=>[esc(o.folio),esc(o.client_name),esc(Object.values(o.characteristics).join(' · ')),badge(o.status),`<div class="actions">${o.status==='Disponible para retiro'?link('Revisar retiro','recepcion.html?pedido='+o.id):''}${!own&&o.status!=='Entregada'&&has('change_order')?btn('Actualizar','order-state',o.id):''}${o.status==='Entregada'?link('Documentos','documentos.html'):''}</div>`]));}
async function modulePage(){
 const endpoint=endpoints[page],q=page==='clientes'&&params.get('q')?'?q='+encodeURIComponent(params.get('q')):'';
 const data=await list(endpoint+'/'+q);let body='',action='';
 if(page==='clientes'){
 action=has('add_client')?btn('Registrar cliente','client-new'):'';
 body=form('search',input('q','Buscar por RUT o nombre','search',params.get('q')||'',''),'Buscar')+table(['Cliente','RUT','Contacto','Estado','Acción'],data.results.map(c=>[esc(c.name),esc(c.rut),esc(c.email)+'<br>'+esc(c.phone),c.active?'Activo':'Inactivo',link('Ver ficha','detalle_cliente.html?cliente='+c.id)]));
 }else if(page==='recetas'){
 action=has('add_prescription')?btn('Nueva receta','recipe-new'):'';
 body=table(['ID','Cliente','Emisión','Vigencia','Archivo'],data.results.map(r=>[esc(r.id),esc(r.client),esc(r.issued_on),badge(r.status),btn('Abrir autorizado','file','prescriptions/'+r.id+'/file/')]));
 }else if(page==='cotizaciones'){
 action=has('add_quote')?btn('Nueva cotización','quote-new'):'';
 body=table(['Folio','Cliente','Monto','Estado','Acción'],data.results.map(q=>[esc(q.folio),esc(q.client),currency(q.amount),q.approved?'Aprobada':'Borrador',has('change_quote')?`<div class="actions">${btn('Editar / aprobar','quote-edit',q.id)}${q.approved&&has('add_order')?btn('Generar OT','convert',q.id):''}</div>`:'']));
 }else if(page==='ordenes'||page==='recepcion')body=ordersTable(data.results);
 else if(page==='documentos')body=table(['Documento','Orden','Cliente','Fecha','Acción'],data.results.map(d=>[esc(d.id),esc(d.order_folio),esc(d.client_name),date(d.created_at),btn('Ver documento / PDF','file','receipts/'+d.id+'/pdf/')]));
 else if(page==='solicitudes')body=table(['Solicitante','Contacto','Tipo / horario','Motivo','Estado','Acción'],data.results.map(r=>[esc(r.name),esc(r.phone)+'<br>'+esc(r.email),esc(r.kind)+'<br>'+esc(r.day||'')+' '+esc(r.slot||''),esc(r.reason),badge(r.status),has('change_inquiry')?btn('Revisar','inquiry-state',r.id):'']));
 else if(page==='garantias'){
 action=has('add_warranty')?btn('Registrar solicitud','warranty-new'):'';
 body=table(['Folio','Orden','Tipo','Motivo','Estado','Acción'],data.results.map(w=>[esc(w.folio),esc(w.order),esc(w.kind),esc(w.reason),badge(w.status),has('change_warranty')?btn('Revisar','warranty-edit',w.id):'']));
 }else if(page==='inventario')body=table(['Artículo','Categoría','Cantidad','Acción'],data.results.map(i=>[esc(i.name),esc(i.category),esc(i.quantity),has('change_inventory')?btn('Actualizar cantidad','inventory-edit',i.id):'']));
 screen.innerHTML=head(names[page],'Registros del servidor. Se aplican permisos en cada operación.')+action+panel(names[page],body)+pages(data);
 if(page==='documentos'&&has('change_siteconfiguration'))screen.innerHTML+=btn('Configurar garantía','settings');
}
async function clientForm(id){
 const c=id?await api('clients/'+id+'/'):{};const agreements=await api('agreements/');
 dialog(id?'Editar cliente':'Registrar cliente',form('client',`<input type="hidden" name="id" value="${esc(id||'')}">`+input('rut','RUT','text',c.rut)+input('name','Nombre completo','text',c.name)+input('phone','Teléfono','tel',c.phone)+input('email','Correo','email',c.email,'')+select('category','Modalidad',[['particular','Particular'],['convenio','Convenio']],c.category)+select('agreement','Convenio',[['','No corresponde'],...agreements.results.map(a=>[a.id,a.name])],c.agreement)+check('consent','Autoriza comunicaciones de posventa')+select('active','Estado',[['true','Activo'],['false','Inactivo']],String(c.active??true))));
 document.querySelector('[name=consent]').checked=!!c.consent;
}
async function recipeForm(){
 const clients=await api('clients/');dialog('Receta óptica',form('recipe',select('client','Cliente',clients.results.map(c=>[c.id,c.name+' · '+c.rut]))+input('issued_on','Fecha de emisión','date','','required')+input('file','Archivo privado PDF, JPG o PNG','file','','required accept=".pdf,.png,.jpg,.jpeg"')+input('physical_reference','Referencia física','text','',''))+note('Se valida contenido y tamaño máximo de 10 MB en el servidor. El archivo no se guarda en localStorage.'));
}
async function quoteForm(id){
 const [clients,recipes,agreements,q]=await Promise.all([api('clients/'),api('prescriptions/'),api('agreements/'),id?api('quotes/'+id+'/'):Promise.resolve({characteristics:{}})]);
 dialog('Cotización',form('quote',`<input type="hidden" name="id" value="${esc(id||'')}">`+select('client','Cliente',clients.results.map(c=>[c.id,c.name]),q.client)+select('prescription','Receta',[['','Sin receta'],...recipes.results.map(r=>[r.id,'Cliente '+r.client+' · '+r.issued_on+' · '+r.status])],q.prescription)+select('category','Modalidad',[['particular','Particular'],['convenio','Convenio']],q.category)+select('agreement','Convenio',[['','No corresponde'],...agreements.results.map(a=>[a.id,a.name])],q.agreement)+select('product_type','Tipo de lentes',[['particular','Particular'],['seguridad','Seguridad']],q.product_type)+input('frame','Armazón / modelo','text',q.characteristics.frame||q.characteristics.security_model||'')+input('crystal','Cristal / color','text',q.characteristics.crystal||q.characteristics.security_color||'')+select('focus','Enfoque',['monofocal','multifocal'],q.characteristics.focus)+input('amount','Monto CLP','number',q.amount||0,'required min="0" step="1"')+input('notes','Observaciones','text',q.notes||'','')+check('approved','Cotización aprobada por el cliente')));
 document.querySelector('[name=approved]').checked=!!q.approved;
}
async function warrantyForm(id){
 const orders=await api('orders/');const w=id?await api('warranties/'+id+'/'):{};
 dialog('Garantía y reparación',form('warranty',`<input type="hidden" name="id" value="${esc(id||'')}">`+select('order','Orden de trabajo',orders.results.map(o=>[o.id,o.folio+' · '+o.client_name]),w.order)+select('kind','Tipo',['Garantía','Reparación','Cambio de armazón'],w.kind)+input('reason','Motivo','text',w.reason)+area('description','Descripción de la falla',w.description)+select('status','Estado',['En revisión taller','Aprobada','Rechazada','Lista para entrega'],w.status)+input('justification','Resolución / justificación','text',w.justification,'')+input('damaged_frame_destination','Destino del armazón dañado','text',w.damaged_frame_destination,'')));
}
async function delivery(){
 review=await api('orders/'+params.get('pedido')+'/preview/');
 screen.innerHTML=head('Documento de entrega y conformidad','Revise los datos antes de aceptar. Firma electrónica simple; no avanzada.')+panel('Datos de entrega',`<dl><dt>Cliente</dt><dd>${esc(review.client)}</dd><dt>RUT</dt><dd>${esc(review.rut)}</dd><dt>Orden</dt><dd>${esc(review.order)}</dd><dt>Producto</dt><dd>${esc(Object.values(review.product).join(' · '))}</dd><dt>Estado</dt><dd>${esc(review.status)}</dd></dl><h3>Condiciones de garantía</h3><p style="white-space:pre-wrap">${esc(review.terms)}</p>`);
 if(review.status!=='Disponible para retiro'){screen.innerHTML+=note('Esta orden no está disponible para retiro.');return;}
 screen.innerHTML+=panel('Confirmación de recepción',form('delivery',input('observations','Observaciones','text','','')+'<div class="wide"><label for="signature">Firma electrónica simple</label><canvas id="signature" class="signature-pad" style="width:100%;height:180px;touch-action:none" aria-label="Firma de recepción"></canvas>'+btn('Limpiar firma','clear-signature')+'</div>'+check('accepted','Revisé los datos y condiciones y confirmo la recepción de los lentes.'),'Confirmar entrega'));
 setupSignature();
}
function setupSignature(){signature='';const canvas=document.getElementById('signature'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect();canvas.width=Math.max(300,rect.width);canvas.height=180;ctx.lineWidth=2.5;ctx.lineCap='round';let drawing=false,points=0;canvas.onpointerdown=e=>{drawing=true;canvas.setPointerCapture(e.pointerId);ctx.beginPath();ctx.moveTo(e.offsetX,e.offsetY);};canvas.onpointermove=e=>{if(!drawing)return;ctx.lineTo(e.offsetX,e.offsetY);ctx.stroke();points++;};canvas.onpointerup=()=>{drawing=false;if(points>3)signature=canvas.toDataURL('image/png');};canvas.clear=()=>{ctx.clearRect(0,0,canvas.width,canvas.height);signature='';points=0;};}
async function openFile(path){const win=window.open('about:blank','_blank');try{const r=await fetch('/api/'+path,{credentials:'same-origin'});if(!r.ok)throw new Error('No se pudo acceder al documento autorizado.');if(r.headers.get('content-type')?.includes('json')){const data=await r.json();if(win)win.location=data.url;else location.href=data.url;}else{const url=URL.createObjectURL(await r.blob());if(win)win.location=url;else location.href=url;setTimeout(()=>URL.revokeObjectURL(url),60000);}}catch(e){win?.close();throw e;}}
document.addEventListener('submit',async e=>{
 const f=e.target;if(!f.dataset.form)return;e.preventDefault();if(!f.reportValidity())return;
 const data=Object.fromEntries(new FormData(f)),submit=f.querySelector('[type=submit]');submit.disabled=true;
 try{switch(f.dataset.form){
 case 'login':{const r=await api('login/',{method:'POST',body:data});csrf=r.csrf;location.reload();return;}
 case 'search':location.href='clientes.html?q='+encodeURIComponent(data.q);return;
 case 'inquiry':data.contact_authorized=!!data.contact_authorized;data.idempotency_key=f.dataset.key;data.day=data.day||null;data.slot=data.slot||null;{const r=await api('inquiries/',{method:'POST',body:data});screen.innerHTML=head('Solicitud registrada')+note(r.detail)+`<p>Referencia: ${esc(r.reference)}</p>`+link('Volver al inicio','index.html');return;}
 case 'client':{const id=data.id;delete data.id;data.consent=!!data.consent;data.active=data.active==='true';data.agreement=data.agreement||null;await api('clients/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});break;}
 case 'recipe':await api('prescriptions/',{method:'POST',body:new FormData(f)});break;
 case 'quote':{const id=data.id;delete data.id;data.approved=!!data.approved;data.agreement=data.agreement||null;data.prescription=data.prescription||null;data.characteristics=data.product_type==='particular'?{frame:data.frame,crystal:data.crystal,focus:data.focus}:{security_model:data.frame,security_color:data.crystal,focus:data.focus};delete data.frame;delete data.crystal;delete data.focus;await api('quotes/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});break;}
 case 'warranty':{const id=data.id;delete data.id;await api('warranties/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});break;}
 case 'state':await api(data.endpoint,{method:data.endpoint.startsWith('orders/')?'POST':'PATCH',body:{status:data.status}});break;
 case 'inventory':await api('inventory/'+data.id+'/',{method:'PATCH',body:{quantity:Number(data.quantity)}});break;
 case 'settings':await api('configuration/',{method:'PATCH',body:data});break;
 case 'delivery':if(!data.accepted||!signature)throw new Error('Debe aceptar la conformidad y dibujar la firma.');{const r=await api('orders/'+review.order+'/deliver/',{method:'POST',body:{accepted:true,signature,review_token:review.review_token,observations:data.observations}});screen.innerHTML=head('Entrega registrada')+note('La orden está entregada. El documento y su referencia quedaron guardados en el servidor.')+btn('Ver documento / PDF','file','receipts/'+r.id+'/pdf/')+link('Documentos','documentos.html');return;}
 }close();await render();message('Operación guardada en el servidor.');
 }catch(err){f.querySelector('.form-feedback').textContent=err.message;}finally{submit.disabled=false;}
});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-op]');if(!b)return;const id=b.dataset.id;try{switch(b.dataset.op){
 case 'reload':location.reload();break;
 case 'logout':await api('logout/',{method:'POST',body:{}});location.href='index.html';break;
 case 'client-new':await clientForm();break;
 case 'client-edit':await clientForm(id);break;
 case 'recipe-new':await recipeForm();break;
 case 'quote-new':await quoteForm();break;
 case 'quote-edit':await quoteForm(id);break;
 case 'convert':await api('quotes/'+id+'/convert/',{method:'POST',body:{}});await render();message('OT registrada.');break;
 case 'order-state':dialog('Actualizar pedido',form('state',`<input name="endpoint" type="hidden" value="orders/${esc(id)}/state/">`+select('status','Estado',states)));break;
 case 'inquiry-state':dialog('Revisar solicitud',form('state',`<input name="endpoint" type="hidden" value="inquiries/${esc(id)}/">`+select('status','Estado',['Nueva','En revisión','Contactada','Cerrada','Cancelada'])));break;
 case 'warranty-new':await warrantyForm();break;
 case 'warranty-edit':await warrantyForm(id);break;
 case 'inventory-edit':{const i=await api('inventory/'+id+'/');dialog('Actualizar cantidad',form('inventory',`<input name="id" type="hidden" value="${esc(id)}">`+input('quantity','Cantidad','number',i.quantity,'required min="0" step="1"')));break;}
 case 'clear-signature':document.getElementById('signature').clear();break;
 case 'file':await openFile(id);break;
 case 'settings':{const c=await api('configuration/');dialog('Condiciones configurables',form('settings',area('warranty_terms','Condiciones de garantía',c.warranty_terms)));break;}
 }}catch(err){message(err.message);}});
document.querySelector('[data-close-dialog]')?.addEventListener('click',close);
document.querySelector('[data-menu]')?.addEventListener('click',e=>{const open=document.querySelector('.sidebar').classList.toggle('open');e.currentTarget.setAttribute('aria-expanded',String(open));});
document.querySelector('[data-public-menu]')?.addEventListener('click',e=>{const open=document.getElementById('public-nav').classList.toggle('open');e.currentTarget.setAttribute('aria-expanded',String(open));});
(async()=>{try{
 session=await api('session/');csrf=session.csrf;
 const navigation={clientes:'view_client',recetas:'view_prescription',cotizaciones:'view_quote',ordenes:'view_order',recepcion:'add_receipt',documentos:'view_receipt',solicitudes:'view_inquiry',garantias:'view_warranty',inventario:'view_inventory'};
 document.querySelectorAll('.sidebar a[href]').forEach(a=>{const route=a.getAttribute('href').split('.')[0];if(navigation[route]&&!has(navigation[route]))a.hidden=true;});
 if(session.authenticated&&!has('view_order')&&['recepcion','documentos'].includes(page)){
  const side=document.querySelector('.sidebar');if(side)side.hidden=true;
  const app=document.querySelector('.app');if(app)app.style.display='block';
  const topbar=document.querySelector('.topbar');if(topbar)topbar.innerHTML=link('Mis pedidos','consulta.html')+link('Mis documentos','documentos.html');
 }
 const top=document.querySelector('.topbar')||document.querySelector('.public-header');
 if(session.authenticated)top?.insertAdjacentHTML('beforeend',btn('Cerrar sesión','logout'));
 document.querySelectorAll('.demo-tag').forEach(n=>n.textContent='DATOS DEL SERVIDOR');await render();
}catch(e){error(e);}})();
})();
