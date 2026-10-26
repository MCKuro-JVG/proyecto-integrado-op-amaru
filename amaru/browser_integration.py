"""Prueba optativa contra el servidor local, usando solo datos ficticios y perfil Chrome efímero."""
import json,uuid
from pathlib import Path
from io import BytesIO
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright


def main():
    root=Path(__file__).resolve().parent
    credentials=json.loads((root/'demo-credentials.json').read_text(encoding='utf-8'))
    marker=uuid.uuid4().hex[:8]
    output=root.parent/'.tools'/'backend-qa';output.mkdir(exist_ok=True)
    errors=[];results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1366,'height':900})
        tab=context.new_page();tab.on('pageerror',lambda exc:errors.append(str(exc)))
        tab.goto('http://127.0.0.1:8001/app/formulario_remoto.html?tipo=contacto')
        tab.get_by_label('Nombre completo',exact=True).fill('FICTICIO navegador '+marker)
        tab.get_by_label('Teléfono',exact=True).fill('+56900000000')
        tab.get_by_label('Correo',exact=True).fill('ficticio@example.invalid')
        tab.get_by_label('Motivo de consulta').fill('Consulta ficticia de integración '+marker)
        tab.get_by_label('Autorizo el contacto para gestionar esta solicitud.').check()
        tab.get_by_role('button',name='Registrar solicitud',exact=True).click()
        tab.get_by_role('heading',name='Solicitud registrada',exact=True).wait_for()
        results.append('Formulario público registrado mediante UI')
        tab.goto('http://127.0.0.1:8001/app/dashboard.html')
        tab.get_by_label('Usuario o correo').fill('personal_demo')
        tab.get_by_label('Contraseña',exact=True).fill(credentials['personal_demo'])
        tab.get_by_role('button',name='Iniciar sesión',exact=True).click()
        tab.get_by_role('heading',name='Resumen de atención',exact=True).wait_for()
        tab.goto('http://127.0.0.1:8001/app/solicitudes.html')
        tab.get_by_text('Consulta ficticia de integración '+marker,exact=True).wait_for()
        results.append('Solicitud visible desde personal autenticado')
        tab.goto('http://127.0.0.1:8001/app/clientes.html')
        tab.get_by_role('button',name='Registrar cliente',exact=True).click()
        # Un RUT ficticio válido distinto en cada ejecución, evitando sobrescribir fichas previas.
        body=str(30000000+int(marker,16)%50000000)
        total=sum(int(n)*(2+i%6) for i,n in enumerate(reversed(body)));dv=11-total%11
        rut=body+'-'+('0' if dv==11 else 'K' if dv==10 else str(dv))
        tab.get_by_label('RUT',exact=True).fill(rut)
        tab.get_by_label('Nombre completo',exact=True).fill('FICTICIO integración '+marker)
        tab.get_by_label('Teléfono',exact=True).fill('+56900000000')
        tab.get_by_label('Correo',exact=True).fill('ficticio@example.invalid')
        tab.get_by_role('button',name='Guardar en el servidor',exact=True).click()
        tab.get_by_text('FICTICIO integración '+marker,exact=True).wait_for()
        results.append('Cliente registrado desde UI y vuelto a consultar')
        tab.goto('http://127.0.0.1:8001/app/recetas.html')
        tab.get_by_role('button',name='Nueva receta',exact=True).click()
        tab.get_by_label('Cliente',exact=True).wait_for()
        options=tab.locator('select[name=client] option').evaluate_all('(rows)=>rows.map(r=>({v:r.value,t:r.textContent}))')
        client=next(o['v'] for o in options if marker in o['t'])
        tab.get_by_label('Cliente',exact=True).select_option(client)
        from datetime import date
        tab.get_by_label('Fecha de emisión').fill(date.today().isoformat())
        b=BytesIO();im=Image.new('RGB',(300,120),'white');ImageDraw.Draw(im).text((10,30),'RECETA FICTICIA - PRUEBA',fill='black');im.save(b,format='PNG')
        tab.get_by_label('Archivo privado PDF, JPG o PNG').set_input_files({'name':'ficticia.png','mimeType':'image/png','buffer':b.getvalue()})
        tab.get_by_role('button',name='Guardar en el servidor',exact=True).click()
        tab.locator('dialog').wait_for(state='hidden')
        results.append('Receta ficticia subida mediante UI')
        tab.goto('http://127.0.0.1:8001/app/cotizaciones.html')
        tab.get_by_role('button',name='Nueva cotización',exact=True).click()
        tab.get_by_label('Cliente',exact=True).select_option(client)
        recipes=tab.locator('select[name=prescription] option').evaluate_all('(rows)=>rows.map(r=>({v:r.value,t:r.textContent}))')
        recipe=next(o['v'] for o in recipes if o['t'].startswith('Cliente '+client+' ·'))
        tab.get_by_label('Receta',exact=True).select_option(recipe)
        tab.get_by_label('Armazón / modelo').fill('Armazón ficticio '+marker)
        tab.get_by_label('Cristal / color').fill('Cristal ficticio')
        tab.get_by_label('Monto CLP').fill('25000')
        tab.get_by_label('Cotización aprobada por el cliente').check()
        tab.get_by_role('button',name='Guardar en el servidor',exact=True).click()
        tab.locator('dialog').wait_for(state='hidden')
        with tab.expect_response(lambda r:'/convert/' in r.url and r.request.method=='POST') as converted:
            tab.locator('tbody tr').filter(has=tab.get_by_text(client,exact=True)).get_by_role('button',name='Generar OT').click()
        assert converted.value.status==200
        tab.goto('http://127.0.0.1:8001/app/ordenes.html')
        row=tab.locator('tbody tr').filter(has_text='FICTICIO integración '+marker)
        row.get_by_role('button',name='Actualizar',exact=True).click()
        tab.get_by_label('Estado',exact=True).select_option('Disponible para retiro')
        tab.get_by_role('button',name='Guardar en el servidor',exact=True).click()
        row.get_by_role('link',name='Revisar retiro').click()
        tab.get_by_role('heading',name='Documento de entrega y conformidad',exact=True).wait_for()
        canvas=tab.locator('#signature');canvas.scroll_into_view_if_needed();box=canvas.bounding_box()
        tab.mouse.move(box['x']+15,box['y']+90);tab.mouse.down()
        for x,y in [(35,25),(75,110),(120,30),(160,90)]:tab.mouse.move(box['x']+x,box['y']+y,steps=8)
        tab.mouse.up()
        tab.get_by_label('Revisé los datos y condiciones y confirmo la recepción de los lentes.').check()
        tab.get_by_role('button',name='Confirmar entrega',exact=True).click()
        tab.get_by_role('heading',name='Entrega registrada',exact=True).wait_for()
        results.append('Cotización → OT → disponible → firma → documento y entrega persistidos')
        for width,height in [(1366,900),(375,812)]:
            tab.set_viewport_size({'width':width,'height':height})
            for html in sorted((root.parent/'frontend_amaru').glob('*.html')):
                suffix='?cliente='+client if html.stem=='detalle_cliente' else ''
                tab.goto('http://127.0.0.1:8001/app/'+html.name+suffix)
                tab.wait_for_function("document.documentElement.dataset.amaruReady==='true'")
                assert tab.locator('#screen h1').count()>0,html.name
                assert not tab.get_by_role('heading',name='No se pudo cargar esta sección',exact=True).count(),html.name
                overflow=tab.evaluate('document.documentElement.scrollWidth>innerWidth+2')
                assert not overflow,(html.name,width,'desbordamiento')
                results.append(f'{html.name} visible {width}x{height}')
            tab.screenshot(path=str(output/f'personal-{width}.png'),full_page=True)
        # Contexto ajeno: el almacenamiento de la demostración no intervino.
        assert tab.evaluate('Object.keys(localStorage).length')==0
        assert not errors,errors
        browser.close()
    (output/'resultado.json').write_text(json.dumps({'results':results,'page_errors':errors,'marker':marker},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':len(results),'page_errors':errors,'marker':marker}))


if __name__=='__main__':main()
