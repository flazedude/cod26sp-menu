import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codgod_client import Agent

pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
first = int(sys.argv[2]) if len(sys.argv) > 2 else 100
second = int(sys.argv[3]) if len(sys.argv) > 3 else 150
a = Agent(pid)
hits = []
for r in a.regions():
    if r.type != 0x20000 or r.state != 0x1000 or (r.protect & 0x100):
        continue
    off = 0
    while off < int(r.size):
        n = min(16 * 1024 * 1024, int(r.size) - off)
        try:
            hits.extend(int(x) for x in a.scan_range_int(int(r.base) + off, n, first, pair=False))
        except Exception:
            pass
        off += n
print("first-value hits", len(hits))
found = []
for addr in hits:
    data = a.read(addr, 8)
    if len(data) != 8:
        continue
    x, y = struct.unpack("<ii", data)
    if (x, y) in ((first, second), (second, first)):
        found.append((addr, x, y))
        print(f"pair ({x},{y}) at {addr:#018x}", flush=True)
print("found", len(found))
Path(__file__).resolve().parent.joinpath("health_pairs_mixed.json").write_text(
    __import__("json").dumps({"first": first, "second": second, "hits": [x[0] for x in found]}, indent=2)
)
