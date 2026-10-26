/* Carga independiente: los errores de un recurso no deben dejar #screen vacío. */
(() => {
  'use strict';
  function showError(message) {
    let main=document.getElementById('screen');
    if(!main){
      main=document.createElement('main');main.id='screen';main.className='body-error';
      (document.querySelector('.workspace')||document.body).append(main);
    }
    if(document.documentElement.dataset.amaruReady==='true' && main.querySelector('h1')) {
      const alert=document.getElementById('storage-alert');if(alert){alert.hidden=false;alert.textContent='Una operación encontró un error. Los datos guardados no se borraron. '+message;}return;
    }
    main.replaceChildren();
    const section=document.createElement('section');section.className='panel panel-body boot-message';
    const h=document.createElement('h1');h.textContent='No se pudo cargar esta vista';
    const p=document.createElement('p');p.textContent=message+' Puedes reintentar sin borrar tus datos.';
    const retry=document.createElement('button');retry.className='button primary';retry.textContent='Volver a cargar';retry.onclick=()=>location.reload();
    section.append(h,p,retry);main.append(section);
    main.dataset.bootError='true';
  }
  window.addEventListener('error',event=>{
    const source=event.target;
    if(source instanceof HTMLScriptElement)showError('No se descargó '+new URL(source.src).pathname+'.');
    else if(event.message)showError('El código de la vista no pudo terminar de ejecutarse.');
  },true);
  window.addEventListener('unhandledrejection',()=>showError('No se completó una operación de la interfaz.'));
  document.addEventListener('click',e=>{if(e.target.closest('[data-boot-retry]'))location.reload();});
  const check=()=>{if(document.documentElement.dataset.amaruReady!=='true')showError('Los recursos de la página no coinciden o no terminaron de cargar.');};
  // Todos los módulos son defer: al llegar DOMContentLoaded ya deben haber
  // renderizado. No depender de temporizadores que Chrome limita en pestañas de fondo.
  document.addEventListener('DOMContentLoaded',check,{once:true});
  window.addEventListener('load',check,{once:true});
  window.AmaruBoot={showError};
})();
