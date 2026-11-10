import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codgod_client import Agent

pid = int(sys.argv[1])
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
addrs = [150637159804, 150637163900]
a = Agent(pid)
print("watching", [hex(x) for x in addrs], flush=True)
prev = {}
start = time.time()
while time.time() - start < seconds:
    for addr in addrs:
        data = a.read(addr, 8)
        if len(data) == 8:
            value = struct.unpack("<ii", data)
            old = prev.get(addr)
            if old is not None and old != value:
                print(f"{time.time()-start:6.2f}s {addr:#x} {old} -> {value}", flush=True)
            prev[addr] = value
    time.sleep(0.1)
print("final", {hex(k): v for k, v in prev.items()}, flush=True)
