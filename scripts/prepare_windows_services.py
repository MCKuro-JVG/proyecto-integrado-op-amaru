"""Genera configuraciones revisables; no registra ni arranca servicios Windows."""
import hashlib,json,shutil,sys,subprocess,csv,io,os
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
def definition(name,root):
    service=ET.Element('service')
    def add(tag,text):ET.SubElement(service,tag).text=str(text)
    add('id',name);add('name',name);add('description','Ópticas Amaru: servicio local sin privilegios administrativos.')
    add('startmode','Automatic');add('delayedAutoStart','true')
    account=ET.SubElement(service,'serviceaccount');ET.SubElement(account,'domain').text='NT AUTHORITY';ET.SubElement(account,'user').text='LocalService'
    add('workingdirectory',root);add('logpath',root/'.tools/stability/runtime');ET.SubElement(service,'log',mode='roll-by-size').append(ET.Element('sizeThreshold'))
    service.find('log/sizeThreshold').text='5120'
    ET.SubElement(service,'onfailure',action='restart',delay='15 sec');ET.SubElement(service,'onfailure',action='restart',delay='30 sec');ET.SubElement(service,'onfailure',action='restart',delay='60 sec')
    add('resetfailure','1 hour');add('stoptimeout','60 sec')
    py=root/'.venv/Scripts/python.exe'
    if name=='OpticasAmaruDatabase':
        add('executable',root/'.tools/mariadb/mariadb-11.4.13-winx64/bin/mariadbd.exe')
        add('startarguments','--defaults-file="'+str(root/'.tools/mariadb/data/my.ini')+'"')
        add('stopexecutable',py);add('stoparguments','-B "'+str(root/'scripts/service_database.py')+'" stop')
    elif name=='OpticasAmaruAttention':
        add('depend','OpticasAmaruDatabase');add('executable',py)
        add('startarguments','-B "'+str(root/'scripts/attention_runtime.py')+'" supervise')
        add('stopexecutable',py);add('stoparguments','-B "'+str(root/'scripts/attention_runtime.py')+'" stop')
        ET.SubElement(service,'env',name='AMARU_STABLE_ENV_FILE',value=str(root/'amaru/.env.qr-demo'))
    else:raise ValueError('Servicio no autorizado en este plan.')
    return service

def prepare():
    target=ROOT/'.tools/stability/services';target.mkdir(parents=True,exist_ok=True)
    owner=ROOT/'.tools/stability/install-owner.json'
    if not owner.exists() and os.name=='nt':
        output=subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True)
        sid=next(csv.reader(io.StringIO(output)))[-1]
        owner.write_text(json.dumps({'sid':sid}),encoding='utf-8')
    source=ROOT/'.tools/stability/winsw/WinSW.exe'
    if source.exists():
        manifest=json.loads(source.with_name('source.json').read_text());actual=hashlib.sha256(source.read_bytes()).hexdigest()
        if actual!=manifest['sha256']:raise RuntimeError('El archivo WinSW cambió; no preparar la instalación.')
    for name in ('OpticasAmaruDatabase','OpticasAmaruAttention'):
        ET.ElementTree(definition(name,ROOT)).write(target/(name+'.xml'),encoding='utf-8',xml_declaration=True)
        if source.exists():
            destination=target/(name+'.exe')
            if destination.exists():
                if hashlib.sha256(destination.read_bytes()).digest()!=hashlib.sha256(source.read_bytes()).digest():
                    raise RuntimeError('La versión instalada difiere. Actualizar solo mediante mantenimiento autorizado.')
            else:shutil.copy2(source,destination)
    return target
if __name__=='__main__':print(str(prepare()))
