/* Cliente del backend: sesión Django, CSRF y MariaDB. No almacena datos personales en el navegador. */
'use strict';
document.documentElement.dataset.amaruStarting='true';
(() => {
const screen=document.getElementById('screen'),page=document.body.dataset.page;
const params=new URLSearchParams(location.search);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let session,csrf='',signature='',review=null,qrRefresh=null,refreshAppointmentCalendar;
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
function close(){clearInterval(qrRefresh);qrRefresh=null;document.getElementById('app-dialog').close();}
async function api(path,options={}){
 const headers={'Accept':'application/json','X-CSRFToken':csrf,...options.headers};
 if(options.body&&!(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
 const r=await fetch('/api/'+path,{...options,headers,credentials:'same-origin'});
 const body=r.headers.get('content-type')?.includes('json')?await r.json():null;
 if(!r.ok){const failure=new Error(body?Object.entries(body).map(([k,v])=>(k==='detail'?'':k+': ')+(Array.isArray(v)?v.join(' '):typeof v==='object'?JSON.stringify(v):v)).join(' '):'El servidor no pudo completar la operación ('+r.status+').');failure.status=r.status;throw failure;}
 return body;
}
async function list(path){return api(path+(path.includes('?')?'&':'?')+'page='+(params.get('pagina')||1));}
function paginationURL(number){const query=new URLSearchParams(params);query.set('pagina',number);return location.pathname+'?'+query;}
function pages(result){return `<p>${esc(result.count)} registros · Página ${esc(params.get('pagina')||1)}</p><div class="actions">${result.previous?link('← Anterior',paginationURL(Number(params.get('pagina')||1)-1)):''}${result.next?link('Siguiente →',paginationURL(Number(params.get('pagina')||1)+1)):''}</div>`;}

const registrationLink='<p class="signup-link"><a href="/app/registro.html">¿No tienes una cuenta? Regístrate aquí.</a></p>';
async function renderRegistration(){
 if(session.authenticated){screen.innerHTML=head('Tu sesión está activa')+link('Ir a mis pedidos','consulta.html');return;}
 const setup=await api('register/');
 screen.innerHTML=head('Crear cuenta','Regístrate para solicitar cotizaciones y consultar tus pedidos desde tu cuenta.')+
 panel('Tus datos',form('register',
  input('name','Nombre completo','text','','required maxlength="180" autocomplete="name"')+
  input('rut','RUT','text','','required maxlength="18" placeholder="12.345.678-5"')+
  input('email','Correo electrónico','email','','required maxlength="150" autocomplete="email"')+
  input('phone','Número de teléfono','tel','','required maxlength="30" autocomplete="tel" placeholder="+56 9 …"')+
  input('password','Contraseña','password','','required maxlength="128" autocomplete="new-password" aria-describedby="signup-password-help"')+
  input('password_confirmation','Confirmar contraseña','password','','required maxlength="128" autocomplete="new-password"')+
  '<p id="signup-password-help" class="wide">Elige una contraseña difícil de adivinar, distinta a tu nombre y correo.</p>'+
  '<label class="check wide"><input type="checkbox" name="privacy" required><span>Acepto la <a href="privacidad.html" target="_blank" rel="noopener">política de privacidad</a> (se abre en otra pestaña).</span></label>'+
  '<label class="check wide"><input type="checkbox" name="promotions">Autorizo recibir promociones (opcional).</label>'+
  '<div class="signup-trap" aria-hidden="true"><label for="signup-website">Sitio web (dejar vacío)</label><input id="signup-website" name="website" tabindex="-1" autocomplete="off"></div>'+
  `<input type="hidden" name="challenge" value="${esc(setup.challenge)}"><input type="hidden" name="privacy_version" value="${esc(setup.privacy_version)}">`,
  'Crear mi cuenta')+link('Volver a Iniciar sesión','consulta.html'))+
 note('Una persona autorizada verificará tu correo y tu identidad antes de activar la cuenta.');
}
function renderPrivacy(){
 screen.innerHTML=head('Política de privacidad del registro','Versión académica · academica-1')+panel('Uso de los datos',
  '<p>Ópticas Amaru usa tu nombre, RUT y datos de contacto para revisar tu solicitud, verificar tu identidad y administrar tu cuenta. Una ficha existente solo puede vincularse después de la verificación.</p>'+
  '<p>Las solicitudes de registro son privadas. La contraseña se guarda mediante un hash y no puede consultarse desde el sistema. La autorización de promociones es opcional y no condiciona la creación de la cuenta.</p>'+
  '<p>Para revisar, corregir o retirar los datos de la cuenta, solicita ayuda al personal autorizado de la óptica. Esta es una demostración académica: usa solo datos ficticios y no ingreses antecedentes clínicos reales.</p>'+
  link('Volver al registro','registro.html'));
}
async function renderMyAccount(){
 const data=await api('my-account/');
 const rows=data.inquiries.map(r=>[esc(r.reference),esc(r.kind),esc(date(r.created_at)),badge(r.status)]);
 return panel('Mis solicitudes',rows.length?table(['Referencia','Tipo','Fecha','Estado'],rows):note('Aún no tienes solicitudes enviadas desde esta cuenta.'))+
  panel('Mi convenio',note(data.agreement?'Convenio vigente y validado: '+data.agreement:'No tienes un convenio vigente y validado.')+
  (data.memberships||[]).map(row=>`<p>${esc(row.organization)} · ${esc(unionStates[row.state])} · ${row.available?'Vigente':'Sin beneficios vigentes'}</p>`).join('')+
  (session.mining?link('Catálogo de lentes mineros','catalogo.html?scope=mining'):''))+
 panel('Mis cotizaciones',table(['Folio','Monto','Estado'],(data.quotes||[]).map(q=>[esc(q.folio),currency(q.amount),q.approved?'Aprobada':'En revisión'])))+
  panel('Mis recetas',form('account-recipe',input('issued_on','Fecha de emisión','date')+
   input('file','Receta privada (JPG, PNG o PDF)','file','','required accept=".jpg,.jpeg,.png,.pdf"'),'Guardar receta privada'));
}

function loginForm(){screen.innerHTML=head('Acceso a Ópticas Amaru','Ingresa con tu usuario o con el correo de tu cuenta activada.')+panel('Autenticación',form('login',input('username','Usuario o correo','text','','required autocomplete="username"')+input('password','Contraseña','password','','required autocomplete="current-password"'),'Iniciar sesión')+registrationLink);}
function error(e){screen.innerHTML=head('No se pudo cargar esta sección')+note(e.message)+btn('Reintentar','reload');}

const unionStates={pending:'Pendiente',active:'Activo',inactive:'Inactivo',suspended:'Suspendido'};
let pickupReview=null;
const unionMenu=[
 ['resumen','Resumen'],['convenio','Mi convenio'],['firma','Firmar convenio'],
 ['trabajadores','Mis trabajadores'],['crear','Crear trabajador'],
 ['accesos','Administrar accesos'],['cuenta','Configuración de cuenta'],
];
let unionAdminRows=[];
const hidden=(name,value)=>`<input type="hidden" name="${name}" value="${esc(value)}">`;
const textDate=value=>value?esc(value):'—';
const workerActions=(row,canManage)=>
 (row.state!=='inactive'?btn('Desactivar','worker-disable',row.id):'')+
 (canManage&&row.state!=='active'?btn('Reemitir invitación','worker-reissue',row.id):'')+
 (row.accepted_at&&!row.recovery_requested_at?btn('Solicitar recuperación','worker-recovery',row.id):'')+
 (canManage&&row.state!=='inactive'?btn('Editar datos','worker-edit',row.id):'');

function unionDocument(data){
 const d=data.document;
 if(!d)return note('Aún no hay un documento asociado.');
 return `<p>Versión ${esc(d.version)} · ${d.signed_at?'Firmado por '+esc(d.signer)+' el '+esc(date(d.signed_at)):'Pendiente de firma'}</p>
 <p class="qr-url">SHA-256: ${esc(d.sha256)}</p>`+
 link('Abrir PDF privado','/api/union-documents/'+d.id+'/');
}
function invitationDialog(invitation){
 const url=new URL(invitation.url,location.origin).href;
 dialog('Invitación individual',
  note('Entrégala directamente a su titular por un canal seguro. El enlace vence el '+date(invitation.expires_at)+'.')+
  `<p class="qr-url">${esc(url)}</p>`+btn('Copiar enlace','copy-invitation',url));
}
function renderInvitation(){
 const token=new URLSearchParams(location.hash.slice(1)).get('token')||'';
 if(!/^[A-Za-z0-9_-]{43}$/.test(token)){
  screen.innerHTML=head('Invitación')+note('Abre el enlace individual que te entregó tu organización.');
  return;
 }
 screen.innerHTML=head('Aceptar invitación','Usa este enlace para activar o recuperar tu acceso.')+
 panel('Acceso a Ópticas Amaru',form('claim-invitation',
  input('password','Nueva contraseña','password','','maxlength="128" autocomplete="new-password"')+
  input('password_confirmation','Repite la nueva contraseña','password','','maxlength="128" autocomplete="new-password"')+
  check('accepted','Acepto esta invitación y solicito el acceso o la vinculación.'),'Aceptar invitación')+
  note('Si ya tienes una cuenta personal y estás aceptando una afiliación, inicia sesión abajo y deja en blanco la nueva contraseña.'))+
 (!session.authenticated?panel('Ya tengo cuenta',form('login',
  input('username','Correo o usuario','text','','required autocomplete="username"')+
  input('current_password','Contraseña actual','password','','required autocomplete="current-password"'),'Iniciar sesión')):'');
}
async function renderUnion(){
 if(!session.union){screen.innerHTML=head('Panel del Sindicato')+note('Ingresa con la cuenta institucional del sindicato.');return;}
 const data=await api('union/portal/');
 const u=data.union;
 const selected=unionMenu.find(([key])=>key===params.get('vista'))?.[0]||'resumen';
 const nav=unionMenu.map(([key,label])=>`<a class="button soft" ${key===selected?'aria-current="page"':''} href="sindicato.html?vista=${key}">${label}</a>`).join('');
 screen.innerHTML=head('Panel del Sindicato',u.name)+`<nav class="actions union-nav" aria-label="Panel del Sindicato">${nav}</nav>`;
 let content;
 if(selected==='convenio'){
  content=panel('Mi convenio',`<p>${esc(u.identifier)} · ${esc(unionStates[u.state])}</p>
   <p>Vigencia: ${textDate(u.starts_on)} a ${textDate(u.ends_on)}</p><p>${esc(u.institutional_details)}</p>`+unionDocument(u));
 }else if(selected==='firma'){
  const doc=u.document;
  content=panel('Firmar convenio',unionDocument(u)+(doc&&!doc.signed_at&&u.state!=='suspended'?
   form('union-sign',hidden('document',doc.id)+hidden('sha256',doc.sha256)+check('accepted',esc(data.acceptance)),'Firmar convenio'):''));
 }else if(selected==='trabajadores'||selected==='accesos'){
  content=panel(selected==='accesos'?'Administrar accesos':'Mis trabajadores',
   table(['Trabajador','RUT','Contacto','Calidad','Estado','Acciones'],data.workers.map(r=>[
    esc(r.name),esc(r.rut),esc(r.email)+'<br>'+esc(r.phone),esc(r.role),
    badge(unionStates[r.state])+(r.recovery_requested_at?'<p>Recuperación solicitada</p>':''),
    `<div class="actions union-nav">${workerActions(r,u.available)}</div>`])));
 }else if(selected==='crear'){
  content=panel('Crear trabajador',u.available?note('Sindicato asignado: '+u.name)+
   form('union-worker',input('name','Nombre completo','text','','required maxlength="180"')+
    input('rut','RUT','text','','required maxlength="18"')+input('email','Correo','email','','required maxlength="150"')+
    input('phone','Teléfono','tel','','required maxlength="30"')+
    select('role','Calidad',u.allow_dependents?[['titular','Titular'],['carga','Carga familiar']]:[['titular','Titular']]),
    'Crear e invitar'):note('La creación de trabajadores requiere un convenio activo y vigente.'));
 }else if(selected==='cuenta'){
  content=panel('Configuración de cuenta',note(u.contact_name+' · '+u.contact_email)+
   form('union-password',input('current','Contraseña actual','password','','required maxlength="128" autocomplete="current-password"')+
    input('password','Nueva contraseña','password','','required maxlength="128" autocomplete="new-password"'),'Actualizar contraseña'));
 }else{
  content=panel('Resumen',`<p>Convenio: ${esc(unionStates[u.state])} · ${u.available?'Vigente':'Sin beneficios vigentes'}</p>
   <p>Vigencia: ${textDate(u.starts_on)} a ${textDate(u.ends_on)}</p>`+unionDocument(u))+
   `<div class="stats">${[['Activos',data.counts.active],['Inactivos',data.counts.inactive],['Afiliaciones pendientes',data.counts.pending],
    ['Recuperaciones pendientes',data.workers.filter(row=>row.recovery_requested_at).length]].map(([label,n])=>
    `<article class="stat"><div>${label}</div><strong>${esc(n)}</strong></article>`).join('')}</div>`;
 }
 screen.insertAdjacentHTML('beforeend',content);
}
async function renderUnionAdmin(){
 if(!has('change_union')){screen.innerHTML=head('Gestión de sindicatos')+note('Se requiere autorización administrativa.');return;}
 const organization=params.get('union');
 if(organization&&/^\d+$/.test(organization)){
  const data=await api('unions/'+organization+'/workers/');
  screen.innerHTML=head('Trabajadores del sindicato',data.union.name)+link('Volver a sindicatos','sindicatos.html')+
   table(['Trabajador','RUT','Calidad','Estado'],data.workers.map(row=>[esc(row.name),esc(row.rut),esc(row.role),badge(unionStates[row.state])]));
  return;
 }
 const [unions,requests]=await Promise.all([api('unions/'),api('union/reviews/')]);
 unionAdminRows=unions;
 screen.innerHTML=head('Gestión de sindicatos','Registra, revisa y activa los convenios de cada organización.')+
 btn('Registrar sindicato','union-new')+
 unions.map(u=>panel(u.name,`<p>${esc(u.identifier)} · ${esc(unionStates[u.state])} · ${textDate(u.starts_on)} a ${textDate(u.ends_on)}</p>`+
  unionDocument(u)+`<div class="actions union-nav">`+link('Ver trabajadores','sindicatos.html?union='+u.id)+btn('Editar datos institucionales','union-edit',u.id)+btn('Asociar PDF','union-upload',u.id)+btn('Reemitir invitación del representante','union-invite',u.id)+
  (u.state==='active'?btn('Suspender sindicato','union-suspend',u.id):u.document?.signed_at?btn('Activar sindicato','union-activate',u.id):'')+'</div>')).join('')+
 panel('Vinculaciones y recuperaciones pendientes',table(['Organización','Trabajador','RUT','Acciones'],requests.map(r=>[
  esc(r.organization),esc(r.name),esc(r.rut),(r.state==='pending'&&r.accepted_at?btn('Verificar y vincular','worker-review',r.id):'')+
  (r.recovery_requested_at?btn('Preparar recuperación','worker-reset',r.id):'')])));
}
function showUnionForm(){
 dialog('Registrar sindicato',form('union-new',input('name','Nombre del sindicato')+
  input('identifier','Identificador único','text','','required maxlength="40" pattern="[A-Za-z0-9_-]+"')+
  area('institutional_details','Datos institucionales')+input('contact_name','Nombre del representante')+
  input('contact_email','Correo institucional','email')+input('starts_on','Inicio de vigencia','date')+
  input('ends_on','Término de vigencia','date')+check('allow_dependents','El convenio admite cargas familiares.'),'Registrar e invitar'));
}
function showPickupValidation(){
 if(!has('add_receipt')||!has('view_order')){screen.innerHTML=head('Validar retiro de lentes')+note('Se requiere acceso de vendedor.');return;}
 screen.innerHTML=head('Validar retiro de lentes','Ingresa el código presentado y verifica la identidad o autorización de quien retira.')+
 panel('Código de retiro',form('pickup-validate',input('code','Código de 24 caracteres','text','','required maxlength="24" autocomplete="off" autocapitalize="characters"')+
 '','Buscar orden'));
}

async function render(){
 try{
 const publicPages=['index','catalogo','formulario_remoto','producto','carrito','portal_convenios','registro','privacidad','invitacion'];
 if(!publicPages.includes(page)&&!session.authenticated){loginForm();return;}
 if(!publicPages.includes(page)&&!['consulta','recepcion','documentos','representante','sindicato','sindicatos','retiro'].includes(page)&&!session.permissions.some(p=>p.startsWith('gestion.view_'))){screen.innerHTML=head('Acceso restringido')+link('Ir a mis pedidos','consulta.html');return;}
 if(page==='index'){screen.innerHTML=head('Una mirada clara. Una atención más cerca.','Conoce la propuesta de Ópticas Amaru y solicita orientación.')+`<section class="hero"><div><h2>Tu atención, conectada.</h2><p>Desde la primera consulta hasta el retiro de tus lentes.</p><div class="actions">${link('Solicitar atención','formulario_remoto.html')}${link('Productos y servicios','catalogo.html')}${link('Mis pedidos','consulta.html')}</div></div><img src="/static/interfaz/img/atencion_optica.svg" alt="Atención óptica" style="max-width:100%;width:400px"></section>`+note('Catálogo académico y horarios de referencia. Las solicitudes quedan registradas para revisión, sin envío automático de correos.');}
 else if(page==='registro')await renderRegistration();
 else if(page==='privacidad')renderPrivacy();
 else if(page==='catalogo')await renderCatalog();
 else if(page==='producto')await renderProduct();
 else if(page==='carrito')await renderCart();
 else if(page==='portal_convenios')renderMembershipPortal();
 else if(page==='representante')await (session.union?renderUnion():renderRepresentative());
 else if(page==='sindicato')await renderUnion();
 else if(page==='sindicatos')await renderUnionAdmin();
 else if(page==='invitacion')renderInvitation();
 else if(page==='retiro')showPickupValidation();
 else if(page==='convenios')await renderAgreements();
 else if(page==='formulario_remoto')await requestForm();
 else if(page==='consulta'){
 const data=await list('orders/');screen.innerHTML=head('Mis pedidos','El servidor limita los registros a tu cuenta autenticada.')+ordersTable(data.results,true)+pages(data);
 if(session.client_id&&!has('view_order')){
  try{screen.insertAdjacentHTML('beforeend',await renderMyAccount());}
  catch(e){screen.insertAdjacentHTML('beforeend',note(e.message));}
 }
 }
 else if(page==='dashboard'){
 const results=await Promise.all(['clients/','orders/','receipts/','inquiries/'].map(p=>api(p).catch(()=>null)));
 screen.innerHTML=head('Resumen de atención','Información persistida en la base de datos del servidor.')+`<div class="stats dashboard-stats">${results.map((r,i)=>`<article class="stat"><div>${['Clientes','Órdenes de trabajo','Entregas registradas','Solicitudes de atención'][i]}</div><strong>${r?r.count:'Sin permiso'}</strong></article>`).join('')}</div>`+(results[1]?panel('Pedidos recientes',ordersTable(results[1].results)):note('No tienes acceso a las órdenes.'))+link('Bitácora','/auditoria/')+(has('change_union')?link('Sindicatos','sindicatos.html'):'')+(has('add_receipt')?link('Validar retiro de lentes','retiro.html'):'')+(has('view_agreement')?link('Gestión de convenios','convenios.html'):'')+(has('view_product')?link('Administración de catálogo','catalogo.html?gestion=1'):'')+(has('view_inquiry')?btn('Mostrar QR de atención','attention-qr')+link('Solicitudes recibidas','solicitudes.html'):'');
 }
 else if(page==='detalle_cliente'){
 const c=await api('clients/'+params.get('cliente')+'/');screen.innerHTML=head(c.name,c.rut)+panel('Ficha de cliente',`<p>${esc(c.phone)} · ${esc(c.email)}</p><p>${esc(c.category)} · Contacto posventa: ${c.consent?'Autorizado':'No autorizado'}</p><p>Estado: ${c.active?'Activo':'Inactivo'}</p>`+btn('Editar ficha','client-edit',c.id)) +link('Clientes','clientes.html');
  if(has('view_agreement')){const a=await api('clients/'+c.id+'/agreement/');screen.innerHTML+=panel('Atención por convenio',note(a.agreement?`${a.agreement} · ${a.available?'Vigente':'Fuera de vigencia'} · ${a.verified?(a.role==='carga'?'Carga validada':'Titular validado'):'Sin validación registrada'}`:'Sin convenio asociado.')+(a.pending?note('Tiene una solicitud de pertenencia pendiente.'):'')+(has('view_inquiry')?link('Revisar solicitudes','solicitudes.html'):'')+(has('add_request')?btn('Registrar atención presencial','agreement-visit',c.id):''));}
 }
 else if(page==='recepcion'&&params.get('pedido'))await delivery();
 else if(endpoints[page])await modulePage();
 else screen.innerHTML=head('Módulo no disponible');
 }catch(e){error(e);}finally{document.documentElement.dataset.amaruReady='true';}
}
const categories=[['seguridad','Armazones de seguridad'],['armazon','Armazones particulares'],['cristal','Cristales'],['repuesto','Repuestos']];
async function renderCatalog(){
 const manage=params.get('gestion')==='1'&&has('view_product');
 const mining=params.get('scope')==='mining'&&!manage;
 const query=new URLSearchParams([...params].filter(([key])=>['q','category','scope'].includes(key)));
 const data=await list((manage?'catalog-management/':'products/')+'?'+query);
 const filters=form('catalog-filter',input('q','Buscar por nombre o código','search',params.get('q')||'','')+
   select('category','Categoría',[['','Todas'],...categories],params.get('category')||''),'Buscar');
 const navigation=manage?link('Vista pública','catalogo.html'):has('view_product')?link('Administrar catálogo','catalogo.html?gestion=1'):'';
 const create=manage&&has('add_product')?btn('Nuevo producto','product-new'):'';
 const cards=data.results.map(p=>panel(p.name,
  `<img src="${esc(p.active&&p.image_url?p.image_url:'/static/interfaz/img/atencion_optica.svg')}" alt="${esc(p.name)}" style="width:100%;max-height:220px;object-fit:contain">
  <p>${esc(p.description)}</p><dl><dt>Categoría</dt><dd>${esc(categories.find(([value])=>value===p.category)?.[1]||p.category)}</dd>
  <dt>Tipo, cristal y color</dt><dd>${esc([p.lens_type,p.crystal,p.color].filter(Boolean).join(' · ')||'Por definir')}</dd>
  <dt>Tratamientos</dt><dd>${esc(p.treatments||'Por definir')}</dd></dl>
  ${p.reference_price!==null?`<p>Referencia académica: ${currency(p.reference_price)}</p>`:''}
  <p>${p.active?'Visible en el catálogo':'Producto desactivado'}</p>`+
  (manage?(has('change_product')?btn('Editar producto','product-edit',p.id):''):link('Ver producto','producto.html?id='+p.id)+link('Consultar','formulario_remoto.html?tipo=contacto'))));
 screen.innerHTML=head(manage?'Administración de catálogo':mining?'Catálogo de lentes mineros':'Productos y servicios','Catálogo académico con productos de prueba.')+
  navigation+create+(session.mining?link(mining?'Catálogo general':'Catálogo de lentes mineros',mining?'catalogo.html':'catalogo.html?scope=mining'):'')+link('Ver carrito','carrito.html')+filters+`<div class="cards">${cards.join('')||note('No se encontraron productos.')}</div>`+pages(data);
}
async function productRequestForm(id){
 if(!session.authenticated){
  dialog('Solicitar producto',note('Inicia sesión con tu cuenta de cliente para registrar una solicitud de producto.')+link('Iniciar sesión','consulta.html')+link('Consultar sin cuenta','formulario_remoto.html?tipo=lentes'));
  return;
 }
 const [product,recipes]=await Promise.all([api('products/'+id+'/'),api('my-prescriptions/')]);
 dialog('Solicitar '+product.name,
  (product.requires_prescription?note('Este producto requiere una receta vigente. Puedes usar una guardada o cargar un archivo privado.'): '')+
  form('request-product',`<input name="product" type="hidden" value="${esc(id)}">`+
   select('prescription','Receta vigente',[['','Sin receta seleccionada'],...recipes.map(p=>[p.id,'Receta del '+p.issued_on])])+
   area('reason','Indica lo que necesitas')+check('contact_authorized','Autorizo el contacto para gestionar mi solicitud.'),'Enviar solicitud')+
  '<details><summary>Cargar receta</summary>'+form('own-prescription',`<input name="product" type="hidden" value="${esc(id)}">`+
   input('issued_on','Fecha de emisión','date')+input('file','Foto o PDF privado','file','','required accept=".png,.jpg,.jpeg,.pdf"'),'Cargar receta')+'</details>');
 document.querySelector('[data-form="request-product"]').dataset.key=crypto.randomUUID();
}
async function productForm(id){
 const p=id?await api('catalog-management/'+id+'/'):{};
 dialog(id?'Editar producto':'Nuevo producto',form('product',
  `<input type="hidden" name="id" value="${esc(id||'')}">`+input('sku','Código SKU','text',p.sku)+
  input('name','Nombre','text',p.name)+select('category','Categoría',categories,p.category)+area('description','Descripción',p.description)+
  input('variants','Variantes separadas por coma','text',(p.variants||[]).join(', '),'maxlength="1600"')+input('lens_type','Tipo de lente','text',p.lens_type,'')+input('crystal','Cristal','text',p.crystal,'')+
  input('treatments','Tratamientos','text',p.treatments,'')+input('color','Color','text',p.color,'')+
  input('reference_price','Precio ficticio CLP','number',p.reference_price??'','min="0" step="1"')+
  input('image','Imagen JPG o PNG','file','','accept="image/jpeg,image/png"')+
  select('active','Visibilidad',[['true','Activo'],['false','Desactivado']],String(p.active??true))+
  select('mining_only','Catálogo',[['false','General'],['true','Exclusivo de lentes mineros']],String(p.mining_only??false))+
  select('requires_prescription','Receta',[['false','No exige receta'],['true','Exige receta vigente']],String(p.requires_prescription??false))));
}
async function renderAgreements(){
 const result=await list('agreements/');
 const rows=result.results.map(a=>[esc(a.name),esc(a.code||'Guardar para generar'),a.available?'Vigente':'Inactivo o fuera de vigencia',
  (a.managed_union?(has('change_union')?link('Gestionar sindicato','sindicatos.html'):''):(has('change_agreement')?btn('Editar','agreement-edit',a.id):'')+(a.available&&a.code?btn('Mostrar QR','agreement-qr',a.id):''))]);
 screen.innerHTML=head('Gestión de convenios','El código identifica al convenio. La pertenencia requiere revisión del personal.')+
  (has('change_union')?link('Gestionar sindicatos','sindicatos.html'):'')+(has('add_agreement')?btn('Nuevo convenio','agreement-new'):'')+link('Solicitudes de validación','solicitudes.html?verification=all')+
  panel('Convenios',table(['Organización','Código','Estado','Acciones'],rows))+pages(result);
}
async function agreementForm(id){
 const a=id?await api('agreements/'+id+'/'):{};
 dialog(id?'Editar convenio':'Nuevo convenio',form('agreement',
  `<input name="id" type="hidden" value="${esc(id||'')}">`+input('name','Organización','text',a.name)+
  input('starts_on','Inicio','date',a.starts_on,'')+input('ends_on','Término','date',a.ends_on,'')+
  input('contact_name','Responsable','text',a.contact_name,'')+input('contact_email','Correo de contacto','email',a.contact_email,'')+
  select('allow_dependents','Cargas familiares',[['false','No admitidas'],['true','Admitidas']],String(a.allow_dependents??false))+
  select('active','Estado',[['true','Activo'],['false','Inactivo']],String(a.active??true))));
}
function renderMembershipPortal(){
 screen.innerHTML=head('Convenios','Orientación para titulares y cargas familiares de organizaciones con convenio.')+
  panel('Solicita tu validación',note('Utiliza el código que te entregó tu organización o abre su enlace escaneando el QR con la cámara del teléfono. La óptica revisará la pertenencia.')+
   form('membership-start',input('code','Código de organización','text','','required maxlength="24"'),'Continuar al registro')+
   link('Solicitar atención','formulario_remoto.html')+link('Panel del Sindicato','sindicato.html')+link('Acceso de representantes','representante.html'))+
  panel('Consulta tu estado',form('membership-status',input('reference','Referencia privada recibida al enviar','text','','required maxlength="36"'),'Consultar estado'));
}
async function renderRepresentative(){
 if(!session.representative){screen.innerHTML=head('Acceso de representantes')+note('Esta cuenta no está autorizada para revisar un convenio.');return;}
 const data=await api('membership/queue/');
 screen.innerHTML=head('Validación de pertenencia',data.organization)+panel('Solicitudes de tu organización',table(
  ['Nombre','RUT','Calidad','Estado','Acción'],data.requests.map(r=>[esc(r.name),esc(r.rut),esc(r.role),badge(r.state),r.state==='pendiente'?btn('Revisar','representative-review',r.id):''])));
}
function readCart(){
 try{
  const saved=JSON.parse(sessionStorage.getItem('amaru-cart')||'[]');
  return Array.isArray(saved)?saved.filter(x=>Number.isSafeInteger(x.product)&&x.product>0&&Number.isInteger(x.quantity)&&x.quantity>=1&&x.quantity<=99&&typeof x.variant==='string').slice(0,20):[];
 }catch{return [];}
}
function saveCart(items){sessionStorage.setItem('amaru-cart',JSON.stringify(items));}
async function renderProduct(){
 const id=params.get('id')||'';
 if(!/^\d+$/.test(id))throw new Error('Selecciona un producto del catálogo.');
 const p=await api('products/'+id+'/');
 const picture=`<img class="catalog-detail-image" src="${esc(p.image_url||'/static/interfaz/img/atencion_optica.svg')}" alt="${esc(p.name)}">`;
 screen.innerHTML=head(p.name,'Producto de demostración')+panel('Modelo '+p.sku,picture+`<p>${esc(p.description)}</p><p>${esc([p.lens_type,p.crystal,p.color,p.treatments].filter(Boolean).join(' · '))}</p>`+
  note(p.reference_price==null?'Precio sujeto a cotización':'Precio de referencia '+currency(p.reference_price))+
  (p.requires_prescription?note('Requiere una receta vigente.'): '')+
  form('cart-add',`<input name="product" type="hidden" value="${p.id}">`+
   select('variant','Variante',p.variants?.length?p.variants:[['','Modelo único']])+input('quantity','Cantidad','number',1,'required min="1" max="99"'),'Agregar al carrito'))+
  link('Ver carrito','carrito.html')+link('Volver al catálogo','catalogo.html');
}
async function renderCart(){
 const items=readCart();
 screen.innerHTML=head('Carrito','Revisa los productos antes de enviar una solicitud.')+link('Seguir explorando','catalogo.html');
 if(!items.length){screen.innerHTML+=note('Tu carrito está vacío.');return;}
 const ids=[...new Set(items.map(i=>i.product))];
 const {results}=await api('products/?ids='+ids.join(','));
 const products=new Map(results.map(p=>[p.id,p]));
 const invalid=items.some(i=>!products.has(i.product)||!(products.get(i.product).variants?.length?products.get(i.product).variants:['']).includes(i.variant));
 let total=0,complete=true;
 const rows=items.map((i,index)=>{
  const product=products.get(i.product),price=product?.reference_price;
  if(price==null)complete=false;else total+=i.quantity*price;
  return [esc(product?.name||'Producto no disponible')+'<br>'+esc([i.variant,product?.lens_type,product?.crystal,product?.color,product?.treatments].filter(Boolean).join(' · ')),
   `<input aria-label="Cantidad de ${esc(product?.name||'producto')}" type="number" min="1" max="99" value="${i.quantity}" data-cart-index="${index}">`,
   price==null?'Por cotizar':currency(price*i.quantity),product?.requires_prescription?'Sí':'—',btn('Quitar','cart-remove',index)];
 });
 screen.innerHTML+=panel('Productos seleccionados',table(['Producto','Cantidad','Subtotal','Receta','Acción'],rows)+note((complete?'Subtotal de referencia: ':'Subtotal de productos con precio: ')+currency(total)));
 if(invalid){screen.innerHTML+=note('Quita o reemplaza los productos y variantes que ya no están disponibles.');return;}
 if(!session.authenticated){screen.innerHTML+=panel('Identificación',note('Inicia sesión con tu cuenta de cliente para enviar esta selección.')+form('login',input('username','Usuario o correo')+input('password','Contraseña','password','','required autocomplete="current-password"'),'Iniciar sesión')+registrationLink);return;}
 if(!session.client_id){screen.innerHTML+=note('Se requiere una cuenta vinculada a una ficha activa.');return;}
 const [profile,recipes]=await Promise.all([api('checkout/'),api('my-prescriptions/')]);
 const needsRecipe=items.some(i=>products.get(i.product).requires_prescription);
 screen.innerHTML+=panel('Resumen de solicitud',`<p>${esc(profile.name)} · ${esc(profile.phone)} · ${esc(profile.email||'Sin correo')}</p>`+
  note(profile.agreement?'Convenio validado y vigente: '+profile.agreement:'Atención particular')+note('Estado inicial: Nueva · Pendiente de revisión')+
  (needsRecipe?note('El carrito requiere una receta vigente. Si aún no tienes una, solicita una evaluación.'): '')+
  form('checkout',select('mode','Modalidad',[['cotizacion','Solicitud de cotización'],['compra','Solicitud de compra']])+
   select('prescription','Receta privada',[['','Selecciona una receta si corresponde'],...recipes.map(r=>[r.id,'Receta del '+r.issued_on])])+
   area('reason','Observaciones','Solicito revisar la selección del catálogo.')+check('contact_authorized','Autorizo el contacto para gestionar esta solicitud.'),'Enviar solicitud')+
  '<details><summary>Adjuntar receta privada</summary>'+form('cart-recipe',input('issued_on','Fecha de emisión','date')+input('file','JPG, PNG o PDF','file','','required accept=".jpg,.jpeg,.png,.pdf"'),'Guardar receta')+'</details>'+
  link('Agendar evaluación','formulario_remoto.html'));
 const checkout=screen.querySelector('[data-form=checkout]');checkout.dataset.key=crypto.randomUUID();
 checkout.elements.prescription.required=needsRecipe;
 checkout.elements.contact_authorized.required=true;
}
async function purchaseDetail(id){
 const purchase=await api('purchases/'+id+'/');
 const rows=purchase.items.map(i=>[esc(i.product_name),esc(i.variant||'Modelo único'),esc(i.quantity),i.unit_price==null?'Por cotizar':currency(i.unit_price)]);
 let actions='';
 if(purchase.quote)actions=link('Abrir cotizaciones','cotizaciones.html');
 else if(has('add_quote')&&has('view_quote')&&!['Cerrada','Cancelada'].includes(purchase.state)){
  const fields=purchase.items.map(i=>input('price_'+i.id,'Precio unitario CLP','number',i.unit_price??'','required min="0" max="999999999" step="1"')).map((field,index)=>'<div><p>'+esc(purchase.items[index].product_name)+' · '+esc(purchase.items[index].variant)+'</p>'+field+'</div>').join('');
  actions=form('purchase-quote',`<input name="id" type="hidden" value="${esc(id)}">`+fields,'Crear borrador de cotización');
 }
 dialog('Detalle de solicitud',note(purchase.mode+' · '+purchase.state)+note(purchase.agreement||'Atención particular')+
  table(['Producto','Variante','Cantidad','Referencia unitaria'],rows)+
  (purchase.prescription&&has('view_prescription')?btn('Abrir receta autorizada','file','prescriptions/'+purchase.prescription+'/file/'): '')+actions);
}
async function requestForm(){
 const code=params.get('convenio')||'';
 const kind=code||params.get('registro_convenio')==='1'?'registro':params.get('tipo')||'agenda';
 screen.innerHTML=head('Agendar / contactar','No necesitas una cuenta. Tu solicitud será revisada por el personal.')+
 form('inquiry',select('kind','Tipo de solicitud',[['agenda','Atención'],['contacto','Contacto'],['lentes','Orientación de lentes'],['registro','Registro de cliente']],kind)+
 input('name','Nombre completo','text','','required minlength="3" maxlength="180" autocomplete="name"')+
 '<div id="registration-rut" hidden>'+input('registration_rut','RUT para registro','text','','maxlength="12" placeholder="12345678-5"')+'</div>'+
 '<div id="agreement-fields" hidden>'+input('agreement_code','Código de convenio (opcional)','text',code,'maxlength="24"')+select('agreement_role','Calidad',[['','No aplica'],['titular','Titular'],['carga','Carga familiar, si el convenio la permite']],'')+'</div>'+
 input('phone','Teléfono','tel','','required maxlength="30" autocomplete="tel"')+
 input('email','Correo','email','','maxlength="254" autocomplete="email"')+
 input('service','Tipo de atención','text','Orientación de lentes','required maxlength="120"')+
 '<section id="appointment-calendar" class="appointment-calendar" aria-labelledby="appointment-title" hidden>'+
 '<h2 id="appointment-title">Elige una fecha y hora</h2>'+
 '<input type="hidden" name="day"><input type="hidden" name="slot">'+
 '<div data-calendar-content></div><p data-calendar-feedback role="status"></p></section>'+
 area('reason','Motivo de consulta')+
 '<div class="honeypot" aria-hidden="true"><label>Dejar vacío<input name="website" tabindex="-1" autocomplete="off"></label></div>'+
 check('contact_authorized','Autorizo el contacto para gestionar esta solicitud.'),'Registrar solicitud')+
 note('Las horas quedan sujetas a aprobación. El registro de cliente crea una ficha pendiente de revisión, sin cuenta de acceso. Esta autorización no permite promociones ni posventa.')+
 (params.get('origen')==='qr'?note('Origen de esta solicitud: Código QR'):'');
 const f=screen.querySelector('form');f.dataset.key=crypto.randomUUID();f.querySelector('[name=contact_authorized]').required=true;
 const calendar=f.querySelector('#appointment-calendar');
 refreshAppointmentCalendar=mountAppointmentCalendar(f,calendar);
 const update=()=>{
  const kind=f.elements.kind.value;
  const appointment=kind==='agenda';
  calendar.hidden=!appointment;
  for(const name of ['day','slot'])f.elements[name].disabled=!appointment;
  document.getElementById('registration-rut').hidden=kind!=='registro';
  f.elements.registration_rut.required=kind==='registro';
  document.getElementById('agreement-fields').hidden=kind!=='registro';
  f.elements.agreement_role.required=kind==='registro'&&!!f.elements.agreement_code.value.trim();
 };
 f.elements.kind.addEventListener('change',()=>{update();if(!calendar.hidden)refreshAppointmentCalendar();});
 f.elements.agreement_code.addEventListener('input',update);
 update();
 if(!calendar.hidden)await refreshAppointmentCalendar();
}
function mountAppointmentCalendar(form,calendar){
 const content=calendar.querySelector('[data-calendar-content]');
 const feedback=calendar.querySelector('[data-calendar-feedback]');
 const day=form.elements.day,slot=form.elements.slot;
 const weekdays=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
 const monthLabel=new Intl.DateTimeFormat('es-CL',{month:'long',year:'numeric',timeZone:'UTC'});
 const dayLabel=new Intl.DateTimeFormat('es-CL',{dateStyle:'full',timeZone:'UTC'});
 const dateOf=value=>new Date(value+'T00:00:00Z');
 const monthOf=value=>value.slice(0,7);
 let dates=new Map(),months=[],month,loading=false;

 function render(focus){
  const first=dateOf(month+'-01');
  const label=monthLabel.format(first);
  const padding=(first.getUTCDay()+6)%7;
  const last=new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth()+1,0)).getUTCDate();
  const currentMonth=months.indexOf(month);
  const cells=Array.from({length:Math.ceil((padding+last)/7)*7},(_,index)=>{
   const number=index-padding+1;
   if(number<1||number>last)return '<td></td>';
   const value=month+'-'+String(number).padStart(2,'0');
   const hours=dates.get(value)||[];
   const available=hours.some(hour=>hour.status==='available');
   const state=available?'Hay horas disponibles':hours.length?'Sin horas disponibles':'Fuera de agenda';
   return `<td><button type="button" class="appointment-day ${available?'has-hours':''}" data-day="${value}"
    aria-label="${esc(dayLabel.format(dateOf(value))+' · '+state)}" aria-pressed="${day.value===value}"
    ${!hours.length?'disabled':''}>${number}</button></td>`;
  });
  const weeks=[];
  for(let index=0;index<cells.length;index+=7)weeks.push('<tr>'+cells.slice(index,index+7).join('')+'</tr>');
  const hours=dates.get(day.value)||[];
  const hourLabels={available:'Disponible',occupied:'Ocupada',blocked:'No disponible'};
  const hourButtons=hours.map(({time,status})=>`<button type="button" data-hour="${esc(time)}"
   class="appointment-hour ${status==='available'?'':'is-unavailable'}"
   aria-pressed="${slot.value===time}" ${status==='available'?'':'disabled'}>
   <strong>${esc(time)}</strong><span>${hourLabels[status]}</span></button>`).join('');
  content.innerHTML=`<div class="appointment-layout">
   <div class="appointment-month">
    <div class="appointment-month-header">
     <button type="button" data-month-step="-1" aria-label="Mes anterior" ${currentMonth===0?'disabled':''}>‹</button>
     <h3 tabindex="-1" data-month-title>${esc(label)}</h3>
     <button type="button" data-month-step="1" aria-label="Mes siguiente" ${currentMonth===months.length-1?'disabled':''}>›</button>
    </div>
    <table class="appointment-grid" aria-label="${esc(label)}">
     <thead><tr>${weekdays.map(name=>`<th scope="col"><abbr title="${name}">${name.slice(0,2)}</abbr></th>`).join('')}</tr></thead>
     <tbody>${weeks.join('')}</tbody>
    </table>
   </div>
   <div class="appointment-hours">
    <h3>${day.value?esc(dayLabel.format(dateOf(day.value))):'Horarios en Chile'}</h3>
    <div class="appointment-hours-grid">${hourButtons}</div>
    ${!day.value?'<p>Selecciona un día para ver sus horarios.</p>':''}
    <p class="appointment-legend">Los horarios en gris están ocupados o bloqueados.</p>
   </div>
  </div>`;
  if(focus)content.querySelector(focus)?.focus();
 }

 calendar.addEventListener('click',event=>{
  const button=event.target.closest('button');
  if(!button||button.disabled||loading)return;
  const {day:date,hour,monthStep,calendarRetry}=button.dataset;
  if(monthStep){
   month=months[months.indexOf(month)+Number(monthStep)];
   render('[data-month-title]');
  }else if(date){
   if(day.value!==date)slot.value='';
   day.value=date;
   feedback.textContent='';
   render(`[data-day="${date}"]`);
  }else if(hour&&dates.get(day.value)?.some(row=>row.time===hour&&row.status==='available')){
   slot.value=hour;
   feedback.textContent='Horario seleccionado: '+hour+' del '+dayLabel.format(dateOf(day.value))+'.';
   render(`[data-hour="${hour}"]`);
  }else if(calendarRetry!==undefined){
   refresh();
  }
 });

 async function refresh(){
  if(loading)return;
  loading=true;
  feedback.textContent='Cargando horarios…';
  try{
   const availability=await api('agenda/');
   const rows=availability.calendar??availability.days.map(row=>({
    day:row.day,slots:row.slots.map(time=>({time,status:'available'}))
   }));
   if(!rows.length){
    day.value=slot.value='';
    content.innerHTML='<button type="button" class="button soft" data-calendar-retry>Actualizar disponibilidad</button>';
    feedback.textContent='Por ahora no hay horas disponibles.';
    return;
   }
   dates=new Map(rows.map(row=>[row.day,row.slots]));
   months=[...new Set(rows.map(row=>monthOf(row.day)))];
   month=months.includes(month)?month:months[0];
   const selected=dates.get(day.value);
   if(!selected?.length)day.value='';
   if(!selected?.some(row=>row.time===slot.value&&row.status==='available'))slot.value='';
   feedback.textContent='';
   render();
  }catch{
   day.value=slot.value='';
   content.innerHTML='<button type="button" class="button soft" data-calendar-retry>Reintentar</button>';
   feedback.textContent='No pudimos cargar los horarios. Vuelve a intentarlo.';
  }finally{
   loading=false;
  }
 }
 return refresh;
}
async function showAttentionQR(){
 clearInterval(qrRefresh);
 const data=await api('attention-qr/');
 dialog('Formulario de atención — Ópticas Amaru',`<div class="attention-qr"><p>Escanea el código con la cámara del celular y completa el formulario.</p>${data.warning?note(data.warning):''}${data.scannable?`<img id="attention-qr" src="/api/attention-qr/?image=png&t=${Date.now()}" alt="Código QR del formulario público de atención"><p class="qr-url">${esc(data.url)}</p><div class="actions">${btn('Copiar enlace','qr-copy',data.url)}${btn('Ampliar QR','qr-enlarge')}${link('Descargar QR','/api/attention-qr/?image=png&download=1')}${btn('Imprimir QR','qr-print')}</div>${data.staff_url?link('Solicitudes de la demostración',data.staff_url):''}`:''}</div>`);
 qrRefresh=setInterval(async()=>{if(!document.getElementById('app-dialog').open||!document.querySelector('.attention-qr')){clearInterval(qrRefresh);return;}try{const next=await api('attention-qr/');if(next.url!==data.url)await showAttentionQR();}catch(e){message(e.message);}},10000);
}
function printAttentionQR(){const img=document.getElementById('attention-qr');if(!img)return;const win=window.open('about:blank','_blank');if(!win)throw new Error('Permite abrir la ventana de impresión.');win.document.write('<!doctype html><title>QR — Ópticas Amaru</title><style>body{font:20px sans-serif;text-align:center}img{width:440px;max-width:90%}p{overflow-wrap:anywhere}</style><h1>Formulario de atención — Ópticas Amaru</h1><p>Escanea para dejar tu solicitud</p><img alt="QR" src="'+img.src+'"><p>'+esc(document.querySelector('.qr-url').textContent)+'</p>');win.document.close();win.onload=()=>win.print();}

function ordersTable(rows,own=false){return table(['Orden','Cliente','Producto','Estado','Acción'],rows.map(o=>[esc(o.folio),esc(o.client_name),esc(Object.values(o.characteristics).join(' · ')),badge(o.status),`<div class="actions">${o.status==='Disponible para retiro'?(own?btn('Ver código de retiro','pickup-owner',o.id):link('Revisar retiro','recepcion.html?pedido='+o.id)):''}${!own&&o.status!=='Entregada'&&has('change_order')?btn('Actualizar','order-state',o.id):''}${o.status==='Entregada'?link('Documentos','documentos.html'):''}</div>`]));}
async function modulePage(){
 const endpoint=endpoints[page],q=page==='clientes'&&params.get('q')?'?q='+encodeURIComponent(params.get('q')):page==='solicitudes'?'?'+new URLSearchParams([...params].filter(([k])=>['status','day','verification'].includes(k))):'';
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
 else if(page==='solicitudes'){
 action=btn('Mostrar QR de atención','attention-qr')+btn('Actualizar solicitudes','reload');
 body=form('inquiry-filter',select('status','Estado',[['','Todos'],...['Nueva','En revisión','Contactada','Cerrada','Cancelada']],params.get('status')||'')+input('day','Fecha de recepción','date',params.get('day')||'',''),'Filtrar')+
 table(['ID / recepción','Solicitante','Tipo / origen','Estado','Acción'],data.results.map(r=>[esc(r.id)+'<br>'+date(r.created_at),esc(r.name),esc(r.kind)+'<br>'+esc(r.source==='qr'?'Código QR':'Sitio web'),badge(r.status),btn('Ver detalle','inquiry-detail',r.id)+(has('change_inquiry')?btn('Revisar estado','inquiry-state',r.id):'')]));
 }
 else if(page==='garantias'){
 action=has('add_warranty')?btn('Registrar solicitud','warranty-new'):'';
 body=table(['Folio','Orden','Tipo','Motivo','Estado','Acción'],data.results.map(w=>[esc(w.folio),esc(w.order),esc(w.kind),esc(w.reason),badge(w.status),has('change_warranty')?btn('Revisar','warranty-edit',w.id):'']));
 }else if(page==='inventario')body=table(['Artículo','Categoría','Cantidad','Acción'],data.results.map(i=>[esc(i.name),esc(i.category),esc(i.quantity),has('change_inventory')?btn('Actualizar cantidad','inventory-edit',i.id):'']));
 screen.innerHTML=head(names[page],'Registros del servidor. Se aplican permisos en cada operación.')+action+panel(names[page],body)+pages(data);
 if(page==='solicitudes'&&has('view_agendablock'))await renderAgendaBlocks();
 if(['ordenes','recepcion'].includes(page)&&has('add_receipt'))screen.insertAdjacentHTML('afterbegin',link('Validar retiro de lentes','retiro.html'));
 if(page==='documentos'&&has('change_siteconfiguration'))screen.innerHTML+=btn('Configurar garantía','settings');
}
async function renderAgendaBlocks(){
 const rows=await api('agenda/blocks/');
 const editable=has('add_agendablock')&&has('change_agendablock');
 const dateFields=input('block_day','Fecha a bloquear','date')+input('slot','Hora opcional (vacío bloquea todo el día)','time','','');
 const controls=editable?form('agenda-block',dateFields,'Bloquear') : '';
 const history=table(['Fecha','Hora','Estado','Acción'],rows.map(row=>[
  esc(row.day),esc(row.slot||'Día completo'),row.active?'Bloqueado':'Liberado',
  row.active&&editable&&row.day>=new Date().toLocaleDateString('sv-SE',{timeZone:'America/Santiago'})?btn('Liberar','agenda-unblock',row.day+'|'+row.slot):''
 ]));
 screen.innerHTML+=panel('Administración de agenda',controls+history);
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
async function delivery(orderId=params.get('pedido')){
 review=await api('orders/'+orderId+'/preview/');
 screen.innerHTML=head('Documento de entrega y conformidad','Revise los datos antes de aceptar. Firma electrónica simple; no avanzada.')+panel('Datos de entrega',`<dl><dt>Cliente</dt><dd>${esc(review.client)}</dd><dt>RUT</dt><dd>${esc(review.rut)}</dd><dt>Orden</dt><dd>${esc(review.order)}</dd><dt>Producto</dt><dd>${esc(Object.values(review.product).join(' · '))}</dd><dt>Estado</dt><dd>${esc(review.status)}</dd></dl><h3>Condiciones de garantía</h3><p style="white-space:pre-wrap">${esc(review.terms)}</p>`);
 if(review.status!=='Disponible para retiro'){screen.innerHTML+=note('Esta orden no está disponible para retiro.');return;}
 if(has('add_receipt')&&has('view_order')){
  screen.innerHTML+=panel('Código de retiro',link('Validar retiro de lentes','retiro.html')+
   btn('Reemitir código','pickup-reissue',review.order)+btn('Revocar código','pickup-revoke',review.order));
 }
 if(review.pickup_required&&pickupReview?.order!==review.order){
  screen.innerHTML+=note('El vendedor debe validar el código y comprobar la identidad antes de completar la entrega.');return;
 }
 screen.innerHTML+=panel('Confirmación de recepción',form('delivery',input('observations','Observaciones','text','','')+'<div class="wide"><label for="signature">Firma electrónica simple</label><canvas id="signature" class="signature-pad" style="width:100%;height:180px;touch-action:none" aria-label="Firma de recepción"></canvas>'+btn('Limpiar firma','clear-signature')+'</div>'+check('accepted','Revisé los datos y condiciones y confirmo la recepción de los lentes.'),'Confirmar entrega'));
 setupSignature();
}
function setupSignature(){signature='';const canvas=document.getElementById('signature'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect();canvas.width=Math.max(300,rect.width);canvas.height=180;ctx.lineWidth=2.5;ctx.lineCap='round';let drawing=false,points=0;canvas.onpointerdown=e=>{drawing=true;canvas.setPointerCapture(e.pointerId);ctx.beginPath();ctx.moveTo(e.offsetX,e.offsetY);};canvas.onpointermove=e=>{if(!drawing)return;ctx.lineTo(e.offsetX,e.offsetY);ctx.stroke();points++;};canvas.onpointerup=()=>{drawing=false;if(points>3)signature=canvas.toDataURL('image/png');};canvas.clear=()=>{ctx.clearRect(0,0,canvas.width,canvas.height);signature='';points=0;};}
async function openFile(path){const win=window.open('about:blank','_blank');try{const r=await fetch('/api/'+path,{credentials:'same-origin'});if(!r.ok)throw new Error('No se pudo acceder al documento autorizado.');if(r.headers.get('content-type')?.includes('json')){const data=await r.json();if(win)win.location=data.url;else location.href=data.url;}else{const url=URL.createObjectURL(await r.blob());if(win)win.location=url;else location.href=url;setTimeout(()=>URL.revokeObjectURL(url),60000);}}catch(e){win?.close();throw e;}}
document.addEventListener('change',async e=>{
 const field=e.target;
 if(!field.matches('[data-cart-index]'))return;
 const items=readCart(),line=items[Number(field.dataset.cartIndex)];
 if(!line)return;
 if(!field.reportValidity()||!Number.isInteger(field.valueAsNumber)){field.value=line.quantity;return;}
 line.quantity=field.valueAsNumber;
 try{saveCart(items);await renderCart();}catch(err){error(err);}
});
document.addEventListener('submit',async e=>{
 const f=e.target;if(!f.dataset.form)return;e.preventDefault();if(!f.reportValidity())return;
 const data=Object.fromEntries(new FormData(f)),submit=f.querySelector('[type=submit]');
 if(f.dataset.form==='inquiry'&&data.kind==='agenda'&&(!data.day||!data.slot)){
  f.querySelector('[data-calendar-feedback]').textContent='Selecciona un día y un horario disponible.';
  f.querySelector('#appointment-title').scrollIntoView({block:'nearest'});
  return;
 }
 submit.disabled=true;
 try{switch(f.dataset.form){
 case 'membership-start':location.href='formulario_remoto.html?registro_convenio=1&convenio='+encodeURIComponent(data.code.trim());return;
 case 'membership-status':{const result=await api('membership/status/',{method:'POST',body:data});f.querySelector('.form-feedback').textContent='Estado: '+result.state;return;}
 case 'representative-review':{const id=data.id;delete data.id;await api('membership/queue/'+id+'/',{method:'POST',body:data});break;}
 case 'cart-add':{const items=readCart(),product=Number(data.product),quantity=Number(data.quantity),variant=data.variant;const line=items.find(i=>i.product===product&&i.variant===variant);if(line){if(line.quantity+quantity>99)throw new Error('El máximo por variante es 99.');line.quantity+=quantity;}else{if(items.length>=20)throw new Error('El carrito admite hasta 20 selecciones.');items.push({product,variant,quantity});}saveCart(items);location.href='carrito.html';return;}
 case 'cart-recipe':await api('my-prescriptions/',{method:'POST',body:new FormData(f)});await renderCart();message('Receta privada guardada. Selecciónala para continuar.');return;
 case 'checkout':{const payload={...data,items:readCart(),contact_authorized:!!data.contact_authorized,idempotency_key:f.dataset.key};if(!payload.prescription)delete payload.prescription;const result=await api('checkout/',{method:'POST',body:payload});saveCart([]);screen.innerHTML=head('Solicitud registrada','El personal revisará tu selección.')+note('Referencia: '+result.reference)+link('Volver al catálogo','catalogo.html');return;}
 case 'purchase-quote':{const prices=Object.fromEntries(Object.entries(data).filter(([key])=>key.startsWith('price_')).map(([key,value])=>[key.slice(6),Number(value)]));const result=await api('purchases/'+data.id+'/quote/',{method:'POST',body:{prices}});close();if(has('change_quote'))await quoteForm(result.id);message('Borrador creado: '+result.folio);return;}
 case 'register':{
   const r=await api('register/',{method:'POST',body:{...data,privacy:!!data.privacy,promotions:!!data.promotions}});
   f.reset();screen.innerHTML=head('Solicitud recibida')+note(r.detail)+link('Volver a Iniciar sesión','consulta.html');return;
 }
 case 'account-recipe':{
   await api('my-prescriptions/',{method:'POST',body:new FormData(f)});
   f.reset();f.querySelector('.form-feedback').textContent='Receta privada guardada. Puedes elegirla al solicitar productos.';return;
 }

 case 'claim-invitation':{
  if(data.password!==data.password_confirmation)throw new Error('Las contraseñas no coinciden.');
  const token=new URLSearchParams(location.hash.slice(1)).get('token');
  const result=await api('invitation/claim/',{method:'POST',body:{token,password:data.password||undefined,accepted:!!data.accepted}});
  history.replaceState(null,'',location.pathname);
  screen.innerHTML=head(result.state==='review'?'Vinculación pendiente de revisión':'Acceso activado')+
   note(result.state==='review'?'Ópticas Amaru verificará la vinculación con tu ficha personal.':'Ya puedes ingresar con tu cuenta.')+
   link('Iniciar sesión','consulta.html')+link('Panel del Sindicato','sindicato.html');return;
 }
 case 'union-new':{
  data.allow_dependents=!!data.allow_dependents;
  const result=await api('unions/',{method:'POST',body:data});close();await renderUnionAdmin();invitationDialog(result.invitation);return;
 }
 case 'union-edit':{
  const id=data.id;delete data.id;
  await api('unions/'+id+'/manage/',{method:'PATCH',body:data});break;
 }
 case 'union-upload':{const body=new FormData(f);body.delete('id');await api('unions/'+data.id+'/document/',{method:'POST',body});break;}
 case 'union-manage':{
  const result=await api('unions/'+data.id+'/manage/',{method:'POST',body:{action:data.action,note:data.note,reviewed:!!data.reviewed}});
  if(result.invitation){close();await renderUnionAdmin();invitationDialog(result.invitation);return;}break;
 }
 case 'union-sign':await api('union/sign/',{method:'POST',body:{...data,accepted:!!data.accepted}});break;
 case 'union-worker':{
  const result=await api('union/workers/',{method:'POST',body:data});await renderUnion();invitationDialog(result.invitation);return;
 }
 case 'worker-manage':{
  if(data.action==='edit'){if(!data.name)delete data.name;if(!data.phone)delete data.phone;}
  const result=await api('union/workers/'+data.id+'/',{method:data.action==='edit'?'PATCH':'POST',body:data});
  if(result.invitation){close();await render();invitationDialog(result.invitation);return;}break;
 }
 case 'union-password':await api('union/account/',{method:'POST',body:data});location.reload();return;
 case 'pickup-validate':{
  const code=data.code.trim();
  if(f.dataset.confirmIdentity&&!data.identity_checked)throw new Error('Confirma que verificaste la identidad.');
  const result=await api('pickup/validate/',{method:'POST',body:{code,identity_checked:!!data.identity_checked}});
  if(!result.proof){
   dialog('Comprueba la identidad',note(result.folio+' · '+result.client+' · '+result.rut)+
    form('pickup-validate',hidden('code',code)+check('identity_checked','Verifiqué la identidad o autorización de quien retira.'),'Validar y revisar entrega'));
   document.querySelector('#app-dialog [data-form="pickup-validate"]').dataset.confirmIdentity='1';
   return;
  }
  close();pickupReview={order:result.order,proof:result.proof};await delivery(result.order);return;
 }
 case 'login':{const r=await api('login/',{method:'POST',body:{username:data.username,password:data.password??data.current_password}});csrf=r.csrf;location.reload();return;}
 case 'search':location.href='clientes.html?q='+encodeURIComponent(data.q);return;
 case 'catalog-filter':{const query=new URLSearchParams(data);if(params.get('scope')==='mining')query.set('scope','mining');if(params.get('gestion')==='1')query.set('gestion','1');location.href='catalogo.html?'+query;return;}
 case 'own-prescription':{const payload=new FormData(f);payload.delete('product');await api('my-prescriptions/',{method:'POST',body:payload});close();await productRequestForm(data.product);message('Receta guardada. Selecciona una vigente.');return;}
 case 'request-product':{if(!data.prescription)delete data.prescription;data.contact_authorized=!!data.contact_authorized;data.idempotency_key=f.dataset.key;const result=await api('product-requests/',{method:'POST',body:data});close();dialog('Solicitud registrada',note('Queda pendiente de revisión por el personal.')+`<p>Referencia: ${esc(result.reference)}</p>`);return;}
 case 'product':{const payload=new FormData(f),id=data.id;payload.delete('id');payload.set('variants',JSON.stringify(data.variants.split(',').map(v=>v.trim()).filter(Boolean)));if(!payload.get('image').size)payload.delete('image');await api('catalog-management/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:payload});break;}
 case 'inquiry-filter':{const filter=new URLSearchParams(data);if(params.get('verification'))filter.set('verification',params.get('verification'));location.href='solicitudes.html?'+filter;return;}
 case 'agreement':{const id=data.id;delete data.id;for(const field of ['starts_on','ends_on'])data[field]=data[field]||null;await api('agreements/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});break;}
 case 'agreement-review':{const id=data.id;delete data.id;await api('agreement-verifications/'+id+'/',{method:'POST',body:data});break;}
 case 'agenda-block':{data.day=data.block_day;delete data.block_day;if(!data.slot)delete data.slot;await api('agenda/blocks/',{method:'POST',body:data});break;}
 case 'inquiry':data.source=params.get('origen')==='qr'?'qr':'web';if(data.kind!=='registro'){delete data.registration_rut;delete data.agreement_code;delete data.agreement_role;}data.contact_authorized=!!data.contact_authorized;data.idempotency_key=f.dataset.key;data.day=data.day||null;data.slot=data.slot||null;{const r=await api('inquiries/',{method:'POST',body:data});screen.innerHTML=head('Solicitud registrada')+note(r.detail)+`<p>Referencia: ${esc(r.reference)}</p>`+link('Volver al inicio','index.html');return;}
 case 'client':{const id=data.id;delete data.id;data.consent=!!data.consent;data.active=data.active==='true';data.agreement=data.agreement||null;await api('clients/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});break;}
 case 'recipe':await api('prescriptions/',{method:'POST',body:new FormData(f)});break;
 case 'quote':{const id=data.id;delete data.id;data.approved=!!data.approved;data.agreement=data.agreement||null;data.prescription=data.prescription||null;data.characteristics=data.product_type==='particular'?{frame:data.frame,crystal:data.crystal,focus:data.focus}:{security_model:data.frame,security_color:data.crystal,focus:data.focus};delete data.frame;delete data.crystal;delete data.focus;await api('quotes/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});break;}
 case 'warranty':{const id=data.id;delete data.id;await api('warranties/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});break;}
 case 'state':await api(data.endpoint,{method:data.endpoint.startsWith('orders/')?'POST':'PATCH',body:{status:data.status}});break;
 case 'inventory':await api('inventory/'+data.id+'/',{method:'PATCH',body:{quantity:Number(data.quantity)}});break;
 case 'settings':await api('configuration/',{method:'PATCH',body:data});break;
 case 'delivery':if(!data.accepted||!signature)throw new Error('Debe aceptar la conformidad y dibujar la firma.');{const r=await api('orders/'+review.order+'/deliver/',{method:'POST',body:{accepted:true,signature,review_token:review.review_token,pickup_proof:pickupReview?.order===review.order?pickupReview.proof:undefined,observations:data.observations}});screen.innerHTML=head('Entrega registrada')+note('La orden está entregada. El documento y su referencia quedaron guardados en el servidor.')+btn('Ver documento / PDF','file','receipts/'+r.id+'/pdf/')+link('Documentos','documentos.html');return;}
 }close();await render();message('Operación guardada en el servidor.');
 }catch(err){
  if(f.dataset.form==='inquiry'&&data.kind==='agenda'&&err.status===409){
   await refreshAppointmentCalendar();
  }
  if(f.dataset.form==='register'&&err.status===400){
   try{f.elements.challenge.value=(await api('register/')).challenge;}catch{/* Conserva la explicación del error original. */}
  }
  f.querySelector('.form-feedback').textContent=err.message;
 }finally{submit.disabled=false;}
});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-op]');if(!b)return;const id=b.dataset.id;try{switch(b.dataset.op){
 case 'cart-remove':{const items=readCart();items.splice(Number(id),1);saveCart(items);await renderCart();break;}
 case 'purchase-detail':await purchaseDetail(id);break;
 case 'representative-review':dialog('Validar pertenencia',form('representative-review',`<input name="id" type="hidden" value="${esc(id)}">`+select('approved','Decisión',[['true','Confirmar pertenencia'],['false','Rechazar']])+input('note','Referencia interna de la verificación')));break;
 case 'reload':location.reload();break;
 case 'agenda-unblock':{const [day,slot]=id.split('|');await api('agenda/blocks/',{method:'POST',body:{day,...(slot?{slot}:{}),active:false}});await render();message('Bloqueo liberado.');break;}
 case 'attention-qr':await showAttentionQR();break;
 case 'qr-copy':await navigator.clipboard.writeText(id);message('Enlace copiado.');break;
 case 'qr-enlarge':document.querySelector('.attention-qr').classList.toggle('enlarged');break;
 case 'qr-print':printAttentionQR();break;
 case 'inquiry-detail':{const r=await api('inquiries/'+id+'/');dialog('Solicitud #'+r.id,`<dl><dt>Solicitante</dt><dd>${esc(r.name)}</dd><dt>Contacto</dt><dd>${esc(r.phone)} · ${esc(r.email||'No informado')}</dd><dt>Tipo y origen</dt><dd>${esc(r.kind)} · ${esc(r.source==='qr'?'Código QR':'Sitio web')}</dd><dt>Recepción</dt><dd>${date(r.created_at)}</dd><dt>Atención solicitada</dt><dd>${esc(r.service)} · ${esc(r.day||'')} ${esc(r.slot||'')}</dd><dt>Motivo y observaciones</dt><dd>${esc(r.reason)}</dd><dt>Estado</dt><dd>${esc(r.status)}</dd></dl>${r.kind==='compra'?btn('Detalle de compra','purchase-detail',r.id):''}${r.agreement?`<p>Convenio #${esc(r.agreement)} · ${esc(r.agreement_role)} · ${esc(r.verification_state)}</p>`:''}${r.verification_state==='pendiente'&&has('change_agreement')?btn('Validar pertenencia','agreement-review',r.id):''}${r.product?`<p>Producto de catálogo #${esc(r.product)}</p>`:''}${r.prescription&&has('view_prescription')?btn('Ver receta autorizada','file','prescriptions/'+r.prescription+'/file/'):''}${r.client?link('Revisar ficha asociada','detalle_cliente.html?cliente='+r.client):''}`);break;}
 case 'logout':await api('logout/',{method:'POST',body:{}});location.href='index.html';break;
 case 'agreement-visit':{const result=await api('clients/'+id+'/agreement/',{method:'POST',body:{}});message(result.detail);break;}
 case 'agreement-new':await agreementForm();break;
 case 'agreement-edit':await agreementForm(id);break;
 case 'agreement-qr':{const data=await api('agreements/'+id+'/qr/');dialog('QR de convenio',`<div class="attention-qr"><img alt="Código QR del convenio" src="/api/agreements/${esc(id)}/qr/?image=png"><p class="qr-url">${esc(data.url)}</p>${btn('Copiar enlace','qr-copy',data.url)}</div>`);break;}
 case 'agreement-review':dialog('Validar pertenencia',form('agreement-review',`<input name="id" type="hidden" value="${esc(id)}">`+select('approved','Decisión',[['true','Aprobar'],['false','Rechazar']])+select('method','Método',[['nomina','Nómina autorizada'],['responsable','Responsable del convenio'],['presencial','Validación presencial']])+input('note','Referencia de verificación, sin datos sensibles')));break;
 case 'request-product':await productRequestForm(id);break;

 case 'union-new':showUnionForm();break;
 case 'union-edit':{
  const u=unionAdminRows.find(row=>String(row.id)===id);
  if(!u)throw new Error('No se encontró el sindicato.');
  dialog('Editar datos institucionales',form('union-edit',hidden('id',id)+
   area('institutional_details','Datos institucionales',u.institutional_details)+
   input('starts_on','Inicio de vigencia','date',u.starts_on)+
   input('ends_on','Término de vigencia','date',u.ends_on),'Guardar datos'));
  break;
 }
 case 'union-upload':dialog('Asociar documento privado',form('union-upload',hidden('id',id)+
  input('file','PDF autorizado del convenio','file','','required accept="application/pdf,.pdf"'),'Asociar PDF'));break;
 case 'union-invite':case 'union-suspend':case 'union-activate':{
  const action=b.dataset.op.slice(6);
  const title={invite:'Reemitir invitación del representante',suspend:'Suspender sindicato',activate:'Activar sindicato'}[action];
  dialog(title,form('union-manage',hidden('id',id)+hidden('action',action)+
   (action==='activate'?check('reviewed','Revisé el documento firmado y autorizo la activación.'): '')+
   (action==='invite'?'':input('note','Referencia interna de revisión','text','','required minlength="5" maxlength="240"')),title));break;
 }
 case 'worker-disable':case 'worker-reissue':case 'worker-recovery':case 'worker-review':case 'worker-reset':case 'worker-edit':{
  const action=b.dataset.op.slice(7);
  const title={disable:'Desactivar trabajador',reissue:'Reemitir invitación',recovery:'Solicitar recuperación',
   review:'Verificar y vincular',reset:'Preparar recuperación',edit:'Editar datos administrativos'}[action];
  const actionFields=['review','reset'].includes(action)?input('note','Referencia de verificación del titular','text','','required minlength="5" maxlength="240"'):
   action==='edit'?input('name','Nombre registrado','text','','maxlength="180"')+input('phone','Teléfono administrativo','tel','','maxlength="30"'):'';
  dialog(title,form('worker-manage',hidden('id',id)+hidden('action',action)+actionFields,title));break;
 }
 case 'copy-invitation':await navigator.clipboard.writeText(id);message('Enlace copiado.');break;
 case 'pickup-owner':{
  const result=await api('pickup/'+id+'/');dialog('Tus lentes están disponibles para retiro',
   `<p class="pickup-code">${esc(result.code)}</p><p>Vence el ${esc(date(result.expires_at))}.</p>`+
   note('Muestra este código al vendedor al momento del retiro.'));break;
 }
 case 'pickup-reissue':case 'pickup-revoke':
  await api('pickup/'+id+'/',{method:'POST',body:{action:b.dataset.op==='pickup-reissue'?'reissue':'revoke'}});
  pickupReview=null;await delivery(id);message('Código de retiro actualizado.');break;
 case 'product-new':await productForm();break;
 case 'product-edit':await productForm(id);break;
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
if(page==='dashboard'&&params.get('qr')==='1')document.addEventListener('amaru-rendered',()=>{if(has('view_inquiry'))showAttentionQR().catch(e=>message(e.message));},{once:true});
document.querySelector('[data-menu]')?.addEventListener('click',e=>{const open=document.querySelector('.sidebar').classList.toggle('open');e.currentTarget.setAttribute('aria-expanded',String(open));});
document.querySelector('[data-public-menu]')?.addEventListener('click',e=>{const open=document.getElementById('public-nav').classList.toggle('open');e.currentTarget.setAttribute('aria-expanded',String(open));});
(async()=>{try{
 session=await api('session/');csrf=session.csrf;
 if(session.authenticated)document.querySelector('[data-signup-nav]')?.remove();
 const navigation={clientes:'view_client',recetas:'view_prescription',cotizaciones:'view_quote',ordenes:'view_order',recepcion:'add_receipt',documentos:'view_receipt',solicitudes:'view_inquiry',garantias:'view_warranty',inventario:'view_inventory'};
 document.querySelectorAll('.sidebar a[href]').forEach(a=>{const route=a.getAttribute('href').split('.')[0];if(navigation[route]&&!has(navigation[route]))a.hidden=true;});
 if(session.authenticated&&!has('view_order')&&['recepcion','documentos'].includes(page)){
  const side=document.querySelector('.sidebar');if(side)side.hidden=true;
  const app=document.querySelector('.app');if(app)app.style.display='block';
  const topbar=document.querySelector('.topbar');if(topbar)topbar.innerHTML=link('Mis pedidos','consulta.html')+link('Mis documentos','documentos.html');
 }
 const top=document.querySelector('.topbar')||document.querySelector('.public-header');
 if(session.authenticated)top?.insertAdjacentHTML('beforeend',(session.union?link('Panel del Sindicato','sindicato.html'):session.representative?link('Validar pertenencia','representante.html'):'')+(session.mining?link('Lentes mineros','catalogo.html?scope=mining'):'')+btn('Cerrar sesión','logout'));
 document.querySelectorAll('.demo-tag').forEach(n=>n.textContent='DATOS DEL SERVIDOR');await render();document.dispatchEvent(new Event('amaru-rendered'));
}catch(e){error(e);}finally{delete document.documentElement.dataset.amaruStarting;document.documentElement.dataset.amaruReady='true';}})();
})();
