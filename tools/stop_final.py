import sys
sys.path.insert(0, r"C:\Users\flaze\Desktop\Coding\cod-sp-trainer\tools")
from codgod_client import Agent
try:
 a=Agent(24928); print("stop",a.freeze_stop()); print("ping",a.ping())
except Exception as e: print("stop err",e)
