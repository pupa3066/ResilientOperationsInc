"""API gateway — calls payment-svc. Logs cascade failures."""
import time, json, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen
from urllib.error import URLError

logging.basicConfig(
    filename="logs/api-gateway.log", level=logging.DEBUG,
    format='%(asctime)s level=%(levelname)s service=api-gateway msg="%(message)s"'
)
log = logging.getLogger()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        start = time.time()
        try:
            resp = urlopen("http://localhost:8002/pay", timeout=3)
            latency = int((time.time() - start) * 1000)
            log.info(f"POST /checkout 200 latency={latency}ms")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "checkout_ok"}')
        except URLError as e:
            latency = int((time.time() - start) * 1000)
            log.error(f"Upstream connect error or disconnect/reset before headers latency={latency}ms")
            log.error("POST /checkout 503 Service Unavailable")
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error": "checkout failed"}')

    def log_message(self, fmt, *args): pass

if __name__ == "__main__":
    import os; os.makedirs("logs", exist_ok=True)
    print("[api-gateway] Starting on :8001")
    HTTPServer(("", 8001), Handler).serve_forever()
