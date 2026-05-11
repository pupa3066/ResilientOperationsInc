"""Fake DB service — kill this to trigger connection errors downstream."""
import time, random
from http.server import HTTPServer, BaseHTTPRequestHandler

FAIL_MODE = False  # toggle to True to simulate DB outage

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if FAIL_MODE or random.random() < 0.05:  # 5% random failure
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error": "DB connection pool exhausted"}')
        else:
            time.sleep(random.uniform(0.01, 0.05))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "rows": 42}')

    def log_message(self, fmt, *args):
        print(f"[db-service] {self.address_string()} - {fmt % args}")

if __name__ == "__main__":
    print("[db-service] Starting on :8003")
    HTTPServer(("", 8003), Handler).serve_forever()
