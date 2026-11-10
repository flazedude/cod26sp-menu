import json,struct,sys
from pathlib import Path
sys.path.insert(0, r"C:\Users\flaze\Desktop\Coding\cod-sp-trainer\tools")
from codgod_client import Agent
a=Agent(int(sys.argv[1])); hits=json.loads(Path(r"C:\Users\flaze\Desktop\Coding\cod-sp-trainer\tools\health_pairs_int.json").read_text())["hits"]
for x in hits: a.write(x,struct.pack("<ii",100,100))
print("restored",len(hits))
