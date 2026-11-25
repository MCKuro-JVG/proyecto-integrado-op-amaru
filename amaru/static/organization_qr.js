/* QR de organización. Toda vinculación y validación se persiste en Django. */
window.AmaruOrganizationQR=function(ctx){
 'use strict';
 const {api,esc,head,panel,input,select,check,form,table,btn,link,note,dialog,message,screen,params,date,mountAppointmentCalendar}=ctx;
 let organization=null,rosterTimer=null,unionTimer=null,refreshCalendar=null,rosterBusy=false,rosterSnapshot='';
 const endpoint=(purpose,token)=>'organization-qr/'+purpose+'/'+encodeURIComponent(token)+'/';
 const hidden=(name,value)=>'<input type="hidden" name="'+name+'" value="'+esc(value)+'">';
 const stateLabel=s=>({pending:'Pendiente',active:'Activa',inactive:'Inactiva',inactiva:'Inactiva',pendiente:'Pendiente',aprobada:'Activa',rechazada:'Rechazada'}[s]||s);
 const action=(label,op,id)=>btn(label,'orgqr-'+op,id);

 async function publicPage(purpose){
  const token=params.get('qr')||'';
  const data=await api(endpoint(purpose,token));
  const worker=purpose==='worker';
  screen.innerHTML=head(data.title,data.organization)+
   panel('Organización identificada','<p><strong>'+esc(data.organization)+'</strong> · '+esc(data.organization_type==='sindicato'?'Sindicato':'Convenio')+'</p>'+note('La organización y el código se reconocen automáticamente desde este enlace. No necesitas seleccionarlos.'));
  if(!worker){
   screen.innerHTML+=panel('Información y beneficios publicados',note('La pertenencia debe validarse antes de habilitar beneficios o catálogos exclusivos.')+
    (data.benefits.length?data.benefits.map(b=>'<article class="organization-benefit"><h3>'+esc(b.name)+'</h3><p>'+esc(b.description)+'</p><p>'+esc(b.type)+' '+esc(b.value==null?'':b.kind==='percent'?Number(b.value)+' %':Number(b.value).toLocaleString('es-CL',{style:'currency',currency:'CLP',maximumFractionDigits:0}))+'</p><p>'+esc(b.conditions)+'</p></article>').join(''):note('No hay condiciones comerciales autorizadas para publicación en este convenio.'))+
    link('Consultar productos y servicios','catalogo.html'));
  }
  let fields=input('name','Nombre completo','text','','required maxlength="180" autocomplete="name"');
  if(worker)fields+=input('rut','RUT','text','','required maxlength="18" placeholder="12.345.678-5"');
  fields+=input('email',worker?'Correo electrónico':'Correo electrónico (opcional)','email','',worker?'required maxlength="150" autocomplete="email"':'maxlength="150" autocomplete="email"')+
   input('phone','Número de teléfono','tel','','required maxlength="30" autocomplete="tel"');
  if(worker){
   fields+=select('role','Calidad',data.allow_dependents?[['titular','Titular'],['carga','Carga familiar']]:[['titular','Titular']]);
  }else{
   fields+=select('kind','Tipo de solicitud',[['contacto','Consulta o información'],['lentes','Solicitar cotización u orientación'],['agenda','Agendar atención']])+
    select('service','Tema',[['Información general','Información general'],['Beneficios','Beneficios publicados'],['Productos y servicios','Productos y servicios'],['Lentes mineros','Información sobre lentes mineros'],['Cotización','Cotización'],['Modalidades de atención','Modalidades de atención']])+
    '<div class="field wide"><label for="reason">Pregunta o motivo</label><textarea id="reason" name="reason" required minlength="5" maxlength="2000"></textarea></div>'+
    '<section id="appointment-calendar" class="appointment-calendar wide" hidden><h2 id="appointment-title">Elige una fecha y hora</h2>'+hidden('day','')+hidden('slot','')+'<div data-calendar-content></div><p data-calendar-feedback role="status"></p></section>'+
    check('contact_authorized','Autorizo el contacto para gestionar esta consulta.');
  }
  fields+='<label class="check wide"><input name="privacy" type="checkbox" required><span>Acepto la <a href="privacidad.html" target="_blank" rel="noopener">política de privacidad</a> para gestionar esta '+(worker?'solicitud de vinculación':'consulta')+'.</span></label>'+
   hidden('privacy_version',data.privacy_version)+hidden('challenge',data.challenge)+
   '<div class="signup-trap" aria-hidden="true"><label for="org-website">Sitio web (dejar vacío)</label><input id="org-website" name="website" tabindex="-1" autocomplete="off"></div>';
  screen.innerHTML+=panel(worker?'Tus datos de registro':'Envía tu consulta',
   note(worker?'Tu registro quedará pendiente de verificar identidad y pertenencia. No crea una cuenta ni modifica una ficha existente. La óptica coordinará una invitación individual o la activación segura de tu cuenta.':'Enviar esta consulta no crea una cuenta de trabajador ni confirma una reserva de hora.')+
   form('orgqr-public',hidden('purpose',purpose)+fields,worker?'Registrarme':'Enviar consulta'));
  const f=screen.querySelector('[data-form=orgqr-public]');f.dataset.key=crypto.randomUUID();
  if(!worker){
   f.elements.contact_authorized.required=true;
   const calendar=f.querySelector('#appointment-calendar');refreshCalendar=mountAppointmentCalendar(f,calendar);
   f.elements.kind.addEventListener('change',()=>{calendar.hidden=f.elements.kind.value!=='agenda';f.elements.day.value='';f.elements.slot.value='';if(!calendar.hidden)refreshCalendar();});
  }
 }

 async function managePage(id){
  clearInterval(rosterTimer);rosterSnapshot='';organization=await api('organization-qrs/'+encodeURIComponent(id)+'/');
  const search=form('orgqr-search',input('q','Nombre o RUT','search',params.get('q')||'','maxlength="180"')+
   select('state','Afiliación',[['','Todas'],['active','Activas'],['pending','Pendientes'],['inactive','Inactivas / rechazadas']],params.get('state')||'')+
   input('desde','Fecha desde','date',params.get('desde')||'','')+input('hasta','Fecha hasta','date',params.get('hasta')||'',''),'Buscar trabajadores');
  const roster = params.get('vista')==='trabajadores';
  const header=head(roster?'Trabajadores registrados':'Códigos QR de atención',organization.name)+
   '<div class="actions">'+link('Volver',ctx.session.union?'sindicato.html':organization.type==='sindicato'?'sindicatos.html':'convenios.html')+'</div>'+
   panel('Resumen del convenio','<dl class="organization-summary">'+
    [['Organización',organization.name],['Código',organization.code],['Estado',organization.available?'Vigente':'Sin vigencia'],
     ['Vigencia',[organization.starts_on,organization.ends_on].filter(Boolean).join(' a ')||'Sin fechas definidas'],
     ['Beneficios vigentes',organization.benefit_count]].filter(([,value])=>value!=null)
     .map(([label,value])=>'<div><dt>'+esc(label)+'</dt><dd>'+esc(value)+'</dd></div>').join('')+'</dl>'+
    '<div class="actions">'+(organization.available&&(organization.can_edit_workers||organization.can_register_union_workers)?action('Registrar trabajador','register',id):'')+
    (organization.can_view_benefits?link('Consultar beneficios','beneficios.html?agreement='+id):'')+
    '<a class="button soft" href="#qr-cards">Ver códigos QR</a><a class="button soft" href="#organization-workers">Ver trabajadores</a></div>')+
   (!organization.available?note('La organización no está habilitada o vigente. Ninguno de estos QR admite envíos mientras continúe en ese estado.'):'');
  const qrCards='<div class="organization-qr-cards" id="qr-cards">'+organization.codes.map(c=>panel(c.purpose==='worker'?'Registrar trabajadores':'Consultas del convenio',
    '<p><strong>'+esc(organization.name)+'</strong></p>'+note(c.purpose==='worker'?'Registra una solicitud de trabajador asociado. La validación de pertenencia y el acceso se revisan por separado.':'Permite consultar información y enviar preguntas sin crear una cuenta ni habilitar beneficios.')+
    '<p>'+esc(!c.enabled?'QR revocado':organization.available?'QR vigente':'Pendiente de habilitación de la organización')+'</p>'+
    (c.url?'<img class="organization-qr-image" width="256" height="256" src="'+esc(c.image_url)+'" alt="QR '+esc(c.title)+'">'+
     '<div class="actions">'+action(c.purpose==='worker'?'Mostrar QR de registro de trabajadores':'Mostrar QR de consultas','show',c.purpose)+
     action('Ampliar','zoom',c.purpose)+
     '<a class="button soft" href="'+esc(c.image_url+'&download=1')+'" download>Descargar QR</a>'+action('Copiar enlace','copy',c.purpose)+action('Imprimir QR','print',c.purpose)+'</div>':note('Configura una dirección HTTPS pública para generar el QR.'))+
    (organization.can_manage?'<div class="actions">'+action('Regenerar QR','change',c.purpose+':rotate')+action(c.enabled?'Revocar QR':'Volver a habilitar','change',c.purpose+(c.enabled?':revoke':':enable'))+'</div>':''))).join('')+'</div>';
  const workers='<div id="organization-workers">'+panel('Trabajadores registrados',search+
    link('Limpiar filtros','qr_organizacion.html?organizacion='+id+'&vista=trabajadores#organization-workers')+
    '<div data-org-roster aria-live="polite"></div><p data-org-update role="status">Consultando el servidor…</p>'+action('Actualizar registros','refresh',id))+'</div>';
  screen.innerHTML=header+(roster?workers+qrCards:qrCards+workers)+
   (organization.can_read_inquiries?link('Consultar solicitudes y preguntas','solicitudes.html?agreement='+id):'');
  await refreshRoster();
  rosterTimer=setInterval(()=>{if(!document.hidden&&!document.getElementById('app-dialog').open)refreshRoster();},20000);
  if(location.hash==='#organization-workers')document.getElementById('organization-workers').scrollIntoView();
 }
 async function refreshRoster(){
  if(rosterBusy||!organization||!screen.querySelector('[data-org-roster]'))return;
  rosterBusy=true;
  try{
   const query=new URLSearchParams([...params].filter(([key])=>['q','state','desde','hasta'].includes(key)));
   query.set('page',params.get('pagina')||'1');
   const data=await api('organization-qrs/'+organization.id+'/registrations/?'+query);
   const target=screen.querySelector('[data-org-roster]');if(!target)return;
   const snapshot=JSON.stringify(data);
   if(snapshot===rosterSnapshot){
    screen.querySelector('[data-org-update]').textContent='Actualización automática cada 20 segundos.';
    return;
   }
   rosterSnapshot=snapshot;
   const workerPage=number=>{
    const next=new URLSearchParams(params);next.set('pagina',String(number));
    return 'qr_organizacion.html?'+next+'#organization-workers';
   };
   target.innerHTML='<div class="stats">'+[['Registrados',data.counts.total],['Pendientes',data.counts.pending],['Validados',data.counts.active],['Inactivos / rechazados',data.counts.inactive]].map(([label,count])=>'<article class="stat"><div>'+label+'</div><strong>'+count+'</strong></article>').join('')+'</div>'+
    table(['Trabajador','RUT','Correo y teléfono','Calidad','Afiliación','Cuenta','Origen','Fecha de registro','Acciones'],
     data.results.map(r=>[esc(r.name),esc(r.rut),esc(r.email||'—')+'<br>'+esc(r.phone||'—'),r.role==='carga'?'Carga familiar':'Titular',
      esc(stateLabel(r.state)),esc(r.account_state),esc(r.origin_label),esc(date(r.created_at)),action('Ver ficha','detail',r.id)]))+
    (data.previous?link('Anterior',workerPage(Number(params.get('pagina')||1)-1)):'')+
    (data.next?link('Ver más registros',workerPage(Number(params.get('pagina')||1)+1)):'');
   target._rows=data.results;
   screen.querySelector('[data-org-update]').textContent='Actualización automática cada 20 segundos.';
  }catch(e){const note=screen.querySelector('[data-org-update]');if(note)note.textContent=e.message+' Puedes pulsar Actualizar registros.';}
  finally{rosterBusy=false;}
 }
 function showCode(purpose, enlarged=false){
  const c=organization.codes.find(c=>c.purpose===purpose);if(!c?.url)throw new Error('El QR no tiene dirección pública.');
  dialog(c.title,'<div class="organization-qr-dialog'+(enlarged?' enlarged':'')+'"><h3>'+esc(organization.name)+'</h3><img class="organization-qr-image" src="'+esc(c.image_url)+'" alt="'+esc(c.title)+'"><p class="qr-url">'+esc(c.url)+'</p><div class="actions">'+action('Ampliar QR','enlarge',purpose)+action('Copiar enlace','copy',purpose)+action('Imprimir QR','print',purpose)+'</div></div>');
 }
 function printCode(purpose){
  const c=organization.codes.find(c=>c.purpose===purpose);if(!c?.url)return;
  const win=window.open('about:blank','_blank');if(!win)throw new Error('Permite abrir la ventana de impresión.');
  win.document.write('<!doctype html><html lang="es"><title>'+esc(c.title)+'</title><style>body{font:20px sans-serif;text-align:center;padding:24px}img{width:420px;max-width:90%}p{overflow-wrap:anywhere}</style><h1>'+esc(c.title)+'</h1><h2>'+esc(organization.name)+'</h2><img alt="QR" src="'+esc(c.image_url)+'"><p>'+esc(c.url)+'</p><p>La pertenencia requiere validación. Este QR no concede acceso a información privada.</p></html>');
  win.addEventListener('load',()=>win.print(),{once:true});
  win.document.close();
 }
 async function click(b){
  const id=b.dataset.id;
  if(b.dataset.op==='orgqr-show')showCode(id);
  else if(b.dataset.op==='orgqr-zoom')showCode(id,true);
  else if(b.dataset.op==='orgqr-enlarge')document.querySelector('.organization-qr-dialog').classList.toggle('enlarged');
  else if(b.dataset.op==='orgqr-print')printCode(id);
  else if(b.dataset.op==='orgqr-copy'){await navigator.clipboard.writeText(organization.codes.find(c=>c.purpose===id).url);message('Enlace copiado.');}
  else if(b.dataset.op==='orgqr-refresh')await refreshRoster();
  else if(b.dataset.op==='orgqr-register'){
   dialog('Registrar trabajador',form('orgqr-register',input('name','Nombre completo')+input('rut','RUT')+
    input('email','Correo','email')+input('phone','Teléfono','tel')+
    select('role','Calidad',organization.allow_dependents?[['titular','Titular'],['carga','Carga familiar']]:[['titular','Titular']])+
    check('privacy','Confirmo que el trabajador autorizó el registro de estos datos.') ,'Registrar trabajador'));
   document.querySelector('[data-form=orgqr-register]').dataset.key=crypto.randomUUID();
  }else if(b.dataset.op==='orgqr-affiliation'){
   const [id,operation]=b.dataset.id.split(':');
   const label={verify:'Validar trabajador',disable:'Desactivar afiliación',reactivate:'Reactivar afiliación'}[operation];
   document.getElementById('app-dialog').close();
   dialog(label,form('orgqr-affiliation',hidden('id',id)+hidden('operation',operation)+
    (operation==='disable'?'':select('method','Método',[['presencial','Presencial'],['nomina','Nómina autorizada'],['responsable','Responsable del convenio']])+
     check('identity_verified','Verifiqué la identidad y autorización del titular.'))+
    input('note','Referencia de verificación','text','','required minlength="5" maxlength="240"'),label));
  }
  else if(b.dataset.op==='orgqr-detail'){
   const r=screen.querySelector('[data-org-roster]')._rows.find(r=>String(r.id)===id);
   const operation={pendiente:'verify',aprobada:'disable',inactiva:'reactivate'}[r.state];
   let actions=organization.can_edit_workers&&operation?action(
    {verify:'Validar trabajador',disable:'Desactivar afiliación',reactivate:'Reactivar afiliación'}[operation],
    'affiliation',r.id+':'+operation):'';
   if(organization.can_manage_union_workers&&r.state==='pending'&&r.accepted_at)
    actions+=action('Validar trabajador','affiliation',r.id+':verify');
   if(organization.can_manage_union_workers&&r.state==='active')
    actions+=action('Desactivar afiliación','affiliation',r.id+':disable');
   if(organization.can_manage_union_workers&&r.state==='inactive')
    actions+=action('Reactivar con invitación','affiliation',r.id+':reactivate');
   if(organization.can_manage_union_workers&&r.state==='pending'&&!r.accepted_at)
    actions+=action('Preparar invitación','affiliation',r.id+':reactivate');
   dialog('Registro de trabajador', '<p><strong>'+esc(r.name)+'</strong></p><p>'+esc(r.rut)+' · '+esc(r.email)+' · '+esc(r.phone)+'</p>'+note(stateLabel(r.state)+' · '+r.origin_label)+
    (r.client?link('Abrir ficha de cliente','detalle_cliente.html?cliente='+r.client):'')+actions);
  }else if(b.dataset.op==='orgqr-change'){
   const [purpose,operation]=id.split(':');dialog('Administrar QR',note('El cambio afecta solo al QR seleccionado. Regenerar invalida el enlace anterior; revocar impide nuevos envíos.')+
    form('orgqr-change',hidden('purpose',purpose)+hidden('operation',operation)+check('confirmed','Confirmo el cambio de este código QR.'),'Aplicar cambio'));
  }
 }
 async function submit(event){
  const f=event.target;event.preventDefault();if(f.dataset.busy==='1'||!f.reportValidity())return;
  const data=Object.fromEntries(new FormData(f)),button=f.querySelector('[type=submit]'),feedback=f.querySelector('.form-feedback');
  f.dataset.busy='1';f.setAttribute('aria-busy','true');button.disabled=true;feedback.textContent='Validando y guardando en el servidor…';
  try{
   if(f.dataset.form==='orgqr-search'){
    const query=new URLSearchParams({organizacion:String(organization.id),vista:'trabajadores'});
    for(const [key,value] of Object.entries(data))if(value.trim())query.set(key,value.trim());
    location.href='qr_organizacion.html?'+query+'#organization-workers';return;
   }
   if(f.dataset.form==='orgqr-register'){
    if(!data.privacy)throw new Error('Confirma la autorización para registrar los datos.');
    const union=organization.type==='sindicato';
    const route=union?(organization.can_manage_union_workers?'unions/'+organization.union_id+'/workers/register/':'union/workers/'):
     'organization-qrs/'+organization.id+'/registrations/';
    const result=await api(route,{method:'POST',body:{...data,privacy:true,privacy_version:organization.privacy_version,idempotency_key:f.dataset.key}});
    document.getElementById('app-dialog').close();
    await refreshRoster();
    if(result.invitation) ctx.invitationDialog(result.invitation);
    message('Trabajador registrado. Su afiliación queda pendiente de validación.');return;
   }
   if(f.dataset.form==='orgqr-affiliation'){
    const {id,operation,note:reference,method,identity_verified}=data;
    if(operation!=='disable'&&!identity_verified)throw new Error('Confirma la verificación del titular.');
    let result;
    if(organization.type==='sindicato'){
     result=await api('union/workers/'+id+'/',{method:'POST',body:{
      action:{verify:'review',disable:'disable',reactivate:'reissue'}[operation],note:reference}});
    }else{
     const route=operation==='verify'?'agreement-verifications/'+id+'/':
      'organization-qrs/'+organization.id+'/registrations/'+id+'/';
     result=await api(route,{method:'POST',body:{action:operation,approved:true,method,note:reference,identity_verified:!!identity_verified}});
    }
    document.getElementById('app-dialog').close();
    await refreshRoster();
    if(result.invitation)ctx.invitationDialog(result.invitation);
    message('Afiliación actualizada.');return;
   }
   if(f.dataset.form==='orgqr-change'){
    if(!data.confirmed)throw new Error('Confirma el cambio antes de continuar.');
    await api('organization-qrs/'+organization.id+'/',{method:'POST',body:{...data,confirmed:true}});document.getElementById('app-dialog').close();await managePage(organization.id);return;
   }
   const purpose=data.purpose;delete data.purpose;data.privacy=!!data.privacy;data.contact_authorized=!!data.contact_authorized;
   data.idempotency_key=f.dataset.key;
   if(data.kind==='agenda'&&(!data.day||!data.slot))throw new Error('Selecciona una fecha y una hora disponibles.');
   if(purpose==='inquiry'){data.day=data.day||null;data.slot=data.slot||null;}
   const result=await api(endpoint(purpose,params.get('qr')),{method:'POST',body:data});
   screen.innerHTML=head(purpose==='worker'?'Registro de trabajador recibido':'Consulta recibida',result.organization)+note(result.detail)+'<p class="qr-url">Referencia privada: '+esc(result.reference)+'</p>'+link('Volver al inicio','index.html');
   try{const channel=new BroadcastChannel('amaru-organization-updates');channel.postMessage('refresh');channel.close();}catch{}
  }catch(e){feedback.textContent=e.message;if(data.kind==='agenda'&&e.status===409&&refreshCalendar)await refreshCalendar();}
  finally{delete f.dataset.busy;f.removeAttribute('aria-busy');button.disabled=false;}
 }
 function watchUnion(data,render){
  clearInterval(unionTimer);let snapshot=JSON.stringify(data);
  unionTimer=setInterval(async()=>{if(document.hidden||document.getElementById('app-dialog').open)return;try{const next=await api('union/portal/');if(JSON.stringify(next)!==snapshot){snapshot=JSON.stringify(next);await render();}}catch{}},10000);
 }
 try{const channel=new BroadcastChannel('amaru-organization-updates');channel.onmessage=()=>refreshRoster();}catch{}
 return {publicPage,managePage,click,submit,watchUnion};
};
