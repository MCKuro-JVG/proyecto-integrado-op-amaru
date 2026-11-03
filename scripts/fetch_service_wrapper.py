"""Prepara WinSW oficial para este instalador; no ejecuta ni registra servicios."""
import hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW.NET461.exe'
EXPECTED='b5066b7bbdfba1293e5d15cda3caaea88fbeab35bd5b38c41c913d492aadfc4f'
def main():
    directory=ROOT/'.tools/stability/winsw';directory.mkdir(parents=True,exist_ok=True);file=directory/'WinSW.exe'
    if file.exists():data=file.read_bytes()
    else:
        request=urllib.request.Request(URL,headers={'User-Agent':'OpticasAmaru-Operations/1.0'})
        with urllib.request.urlopen(request,timeout=45) as response:data=response.read()
    actual=hashlib.sha256(data).hexdigest()
    if actual!=EXPECTED:raise RuntimeError('El archivo no coincide con la versión revisada; no se instala.')
    file.write_bytes(data);file.with_name('source.json').write_text(json.dumps({'source':URL,'sha256':actual,'bytes':len(data),'action':'download_only'}),encoding='utf-8')
    print('WinSW oficial preparado y hash coincidente; no se instalaron servicios.')
if __name__=='__main__':main()
