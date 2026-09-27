"""Run the actual app with fictional devices; no network or switch writes."""
import argparse
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'etherlighting'))
from app import Application, handler_for
from models import identify, PROFILES

DEVICES=[(1,'Front camera','#FF8A32','Cameras'),(3,'Living room TV','#3388FF','Apple TVs'),
         (5,'Home Assistant','#42D9B5','Home automation'),(7,'Office speaker','#B784FF','Audio'),
         (9,'Game console',None,''),(11,'Desk computer',None,'')]

class DemoSwitch:
    writable=True
    def __init__(self,model):self.model=model
    def describe(self):return identify(f'board.name={self.model}\nUS2.7.5.15\n')
    def read(self,key):
        count=PROFILES[self.model]['port_count']
        if key=='port_table':
            active={d[0] for d in DEVICES}|{count}
            return '\n'.join(f'{"U" if p==count else ""}{p} {"U/U 1000F" if p in active else "D/D 0F"}' for p in range(1,count+1))
        header='port vlan mac-address       ip-address      hostname          uptime     age wireless-type\n'
        header+='---- ---- ----------------- --------------- ---------------- ------- ------- -------------\n'
        for i,(port,name,*_) in enumerate(DEVICES+[(count,'Gateway',None,'')],1):
            header+=f'{port:4} {1:4} {"02:00:00:00:00:"+format(i,"02x"):17} {"192.0.2."+str(i):15} {name:16} {1000:7} {1:7} {"":13}\n'
        return header
    def verify_control(self):pass
    def color(self,*_):pass
    def restore(self):pass
    def close(self):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=list(PROFILES),default='USW-Pro-Max-48-PoE')
    parser.add_argument('--port',type=int,default=8099)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='etherlighting-demo-') as data:
        app=Application(Path(data),{'demo':True,'allow_led_control':True,'switch_host':'demo-switch.example'},DemoSwitch(args.model))
        rules=[dict(mac=f'02:00:00:00:00:{i:02x}',name=name,color=color,brightness=30,group=group,enabled=True,allow_shared=False)
               for i,(_,name,color,group) in enumerate(DEVICES,1) if color]
        app.action('/api/rules',dict(version=1,rules=rules))
        app.action('/api/settings',dict(app.settings,fallback_enabled=True))
        app.action('/api/start',{})
        worker=threading.Thread(target=app.poll,daemon=True);worker.start()
        server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(app,True))
        print(f'Demo only: http://127.0.0.1:{args.port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:
            app.quit.set();worker.join(timeout=5);server.server_close()

if __name__=='__main__':main()
