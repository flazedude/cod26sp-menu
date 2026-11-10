import ctypes
import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codgod_client import Agent, ps_main_window

pid = int(sys.argv[1])
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
hits = json.loads((Path(__file__).resolve().parent / "health_pairs_int.json").read_text())["hits"]
agent = Agent(pid)


def sample():
    out = []
    for addr in hits:
        data = agent.read(addr, 8)
        out.append(struct.unpack("<ii", data) if len(data) == 8 else (None, None))
    return out


print("baseline", len(hits))
before = sample()
print("distinct before", len({v for pair in before for v in pair if v is not None}))
if len(sys.argv) > 3 and sys.argv[3] == "grenade":
    user32 = ctypes.windll.user32
    hwnd = ps_main_window(pid)
    print("game hwnd", hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetCursorPos(700, 470)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(1.0)
    for vk in (0x34, 0x47):
        scan = user32.MapVirtualKeyW(vk, 0)
        print("key", hex(vk), "scan", scan)
        user32.keybd_event(vk, scan, 0, 0)
        time.sleep(0.1)
        user32.keybd_event(vk, scan, 2, 0)
        time.sleep(0.4)
    wait = max(wait, 3.5)
time.sleep(wait)
after = sample()
changed = []
for addr, b, a in zip(hits, before, after):
    if b[0] is None or a[0] is None:
        continue
    if b != a:
        changed.append((addr, b, a))
print("changed", len(changed))
for addr, b, a in changed[:80]:
    print(f"{addr:#018x} {b} -> {a}")
Path(__file__).resolve().parent.joinpath("health_changed_int.json").write_text(
    json.dumps([{"addr": x, "before": b, "after": a} for x, b, a in changed])
)
