"""Respaldo SQL local sin secretos en argumentos; no restaura ni borra bases."""
import argparse,hashlib,json,os,subprocess,datetime
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
def backup(env_file):
    env=dotenv_values(env_file);database=env['DB_NAME']
    if database not in ('opticas_amaru','opticas_amaru_qr_demo'):raise RuntimeError('Base fuera del alcance del respaldo del proyecto.')
    directory=ROOT/'.tools/stability/backups';directory.mkdir(parents=True,exist_ok=True)
    binary=Path(os.environ.get('AMARU_DUMP_EXECUTABLE',str(ROOT/'.tools/mariadb/mariadb-11.4.13-winx64/bin/mariadb-dump.exe')))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path=directory/f'{database}-{stamp}.sql';temp=path.with_suffix('.partial')
    child_env=os.environ.copy();child_env['MYSQL_PWD']=env['DB_PASSWORD']
    try:
        with temp.open('wb') as output:
            subprocess.run([str(binary),'--host='+env.get('DB_HOST','127.0.0.1'),'--port='+env.get('DB_PORT','3306'),'--user='+env['DB_USER'],'--single-transaction','--skip-lock-tables','--skip-add-locks','--no-tablespaces',database],env=child_env,stdout=output,stderr=subprocess.PIPE,check=True)
        if temp.stat().st_size<100:raise RuntimeError('El respaldo está vacío.')
        temp.replace(path)
        manifest={'database':database,'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'utc':stamp}
        path.with_suffix('.json').write_text(json.dumps(manifest),encoding='utf-8')
        return path,manifest
    except Exception:
        temp.unlink(missing_ok=True);raise RuntimeError('No se completó el respaldo. No se modificó la base de datos.') from None
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--env-file',type=Path,default=ROOT/'amaru/.env.qr-demo');args=parser.parse_args()
    path,data=backup(args.env_file);print(json.dumps({'backup':str(path),'bytes':data['bytes'],'sha256':data['sha256']}))
