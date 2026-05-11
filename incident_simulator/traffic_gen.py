"""
Traffic generator — hammers the API gateway to produce real log volume.
Run AFTER starting all 3 services.
"""
import time, random
from urllib.request import urlopen
from urllib.error import URLError

RATE = 10       # requests per second
DURATION = 60   # seconds

print(f"[traffic-gen] Sending {RATE} req/s for {DURATION}s → http://localhost:8001")
errors = ok = 0

for _ in range(RATE * DURATION):
    try:
        urlopen("http://localhost:8001/checkout", timeout=4)
        ok += 1
    except URLError:
        errors += 1
    time.sleep(1 / RATE)

print(f"\n[traffic-gen] Done. OK={ok}  ERRORS={errors}  error_rate={errors/(ok+errors)*100:.1f}%")
