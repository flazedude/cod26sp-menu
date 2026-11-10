import ctypes
import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codgod_client import Agent, ps_main_window

pid = int(sys.argv[1])
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
hits = json.loads((Path(__file__).resolve().parent / "health_pairs_int.json").read_text())["hits"]
agent = Agent(pid)
user32 = ctypes.windll.user32
user32.SetForegroundWindow(ps_main_window(pid))
prev = {}
start = time.time()
while time.time() - start < seconds:
    for addr in hits:
        data = agent.read(addr, 8)
        if len(data) != 8:
            continue
        value = struct.unpack("<ii", data)
        old = prev.get(addr)
        if old is not None and old != value:
            print(f"{time.time()-start:6.1f}s {addr:#018x} {old} -> {value}", flush=True)
        prev[addr] = value
    time.sleep(0.2)
print("final distinct", sorted({v for v in prev.values()}))
