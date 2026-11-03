"""Control de cierre del MariaDB del proyecto, solo para instalación autorizada."""
import argparse,json,secrets,socket,time
from pathlib import Path
from dotenv import dotenv_values,set_key
import MySQLdb
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'.tools/stability/service-stop.env'
def provision():
    if PRIVATE.exists():return
    password=json.loads((ROOT/'.tools/mariadb/local-admin.json').read_text())['password']
    con=MySQLdb.connect(host='127.0.0.1',user='root',passwd=password)
    with con.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User='amaru_service_stop' AND Host='127.0.0.1'")
        if cursor.fetchone()[0]:raise RuntimeError('La cuenta de parada ya existe sin archivo privado; requiere revisión manual.')
        value=secrets.token_urlsafe(40)
        cursor.execute("CREATE USER 'amaru_service_stop'@'127.0.0.1' IDENTIFIED BY %s",(value,))
        cursor.execute("GRANT SHUTDOWN ON *.* TO 'amaru_service_stop'@'127.0.0.1'")
    con.close();set_key(str(PRIVATE),'DB_USER','amaru_service_stop');set_key(str(PRIVATE),'DB_PASSWORD',value)
def stop():
    values=dotenv_values(PRIVATE)
    con=MySQLdb.connect(host='127.0.0.1',user=values['DB_USER'],passwd=values['DB_PASSWORD'])
    try:
        with con.cursor() as cursor:cursor.execute('SHUTDOWN')
    finally:con.close()
    for _ in range(60):
        with socket.socket() as s:alive=s.connect_ex(('127.0.0.1',3306))==0
        if not alive:return
        time.sleep(.5)
    raise RuntimeError('MariaDB no completó el cierre; no se inicia una segunda instancia.')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['provision','stop']);args=parser.parse_args()
    if args.action=='provision':provision()
    else:stop()
