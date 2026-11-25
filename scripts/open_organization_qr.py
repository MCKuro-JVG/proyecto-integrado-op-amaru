"""Abre la revisión de QR del hosting sin iniciar servidores ni guardar credenciales."""
import json
import os
from pathlib import Path
import subprocess
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = 'https://opticaamaru.alwaysdata.net'
    pages = [base+'/app/convenios.html', base+'/app/sindicatos.html']
    metadata = ROOT/'.tools/backend-qa/qr-dual/demo-remote.json'
    if metadata.exists():
        values = json.loads(metadata.read_text(encoding='utf-8'))
        for key in ('traditional', 'union_agreement'):
            identifier = values.get(key)
            if isinstance(identifier, int) and identifier > 0:
                pages.append(base+'/app/qr_organizacion.html?organizacion='+str(identifier))
    chrome = Path(os.environ.get('AMARU_CHROME', 'C:/Program Files/Google/Chrome/Application/chrome.exe'))
    if chrome.is_file():
        subprocess.Popen([str(chrome), '--new-window', *pages], cwd=ROOT)
    else:
        for page in pages:
            webbrowser.open_new_tab(page)
    # El iniciador privado existente conserva la conexión de lectura del equipo.
    # No se distribuye ni se crea un archivo de contraseñas junto a este script.
    query = ROOT/'docs/consultas_qr_organizaciones.sql'
    print('Revisión abierta en el hosting. Inicia sesión con tu cuenta autorizada si se solicita.')
    print('Consulta de solo lectura para DBeaver: '+str(query))
    print('No se iniciaron servidores, túneles ni instancias de MariaDB adicionales.')


if __name__ == '__main__':
    main()
