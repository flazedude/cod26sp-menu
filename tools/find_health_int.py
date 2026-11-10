import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codgod_client import Agent

pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
targets = [int(x) for x in (sys.argv[2:] or ["100", "150"])]
agent = Agent(pid)
regions = [r for r in agent.regions() if r.type == 0x20000 and r.size]
regions.sort(key=lambda r: r.size, reverse=True)
print(f"private regions {len(regions)} total {sum(r.size for r in regions)/2**30:.2f} GiB")
chunk = 32 * 1024 * 1024
for target in targets:
    print(f"=== int pair {target} ===")
    t0 = time.time()
    hits = []
    scanned = 0
    for r in regions:
        for off in range(0, r.size, chunk):
            size = min(chunk, r.size - off)
            try:
                addrs = agent.scan_range_int(r.base + off, size, target, True)
            except Exception as exc:
                print("scan error", hex(r.base + off), exc)
                continue
            scanned += size
            if len(addrs):
                for a in addrs[:20]:
                    print(f"int-pair {target} at {int(a):#018x}")
                hits.extend(int(a) for a in addrs)
        if hits:
            break
    print(f"target {target} hits {len(hits)} scanned {scanned/2**30:.2f} GiB in {time.time()-t0:.1f}s")
    if hits:
        out = Path(__file__).resolve().parent / "health_pairs_int.json"
        out.write_text(json.dumps({"target": target, "hits": hits}))
        print("saved", out)
        break
