/* QR de organización. Toda vinculación y validación se persiste en Django. */
window.AmaruOrganizationQR=function(ctx){
 'use strict';
 const {api,esc,head,panel,input,select,check,form,table,btn,link,note,dialog,message,screen,params,date,mountAppointmentCalendar}=ctx;
 let organization=null,rosterTimer=null,unionTimer=null,refreshCalendar=null,rosterBusy=false;
 const endpoint=(purpose,token)=>'organization-qr/'+purpose+'/'+encodeURIComponent(token)+'/';
 const hidden=(name,value)=>'<input type="hidden" name="'+name+'" value="'+esc(value)+'">';
 const stateLabel=s=>({pending:'Pendiente',active:'Activa',inactive:'Inactiva',pendiente:'Pendiente',aprobada:'Aprobada',rechazada:'Rechazada'}[s]||s);
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
  clearInterval(rosterTimer);organization=await api('organization-qrs/'+encodeURIComponent(id)+'/');
  screen.innerHTML=head('Códigos QR de atención',organization.name)+
   '<div class="actions">'+link('Volver',ctx.session.union?'sindicato.html':organization.type==='sindicato'?'sindicatos.html':'convenios.html')+'</div>'+
   (!organization.available?note('La organización no está habilitada o vigente. Ninguno de estos QR admite envíos mientras continúe en ese estado.'):'')+
   '<div class="organization-qr-cards">'+organization.codes.map(c=>panel(c.purpose==='worker'?'Registrar trabajadores':'Consultas y beneficios',
    '<p><strong>'+esc(organization.name)+'</strong></p>'+note(c.purpose==='worker'?'Registra una solicitud de trabajador asociado. La validación de pertenencia y el acceso se revisan por separado.':'Permite consultar información y enviar preguntas sin crear una cuenta ni habilitar beneficios.')+
    '<p>'+esc(!c.enabled?'QR revocado':organization.available?'QR vigente':'Pendiente de habilitación de la organización')+'</p>'+
    (c.url?'<img class="organization-qr-image" width="256" height="256" src="'+esc(c.image_url)+'" alt="QR '+esc(c.title)+'">'+
     '<div class="actions">'+action(c.purpose==='worker'?'Mostrar QR de registro de trabajadores':'Mostrar QR de consultas','show',c.purpose)+
     '<a class="button soft" href="'+esc(c.image_url+'&download=1')+'" download>Descargar QR</a>'+action('Copiar enlace','copy',c.purpose)+action('Imprimir QR','print',c.purpose)+'</div>':note('Configura una dirección HTTPS pública para generar el QR.'))+
    (organization.can_manage?'<div class="actions">'+action('Regenerar QR','change',c.purpose+':rotate')+action(c.enabled?'Revocar QR':'Volver a habilitar','change',c.purpose+(c.enabled?':revoke':':enable'))+'</div>':''))).join('')+'</div>'+
   panel('Trabajadores registrados','<div data-org-roster aria-live="polite"></div><p data-org-update role="status">Consultando el servidor…</p>'+action('Actualizar registros','refresh',id))+
   (organization.can_read_inquiries?link('Consultar solicitudes y preguntas','solicitudes.html?agreement='+id):'');
  await refreshRoster();
  rosterTimer=setInterval(()=>{if(!document.hidden&&!document.getElementById('app-dialog').open)refreshRoster();},10000);
 }
 async function refreshRoster(){
  if(rosterBusy||!organization||!screen.querySelector('[data-org-roster]'))return;
  rosterBusy=true;
  try{
   const data=await api('organization-qrs/'+organization.id+'/registrations/?page='+(params.get('pagina')||1));
   const target=screen.querySelector('[data-org-roster]');if(!target)return;
   target.innerHTML='<div class="stats">'+[['Registrados',data.counts.total],['Pendientes',data.counts.pending],['Validados',data.counts.active],['Inactivos / rechazados',data.counts.inactive]].map(([label,count])=>'<article class="stat"><div>'+label+'</div><strong>'+count+'</strong></article>').join('')+'</div>'+
    table(['Trabajador','RUT','Calidad','Estado','Origen','Recepción','Acciones'],data.results.map(r=>[esc(r.name),esc(r.rut),esc(r.role),esc(stateLabel(r.state)),esc(r.origin_label),esc(date(r.created_at)),action('Ver registro','detail',r.id)]))+
    (data.previous?link('Anterior','qr_organizacion.html?organizacion='+organization.id+'&pagina='+(Number(params.get('pagina')||1)-1)):'')+(data.next?link('Ver más registros','qr_organizacion.html?organizacion='+organization.id+'&pagina='+(Number(params.get('pagina')||1)+1)):'');
   target._rows=data.results;
   screen.querySelector('[data-org-update]').textContent='Datos consultados en MariaDB. Actualización automática cada 10 segundos.';
  }catch(e){const note=screen.querySelector('[data-org-update]');if(note)note.textContent=e.message+' Puedes pulsar Actualizar registros.';}
  finally{rosterBusy=false;}
 }
 function showCode(purpose){
  const c=organization.codes.find(c=>c.purpose===purpose);if(!c?.url)throw new Error('El QR no tiene dirección pública.');
  dialog(c.title,'<div class="organization-qr-dialog"><h3>'+esc(organization.name)+'</h3><img class="organization-qr-image" src="'+esc(c.image_url)+'" alt="'+esc(c.title)+'"><p class="qr-url">'+esc(c.url)+'</p><div class="actions">'+action('Ampliar QR','enlarge',purpose)+action('Copiar enlace','copy',purpose)+action('Imprimir QR','print',purpose)+'</div></div>');
 }
 function printCode(purpose){
  const c=organization.codes.find(c=>c.purpose===purpose);if(!c?.url)return;
  const win=window.open('about:blank','_blank');if(!win)throw new Error('Permite abrir la ventana de impresión.');
  win.document.write('<!doctype html><html lang="es"><title>'+esc(c.title)+'</title><style>body{font:20px sans-serif;text-align:center;padding:24px}img{width:420px;max-width:90%}p{overflow-wrap:anywhere}</style><h1>'+esc(c.title)+'</h1><h2>'+esc(organization.name)+'</h2><img alt="QR" src="'+esc(c.image_url)+'"><p>'+esc(c.url)+'</p><p>La pertenencia requiere validación. Este QR no concede acceso a información privada.</p></html>');
  win.document.close();win.onload=()=>win.print();
 }
 async function click(b){
  const id=b.dataset.id;
  if(b.dataset.op==='orgqr-show')showCode(id);
  else if(b.dataset.op==='orgqr-enlarge')document.querySelector('.organization-qr-dialog').classList.toggle('enlarged');
  else if(b.dataset.op==='orgqr-print')printCode(id);
  else if(b.dataset.op==='orgqr-copy'){await navigator.clipboard.writeText(organization.codes.find(c=>c.purpose===id).url);message('Enlace copiado.');}
  else if(b.dataset.op==='orgqr-refresh')await refreshRoster();
  else if(b.dataset.op==='orgqr-detail'){
   const r=screen.querySelector('[data-org-roster]')._rows.find(r=>String(r.id)===id);
   dialog('Registro de trabajador', '<p><strong>'+esc(r.name)+'</strong></p><p>'+esc(r.rut)+' · '+esc(r.email)+' · '+esc(r.phone)+'</p>'+note(stateLabel(r.state)+' · '+r.origin_label)+
    (organization.can_read_inquiries?(organization.type==='sindicato'?link('Revisar en Sindicatos','sindicatos.html'):link('Revisar validación','solicitudes.html?agreement='+organization.id+'&verification=pendiente')):''));
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
