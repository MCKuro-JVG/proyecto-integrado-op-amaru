"""Servidor estático local de Ópticas Amaru. No es un backend ni procesa datos de clientes."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import partial
import argparse

ROOT=Path(__file__).resolve().parent/'frontend_amaru'
class AmaruHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control','no-store, max-age=0')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Amaru-Server','frontend-local-v3')
        super().end_headers()
    def do_GET(self):
        # No usar 304 con recursos que se actualizan durante la demostración.
        if 'If-Modified-Since' in self.headers:
            del self.headers['If-Modified-Since']
        super().do_GET()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    print(f'Ópticas Amaru: http://127.0.0.1:{args.port}/',flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(AmaruHandler,directory=str(ROOT)))
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
