/* Interfaz comercial académica. Django calcula importes, permisos y existencias. */
window.AmaruCommercial=function(ctx){
 'use strict';
 const {api,esc,head,panel,input,select,area,check,form,table,btn,link,note,currency,date,dialog,close,message,has,session,screen,params,pages,list}=ctx;
 const hidden=(name,value)=>`<input type="hidden" name="${name}" value="${esc(value)}">`;
 const paymentStates=[['','Todos'],['pending','Pendiente de pago'],['submitted','Comprobante enviado'],['review','En revisión'],['approved','Pago aprobado'],['rejected','Pago rechazado'],['cancelled','Cancelado']];
 const benefitTypes=[['percent','Descuento porcentual'],['fixed','Descuento fijo'],['price','Precio preferencial unitario'],['catalog','Catálogo exclusivo'],['mining','Lentes mineros'],['family','Cargas familiares'],['evaluation','Evaluación visual'],['contribution','Aporte de organización'],['other','Otro']];
 const tabs=[['resumen','Resumen'],['productos','Productos y variantes'],['brands','Marcas'],['product-models','Modelos'],['stock-categories','Categorías'],['suppliers','Proveedores'],['entry','Entradas'],['exit','Salidas'],['adjustment','Ajustes'],['historial','Kardex'],['alertas','Alertas'],['reportes','Reportes']];
 const managed={brands:['Marcas','brand'], 'product-models':['Modelos','productmodel'], 'stock-categories':['Categorías','stockcategory'],suppliers:['Proveedores','supplier']};
 const chosen=(key)=>params.get(key)||'';
 let currentPayment=null;
 const checkoutSteps=stage=>'<ol class="checkout-steps" aria-label="Etapas de compra">'+['Mi carrito','Transferencia bancaria','Envío del comprobante'].map((label,index)=>'<li '+(index+1===stage?'aria-current="step"':'')+'><span>'+ (index+1)+'</span>'+label+'</li>').join('')+'</ol>';
 async function checkoutPage(id){await paymentDetail(id,false,true);}
 async function myPayments(){
  const data=await api('payments/');
  return panel('Mis compras y pagos',note('El comprobante se revisa antes de aprobar el pago. Puedes retomar aquí un pago iniciado desde el carrito.')+
   table(['Folio / Productos','Total','Estado del pedido','Estado del pago','Observaciones','Acciones'],data.results.map(p=>[
    esc(p.folio)+'<br>'+p.items.map(i=>esc(i.name)+' × '+i.quantity).join('<br>'),currency(p.amount),esc(p.order?p.order.folio+' · '+p.order.state:'Pendiente de aprobación del pago'),esc(p.state_label),esc(p.history.at(-1)?.observations||'Sin observaciones'),link('Ver pago y comprobantes','carrito.html?pago='+p.id)]))+
   (data.next?link('Ver todos mis pagos','pagos.html'):''));
 }
 const options=rows=>rows.map(r=>[r.id,r.name]);
 const actionBar=body=>'<div class="actions commercial-actions">'+body+'</div>';
 const controls=(brands,categories,suppliers)=>form('commerce-stock-search',hidden('vista',chosen('vista')||'productos')+
  input('q','Buscar por ID, SKU, código de barras, nombre, marca, modelo, categoría o proveedor','search',chosen('q'),'maxlength="180" autocomplete="off"')+
  select('stock','Disponibilidad',[['','Todas'],['available','Disponible'],['low','Stock bajo'],['empty','Agotado']],chosen('stock'))+
  select('active','Estado',[['','Todos'],['true','Activo'],['false','Inactivo']],chosen('active'))+
  select('brand','Marca',[['','Todas'],...options(brands)],chosen('brand'))+
  select('category_id','Categoría',[['','Todas'],...options(categories)],chosen('category_id'))+
  select('supplier','Proveedor',[['','Todos'],...options(suppliers)],chosen('supplier')),'Buscar');

 async function benefitsPage(own=false){
  const data=await api(own?'my-benefits/':'benefits/?'+new URLSearchParams([...params].filter(([k])=>['agreement','page'].includes(k))));
  const rows=own?data:data.results;
  screen.innerHTML=head(own?'Mis beneficios':'Beneficios del convenio',own?'Condiciones disponibles según tu afiliación y la vigencia del convenio.':'Configura las condiciones autorizadas de cada organización.')+
   (own?'':actionBar(link('Volver a convenios','convenios.html')+(has('add_agreementbenefit')?btn('Crear beneficio','commerce-benefit-new',chosen('agreement')):'')))+
   note('Los descuentos monetarios se calculan en el servidor. Se utiliza el beneficio de mayor descuento, sin acumulación.')+
   '<div class="cards">'+rows.map(b=>panel(b.name,`<p>${esc(b.agreement_name)}</p><p>${esc(b.description)}</p><p>${esc(benefitTypes.find(t=>t[0]===b.kind)?.[1])} ${b.value!=null?esc(b.kind==='percent'?b.value+' %':currency(b.value)):''}</p><p>Vigencia: ${esc(b.starts_on||'Sin inicio')} a ${esc(b.ends_on||'Sin término')}</p><p>${esc(b.conditions)}</p>`+
    (own?'':`<p>${b.active?'Activo':'Inactivo'}</p>`+(has('change_agreementbenefit')?btn('Editar beneficio','commerce-benefit-edit',b.id):'')))).join('')+'</div>'+
   (!rows.length?note('No hay beneficios disponibles para esta vista.'):'')+(own?'':pages(data));
 }
 async function benefitForm(id,agreement){
  const [b,agreements,categories,products]=await Promise.all([id?api('benefits/'+id+'/'):Promise.resolve({agreement}),api('agreements/'),api('stock-categories/'),api('catalog-management/')]);
  dialog(id?'Editar beneficio':'Crear beneficio',note('Usa condiciones aprobadas por la óptica. Los datos de la demostración son ficticios.')+
   form('commerce-benefit',hidden('id',id||'')+input('name','Nombre','text',b.name)+select('agreement','Convenio',options(agreements.results),b.agreement)+
    area('description','Descripción',b.description)+select('kind','Tipo de beneficio',benefitTypes,b.kind)+input('value','Porcentaje o monto CLP','number',b.value??'','min="0" max="999999999" step="0.01"')+
    select('role','Beneficiarios',[['all','Titular y cargas'],['titular','Titular'],['carga','Carga familiar']],b.role||'all')+
    select('category','Categoría aplicable',[['','Todas'],...options(categories.results)],b.category)+
    '<div class="field wide"><label for="benefit-products">Productos aplicables (sin selección, todos)</label><select id="benefit-products" name="products" multiple>'+products.results.map(p=>'<option value="'+p.id+'" '+(b.products?.includes(p.id)?'selected':'')+'>'+esc(p.name)+'</option>').join('')+'</select></div>'+
    input('starts_on','Fecha de inicio','date',b.starts_on,'')+input('ends_on','Fecha de término','date',b.ends_on,'')+area('conditions','Condiciones de utilización',b.conditions)+
    select('active','Estado',[['false','Inactivo'],['true','Activo']],String(b.active??false))));
 }

 async function inventoryPage(){
  const view=chosen('vista')||'resumen';
  screen.innerHTML=head('Inventario','Administra existencias, variantes y movimientos registrados.')+
   '<nav class="actions inventory-tabs" aria-label="Secciones de inventario">'+tabs.map(([v,l])=>`<a class="button soft" ${view===v?'aria-current="page"':''} href="inventario.html?vista=${v}">${l}</a>`).join('')+'</nav>';
  if(managed[view]){
   const [title,model]=managed[view],data=await list(view+'/');
   screen.innerHTML+=panel(title,(has('add_'+model)?btn('Crear '+title.toLowerCase(),'commerce-master-new',view):'')+
    table(['Nombre','Detalle','Estado','Acciones'],data.results.map(r=>[esc(r.name),esc(r.brand_name||r.contact||r.rut||''),r.active?'Activo':'Inactivo',has('change_'+model)?btn('Editar','commerce-master-edit',view+':'+r.id):''])))+pages(data);return;
  }
  if(view==='historial'){
   const query=new URLSearchParams([...params].filter(([k])=>['item','kind','desde','hasta'].includes(k)));
   const data=await list('stock-movements/?'+query);
   screen.innerHTML+=panel('Historial de movimientos',form('commerce-movement-search',input('item','ID de artículo','number',chosen('item'),'min="1"')+
    select('kind','Movimiento',[['','Todos'],['entry','Entrada'],['exit','Salida'],['adjustment','Ajuste']],chosen('kind'))+input('desde','Desde','date',chosen('desde'),'')+input('hasta','Hasta','date',chosen('hasta'),''),'Buscar')+
    table(['Fecha','Producto / SKU','Movimiento','Entrada','Salida','Stock anterior','Stock final','Referencia','Responsable','Motivo'],data.results.map(m=>[
     esc(date(m.created_at)),esc(m.name)+'<br>'+esc(m.sku),esc({entry:'Entrada',exit:'Salida',adjustment:'Ajuste'}[m.kind]||m.kind),m.delta>0?m.delta:'—',m.delta<0?-m.delta:'—',m.before,m.after,esc(m.reference),esc(m.actor_name),esc(m.reason)])))+pages(data);return;
  }
  if(view==='resumen'){
   const [s,recent]=await Promise.all([api('stock/summary/'),api('stock-movements/')]);
   const values=[['Productos',s.products],['Unidades físicas',s.physical],['Disponibles',s.available],['Reservadas',s.reserved],['Stock bajo',s.low],['Agotados',s.empty]];
   if(s.value!==undefined)values.push(['Valor a costo',currency(s.value)]);
   screen.innerHTML+='<div class="stats">'+values.map(([l,n])=>`<article class="stat"><div>${l}</div><strong>${esc(n)}</strong></article>`).join('')+'</div>'+
    panel('Movimientos recientes',table(['Fecha','Producto','Tipo','Cantidad','Stock final'],recent.results.slice(0,8).map(m=>[esc(date(m.created_at)),esc(m.name),esc({entry:'Entrada',exit:'Salida',adjustment:'Ajuste'}[m.kind]||m.kind),m.delta,m.after])))+
    note('Las reservas vencidas dejan de bloquear existencias. Las aprobadas se conservan hasta entrega o revisión administrativa.');return;
  }
  if(view==='reportes'){
   screen.innerHTML+=panel('Reportes de existencias',link('Descargar inventario CSV','/api/stock/report/')+link('Consultar Kardex','inventario.html?vista=historial')+note('El CSV muestra existencias físicas, reservadas, disponibles y mínimas.'));return;
  }
  const query=new URLSearchParams([...params].filter(([k])=>['q','stock','active','brand','category_id','supplier'].includes(k)));
  if(view==='alertas'&&!query.get('stock'))query.set('stock','low');
  const [data,brands,categories,suppliers]=await Promise.all([list('stock/?'+query),api('brands/'),api('stock-categories/'),api('suppliers/')]);
  screen.innerHTML+=panel('Buscar existencias',controls(brands.results,categories.results,suppliers.results)+(view==='alertas'?link('Ver agotados','inventario.html?vista=alertas&stock=empty'):'')+link('Limpiar filtros','inventario.html?vista='+view));
  if(view==='productos')screen.innerHTML+=actionBar(link('Administrar catálogo','catalogo.html?gestion=1')+(has('add_productvariant')?btn('Crear variante inventariable','commerce-variant-new'):''));
  const canMove=has('add_stockmovement');
  screen.innerHTML+=panel('Existencias',table(['Producto / SKU / Código','Marca / Modelo','Categoría / Proveedor','Físico','Reservado','Disponible','Mínimo','Estado','Acciones'],data.results.map(r=>[
   esc(r.name)+'<br><small>'+esc(r.sku||'Artículo histórico')+' · '+esc(r.barcode||'Sin código')+'</small>',
   esc([r.brand_name,r.model_name].filter(Boolean).join(' · ')),esc([r.category_name,r.supplier_name].filter(Boolean).join(' · ')),r.quantity,r.reserved,r.available,r.minimum,
   !r.active?'Inactivo':r.available===0?'Agotado':r.available<=r.minimum?'Stock bajo':'Disponible',
   actionBar((canMove?btn(['entry','exit','adjustment'].includes(view)?{entry:'Registrar entrada',exit:'Registrar salida',adjustment:'Ajustar stock'}[view]:'Registrar movimiento','commerce-move',r.id+':'+view):'')+
    (has('change_inventory')?btn('Configurar','commerce-stock-config',r.id):'')+
    (r.variant?link('Imprimir etiqueta','/api/stock/'+r.id+'/label/'):'')+link('Kardex','inventario.html?vista=historial&item='+r.id))])))+pages(data);
 }
 async function masterForm(route,id){
  const row=id?await api(route+'/'+id+'/'):{};
  let body=hidden('route',route)+hidden('id',id||'')+input('name','Nombre','text',row.name)+select('active','Estado',[['true','Activo'],['false','Inactivo']],String(row.active??true));
  if(route==='product-models'){const brands=await api('brands/');body+=select('brand','Marca',options(brands.results),row.brand);}
  if(route==='suppliers')body+=input('rut','RUT','text',row.rut,'')+input('phone','Teléfono','tel',row.phone,'')+input('email','Correo','email',row.email,'')+input('address','Dirección','text',row.address,'')+input('contact','Contacto','text',row.contact,'')+area('notes','Observaciones',row.notes);
  dialog(id?'Editar registro':'Crear registro',form('commerce-master',body));
 }
 async function variantForm(){
  const [products,suppliers]=await Promise.all([api('catalog-management/'),api('suppliers/')]);
  dialog('Crear variante inventariable',note('La cantidad inicial se registra después en Entradas. El SKU identifica esta variante y el código de barras es un dato independiente.')+
   form('commerce-variant',select('product','Producto',options(products.results))+input('label','Variante (vacío para modelo único)','text','','maxlength="80"')+
    input('sku','SKU de variante','text','','required maxlength="60"')+input('barcode','Código de barras (opcional)','text','','maxlength="80"')+
    select('supplier','Proveedor',[['','Sin proveedor'],...options(suppliers.results)])+input('color','Color','text','','maxlength="80"')+input('size','Tamaño','text','','maxlength="60"')));
 }
 async function movementForm(id,view){
  const [item,suppliers]=await Promise.all([api('stock/'+id+'/'),api('suppliers/')]);
  const kinds=[['entry','Entrada'],['exit','Salida'],['adjustment','Ajuste físico']];
  dialog('Registrar movimiento',note(item.name+' · Físico '+item.quantity+' · Reservado '+item.reserved+' · Disponible '+item.available)+
   form('commerce-move',hidden('id',id)+hidden('operation',crypto.randomUUID())+select('kind','Tipo',kinds,kinds.some(([v])=>v===view)?view:'entry')+
    input('quantity','Cantidad (en ajuste, stock físico contado)','number','','required min="0" max="1000000" step="1"')+
    select('supplier','Proveedor',[['','No corresponde'],...options(suppliers.results)])+
    (has('change_transferconfiguration')?input('unit_cost','Costo unitario CLP (entrada)','number','','min="0" step="1"'):'')+
    input('reference','Documento o pedido de referencia','text','','maxlength="180"')+
    input('reason','Motivo obligatorio','text','','required minlength="5" maxlength="240"')));
 }
 async function stockConfig(id){
  const row=await api('stock/'+id+'/');
  const variant=row.variant?await api('variants/'+row.variant+'/'):null;
  dialog('Configurar existencias',form('commerce-stock-config',hidden('id',id)+input('minimum','Stock mínimo','number',row.minimum,'required min="0" step="1"')+
    input('location','Ubicación física','text',row.location,'maxlength="120"')+area('notes','Observaciones',row.notes)+
    (variant?hidden('variant',variant.id)+input('barcode','Código de barras','text',variant.barcode,'maxlength="80"')+select('active','Estado de variante',[['true','Activa'],['false','Inactiva']],String(variant.active)):'')));
 }
 async function paymentsPage(){
  if(params.get('pago')){await paymentDetail(params.get('pago'),false);return;}
  const query=new URLSearchParams([...params].filter(([k])=>['q','rut','folio','desde','hasta','state'].includes(k)));
  const data=await list('payments/?'+query);
  screen.innerHTML=head(has('view_transferpayment')?'Pagos y comprobantes':'Mis pagos','DEMOSTRACIÓN ACADÉMICA — No realizar transferencias reales.')+
   note('El pago queda disponible cuando la óptica confirma precio, disponibilidad y receta. La fabricación y la entrega mantienen su propio estado.')+
   (has('change_transferconfiguration')?btn('Configurar transferencia y reservas','commerce-bank'):'')+
   panel('Buscar pagos',form('commerce-payment-search',input('q','Nombre o referencia de pago','search',chosen('q'),'')+input('rut','RUT del cliente','text',chosen('rut'),'')+
    input('folio','Folio de cotización','text',chosen('folio'),'')+input('desde','Fecha desde','date',chosen('desde'),'')+input('hasta','Fecha hasta','date',chosen('hasta'),'')+
    select('state','Estado',paymentStates,chosen('state')),'Buscar')+link('Limpiar filtros','pagos.html'))+
   panel('Pagos registrados',table(['Referencia / Cotización','Cliente / RUT','Convenio','Monto esperado','Declarado','Fecha','Estado','Acciones'],data.results.map(p=>[
    esc(p.reference)+'<br>'+esc(p.folio),esc(p.client_name)+'<br>'+esc(p.rut),esc(p.agreement||'Particular'),currency(p.amount),p.vouchers.length?currency(p.vouchers.at(-1).declared_amount):'—',
    esc(date(p.created_at)),esc(p.state_label),link('Ver pago y comprobantes','pagos.html?pago='+p.id)])))+pages(data);
 }
 async function paymentDetail(id,modal=true,checkout=false){
  const p=await api('payments/'+id+'/');currentPayment=p;
  const bankLabels={recipient:'Destinatario',bank:'Banco',account_type:'Tipo de cuenta',account_number:'Número de cuenta',holder_rut:'RUT del titular',email:'Correo'};
  let body=(checkout?checkoutSteps(['pending','rejected'].includes(p.state)?2:3):'')+note('Pago de demostración académica. No realizar transferencias reales.')+
   (checkout?panel('Forma de pago','<p><strong>Transferencia bancaria</strong> · Única modalidad disponible en esta demostración.</p>'):'')+
   `<h3>${esc(p.folio)}</h3><p>${esc(p.client_name)} · <strong data-payment-state>${esc(p.state_label)}</strong></p><p>Referencia: ${esc(p.reference)} ${btn('Copiar referencia','commerce-copy',p.reference)}</p>`+
   `<p>Precio original: ${currency(p.original_amount)} · ${p.benefit.name?'Beneficio '+esc(p.benefit.name)+' · Descuento '+currency(p.benefit.discount):'Sin descuento'} · Total confirmado: <strong>${currency(p.amount)}</strong></p>`+
   btn('Copiar monto exacto','commerce-copy',p.amount)+
   '<dl>'+Object.entries(bankLabels).map(([key,label])=>`<dt>${label}</dt><dd>${esc(p.bank[key]||'—')} ${p.bank[key]?btn('Copiar '+label.toLowerCase(),'commerce-copy',p.bank[key]):''}</dd>`).join('')+'</dl>';
  if(['submitted','review'].includes(p.state))body+=note('Tu comprobante está siendo revisado por Óptica Amaru. Subirlo no significa que el pago esté aprobado.');
  if(p.state==='rejected')body+=note('La óptica solicitó un nuevo comprobante: '+(p.history.at(-1)?.observations||'Revisa el archivo y vuelve a enviarlo.'));
  body+=panel('Productos y pedido',table(['Producto','Variante','Cantidad','Precio unitario'],p.items.map(line=>[esc(line.name),esc(line.variant||'Modelo único'),line.quantity,currency(line.unit_price)]))+
   note(p.order?p.order.folio+' · '+p.order.state:'Pendiente de aprobación del pago y creación de la orden.'));
  body+=panel('Comprobantes',table(['Fecha','Monto declarado','Archivo privado'],p.vouchers.map(v=>[esc(date(v.created_at)),currency(v.declared_amount),link('Descargar comprobante',v.url)])));
  if(!has('view_transferpayment')&&['pending','rejected'].includes(p.state))body+=panel('Subir comprobante de transferencia',form('commerce-voucher',hidden('id',id)+hidden('checkout',checkout?'1':'')+
   input('declared_amount','Monto declarado CLP','number',p.amount,'required min="0" step="1"')+
   input('file','Comprobante JPG, PNG o PDF (máximo 5 MB)','file','','required accept=".jpg,.jpeg,.png,.pdf"')+
   '<div class="voucher-preview wide" data-voucher-preview role="status"></div><p class="wide">Puedes reemplazar el archivo seleccionado antes de enviarlo. Máximo 5 MB.</p>','Enviar comprobante de pago'));
  if(has('change_transferpayment')&&p.vouchers.length&&!['approved','cancelled'].includes(p.state))body+=actionBar(btn('Aprobar pago','commerce-review-choice','approved')+btn('Rechazar pago','commerce-review-choice','rejected')+btn('Solicitar nuevo comprobante','commerce-review-choice','rejected'));
  if(has('change_transferpayment')&&!['approved','cancelled'].includes(p.state))body+=panel('Revisión autorizada',note('Contrasta el comprobante con los movimientos bancarios efectivos. En esta demostración se utiliza evidencia ficticia.')+
   form('commerce-review',hidden('id',id)+hidden('expected_state',p.state)+hidden('voucher',p.vouchers.at(-1)?.id||'')+
    select('state','Decisión',p.vouchers.length?[['review','En revisión'],['approved','Aprobar pago'],['rejected','Rechazar y solicitar nuevo comprobante'],['cancelled','Cancelar pago']]:[['cancelled','Cancelar pago']])+
    area('observations','Observaciones o motivo de rechazo')+check('bank_checked','Contrasté el monto con la evidencia bancaria ficticia.')+
    check('confirmed','Confirmo esta decisión y sus efectos sobre la reserva.'),'Registrar revisión'));
  body+=panel('Historial de revisión',table(['Fecha','Estado','Observaciones'],p.history.map(r=>[esc(date(r.created_at)),esc(paymentStates.find(([key])=>key===r.state)?.[1]||r.state),esc(r.observations)])));
  if(modal)dialog('Pago mediante transferencia bancaria',body);
  else screen.innerHTML=head(checkout?'Finalizar compra':'Pago mediante transferencia bancaria','Transferencia simulada y revisión del comprobante.')+actionBar(link(checkout?'Volver a mi carrito':'Volver a pagos',checkout?'carrito.html':'pagos.html')+link('Mis pedidos','consulta.html'))+body;
 }
 async function bankForm(){
  const data=await api('transfer-configuration/');
  dialog('Configuración de transferencia',note('La demostración muestra un banco y una cuenta inoperativos. La utilización comercial necesita aprobación de la empresa.')+
   form('commerce-bank',input('recipient','Destinatario','text',data.recipient)+input('bank','Banco','text',data.bank)+input('account_type','Tipo de cuenta','text',data.account_type)+
    input('account_number','Número de cuenta','text',data.account_number)+input('holder_rut','RUT del titular','text',data.holder_rut)+input('email','Correo','email',data.email,'')+
    input('reserve_hours','Duración de reserva pendiente (horas)','number',data.reserve_hours,'required min="1" max="720"')));
 }
 async function confirmForm(id){
  const q=await api('quotes/'+id+'/');
  dialog('Confirmar monto y solicitar transferencia',note(q.folio+' · '+q.client_name+' · Total actual '+currency(q.amount))+
   form('commerce-confirm-payment',hidden('id',id)+check('prescription_reviewed','Revisé la receta vigente cuando corresponde.')+
    check('confirmed','Confirmé los precios, disponibilidad, cantidades y condiciones con el cliente.'),'Confirmar monto y reservar existencias'));
 }
 async function submit(event){
  const f=event.target;event.preventDefault();if(f.dataset.busy==='1'||!f.reportValidity())return;
  const data=Object.fromEntries(new FormData(f)),button=f.querySelector('[type=submit]'),feedback=f.querySelector('.form-feedback');
  f.dataset.busy='1';f.setAttribute('aria-busy','true');button.disabled=true;feedback.textContent='Procesando y guardando en el servidor…';
  try{
   const kind=f.dataset.form;
   if(kind==='commerce-stock-search'||kind==='commerce-movement-search'||kind==='commerce-payment-search'){
    const query=new URLSearchParams(Object.entries(data).filter(([,v])=>v!==''));
    if(kind==='commerce-movement-search')query.set('vista','historial');
    location.href=(kind==='commerce-payment-search'?'pagos':'inventario')+'.html?'+query;return;
   }
   if(kind==='commerce-benefit'){
    const id=data.id;delete data.id;data.active=data.active==='true';data.value=data.value===''?null:data.value;data.category=data.category||null;
    data.starts_on=data.starts_on||null;data.ends_on=data.ends_on||null;data.products=new FormData(f).getAll('products').map(Number);
    await api('benefits/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:data});close();await benefitsPage();
   }else if(kind==='commerce-master'){
    const {route,id,...payload}=data;payload.active=payload.active==='true';await api(route+'/'+(id?id+'/':''),{method:id?'PATCH':'POST',body:payload});close();await inventoryPage();
   }else if(kind==='commerce-variant'){
    data.supplier=data.supplier||null;data.barcode=data.barcode||null;await api('variants/',{method:'POST',body:data});close();await inventoryPage();
   }else if(kind==='commerce-stock-config'){
    const {id,variant,barcode,active,...payload}=data;await api('stock/'+id+'/',{method:'PATCH',body:payload});
    if(variant)await api('variants/'+variant+'/',{method:'PATCH',body:{barcode:barcode||null,active:active==='true'}});close();await inventoryPage();
   }else if(kind==='commerce-move'){
    const {id,...payload}=data;payload.quantity=Number(payload.quantity);payload.supplier=payload.supplier||null;if(!payload.unit_cost)delete payload.unit_cost;
    await api('stock/'+id+'/movement/',{method:'POST',body:payload});close();await inventoryPage();
   }else if(kind==='commerce-bank'){
    await api('transfer-configuration/',{method:'PATCH',body:data});close();await paymentsPage();
   }else if(kind==='commerce-confirm-payment'){
    const result=await api('quotes/'+data.id+'/confirm-payment/',{method:'POST',body:{confirmed:!!data.confirmed,prescription_reviewed:!!data.prescription_reviewed}});
    close();location.href='pagos.html?pago='+result.id;return;
   }else if(kind==='commerce-cancel-order'){
    if(!data.confirmed)throw new Error('Confirma la cancelación antes de continuar.');
    await api('orders/'+data.id+'/cancel/',{method:'POST',body:{reason:data.reason,confirmed:true}});
    close();location.reload();return;
   }else if(kind==='commerce-voucher'){
    const file=f.elements.file.files[0];if(file.size>5*1024*1024)throw new Error('El archivo supera el límite de 5 MB.');
    const body=new FormData(f);body.delete('id');body.delete('checkout');await api('payments/'+data.id+'/voucher/',{method:'POST',body});
    await paymentDetail(data.id,false,data.checkout==='1');message('Comprobante recibido. Queda pendiente de revisión.');return;
   }else if(kind==='commerce-review'){
    if(!data.confirmed)throw new Error('Confirma la decisión antes de continuar.');
    delete data.confirmed;if(!data.voucher)delete data.voucher;data.bank_checked=!!data.bank_checked;
    await api('payments/'+data.id+'/review/',{method:'POST',body:data});await paymentDetail(data.id,false);
   }
   message('Operación registrada correctamente.');
  }catch(error){feedback.textContent=error.message;}
  finally{delete f.dataset.busy;f.removeAttribute('aria-busy');button.disabled=false;}
 }
 async function click(button){
  const id=button.dataset.id;
  switch(button.dataset.op){
   case 'commerce-benefit-new':await benefitForm(null,id);break;
   case 'commerce-benefit-edit':await benefitForm(id);break;
   case 'commerce-master-new':await masterForm(id);break;
   case 'commerce-master-edit':{const [route,pk]=id.split(':');await masterForm(route,pk);break;}
   case 'commerce-variant-new':await variantForm();break;
   case 'commerce-stock-config':await stockConfig(id);break;
   case 'commerce-move':{const [pk,view]=id.split(':');await movementForm(pk,view);break;}
   case 'commerce-bank':await bankForm();break;
   case 'commerce-confirm-payment':await confirmForm(id);break;
   case 'commerce-review-choice':{const f=screen.querySelector('[data-form=commerce-review]');f.elements.state.value=id;f.elements.observations.focus();f.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});break;}
   case 'commerce-cancel-order':dialog('Cancelar orden',note('Libera las reservas de la orden. Si existe un pago aprobado, se conserva su historial y la administración debe revisar su devolución.')+
    form('commerce-cancel-order',hidden('id',id)+input('reason','Motivo de cancelación','text','','required minlength="5" maxlength="240"')+check('confirmed','Confirmo la cancelación de esta orden.'),'Cancelar orden'));break;
   case 'commerce-copy':await navigator.clipboard.writeText(id);message('Dato copiado.');break;
  }
 }
 document.addEventListener('change',event=>{
  const field=event.target;
  if(!field.matches('[data-form="commerce-voucher"] input[type=file]'))return;
  const preview=field.form.querySelector('[data-voucher-preview]'),file=field.files[0];preview.replaceChildren();
  if(!file)return;
  preview.textContent=file.name+' · '+(file.size/1024).toFixed(0)+' KB';
  if(['image/jpeg','image/png'].includes(file.type)&&file.size<=5*1024*1024){const img=document.createElement('img');img.alt='Vista previa del comprobante seleccionado';img.src=URL.createObjectURL(file);img.onload=()=>URL.revokeObjectURL(img.src);preview.append(img);}
 });
 return {benefitsPage,inventoryPage,paymentsPage,checkoutPage,checkoutSteps,myPayments,submit,click};
};
