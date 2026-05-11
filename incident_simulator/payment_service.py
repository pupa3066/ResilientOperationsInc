"""Payment service — depends on db_service. Logs real errors when DB is down."""
import time, random, json, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen
from urllib.error import URLError

logging.basicConfig(
    filename="logs/payment-service.log", level=logging.DEBUG,
    format='%(asctime)s level=%(levelname)s service=payment-svc msg="%(message)s"'
)
log = logging.getLogger()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            resp = urlopen("http://localhost:8003/query", timeout=2)
            data = json.loads(resp.read())
            log.info("DB query success")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "payment_ok"}).encode())
        except URLError as e:
            log.error(f"DB connection failed: {e.reason}")
            log.error("HikariPool-1 - Connection is not available, request timed out after 2000ms")
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error": "payment failed — db unreachable"}')
        except TimeoutError:
            log.error("DB query timeout after 2000ms — pool exhausted")
            self.send_response(504)
            self.end_headers()
            self.wfile.write(b'{"error": "timeout"}')

    def log_message(self, fmt, *args): pass  # suppress default

if __name__ == "__main__":
    import os; os.makedirs("logs", exist_ok=True)
    print("[payment-svc] Starting on :8002")
    HTTPServer(("", 8002), Handler).serve_forever()
