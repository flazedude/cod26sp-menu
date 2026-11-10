import struct,sys,time
sys.path.insert(0, r"C:\Users\flaze\Desktop\Coding\cod-sp-trainer\tools")
from codgod_client import Agent
a=Agent(24928)
addrs=[0x2312aca57c,0x2312acb57c]
try: print("stop_old",a.freeze_stop())
except Exception as e: print("stop_old_err",e)
print("freeze",a.freeze_start(addrs))
for x in addrs: print(hex(x),a.read(x,8).hex())
for x in addrs: a.write(x,struct.pack("<ii",0,0))
time.sleep(0.3)
print("after zero")
for x in addrs: print(hex(x),a.read(x,8).hex())
print("ping",a.ping())
