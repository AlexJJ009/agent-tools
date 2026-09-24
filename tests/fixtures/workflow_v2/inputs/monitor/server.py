"""Loopback-only service with independent request counters and an append journal."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", required=True)
    args = parser.parse_args()
    journal = Path(args.journal)
    state = {"count": 0, "observations": []}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            if self.path == "/stats":
                with lock:
                    body = json.dumps(state).encode()
                self.send_response(200)
            elif self.path in ("/probe", "/slow"):
                with lock:
                    state["count"] += 1
                    count = state["count"]
                    status = 429 if count % 3 == 2 else 200
                    observation = {"request_count": count, "observed_at_ns": time.time_ns(),
                                   "http_status": status, "path": self.path}
                    state["observations"].append(observation)
                    with journal.open("a") as stream:
                        stream.write(json.dumps(observation) + "\n")
                if self.path == "/slow":
                    time.sleep(0.2)
                body = json.dumps(observation).encode()
                self.send_response(status)
                if status == 429:
                    self.send_header("Retry-After", "1")
            else:
                self.send_response(404)
                body = b'{}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(json.dumps({"base_url": f"http://127.0.0.1:{server.server_port}", "pid": __import__("os").getpid()}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
