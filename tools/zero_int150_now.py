import json,struct,sys,time
from pathlib import Path
sys.path.insert(0, r"C:\Users\flaze\Desktop\Coding\cod-sp-trainer\tools")
from codgod_client import Agent
pid=int(sys.argv[1]); hits=json.loads(Path(r"C:\Users\flaze\Desktop\Coding\cod-sp-trainer\tools\health_pairs_int.json").read_text())["hits"]
a=Agent(pid)
for x in hits: a.write(x,struct.pack("<ii",0,0))
print("zeroed",len(hits))
time.sleep(1)
