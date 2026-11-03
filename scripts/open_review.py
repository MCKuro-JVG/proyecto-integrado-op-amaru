"""Abre las aplicaciones instaladas con configuraciones privadas del equipo."""
import os,subprocess,json
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
private=ROOT/'.tools/demostracion'
ide=Path(os.environ.get('AMARU_PYCHARM', 'C:/Program Files/JetBrains/PyCharm 2026.2.3/bin/pycharm64.exe'))
files=['amaru/gestion/models.py','amaru/gestion/api.py','amaru/gestion/serializers.py','amaru/gestion/services.py','amaru/config/settings.py','amaru/gestion/attention.py','amaru/static/server.js','amaru/gestion/health.py','amaru/config/attention_stable_settings.py','scripts/attention_runtime.py']
if ide.is_file():
    env=os.environ.copy();props=ROOT/'.tools/attention/pycharm.properties'
    if props.exists():env['PYCHARM_PROPERTIES']=str(props)
    subprocess.Popen([str(ide),str(ROOT),*[str(ROOT/p) for p in files]],cwd=ROOT,env=env)
exe=private/'dbeaver/dbeaver.exe'
if exe.is_file():
    env=os.environ.copy()
    for file,prefix in [(private/'database.env','AMARU_DEMO_DB_'),(ROOT/'.tools/attention/database-readonly.env','AMARU_QR_DB_')]:
        if file.exists():
            values=dotenv_values(file);env[prefix+'USER']=values['DB_USER'];env[prefix+'PASSWORD']=values['DB_PASSWORD']
    subprocess.Popen([str(exe),'-data',str(private/'workspace'),'-con','name=Opticas Amaru QR DEMO - SOLO LECTURA','-f',str(Path(os.environ.get('AMARU_REVIEW_QUERY_FILE',str(ROOT/'docs/consultas_demostracion_qr.sql')))),'-vmargs','-Dproduct.config.disable=true','-Ddbeaver.drivers.configuration-file='+str(private/'drivers.xml')],env=env,cwd=exe.parent)
print('Apertura solicitada: PyCharm y DBeaver. No se escribieron contraseñas en argumentos.')
