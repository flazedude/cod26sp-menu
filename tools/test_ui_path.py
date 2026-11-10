import sys,time
sys.path.insert(0, r"C:\Users\flaze\Desktop\Coding\cod-sp-trainer")
from trainer import scan_health_candidates, ensure_agent, game_pid
pid=game_pid(); a=ensure_agent(pid)
hits=[]
for v in (100,150): hits += scan_health_candidates(a,v)
seen=set(); hits=[h for h in hits if not (h in seen or seen.add(h))]
print("candidates",len(hits))
print("freeze",a.freeze_start(hits[:4000]))
time.sleep(0.3)
print("ping",a.ping())
print("stop",a.freeze_stop())
time.sleep(0.3)
print("ping2",a.ping())
