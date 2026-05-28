"""
capture_line_userid.py — one-shot webhook receiver to capture LINE user ID

Usage:
  1. python scripts/capture_line_userid.py          (starts on port 8765)
  2. ngrok http 8765                                (exposes public URL)
  3. Paste the ngrok URL into LINE Developers Console
     -> Messaging API tab -> Webhook URL -> (ngrok URL)/webhook
  4. Click "Verify" in the console  OR  send any message to the bot via LINE app
  5. This script prints your userId (starts with U...)
  6. Ctrl+C to stop
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8765
found_ids = set()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"LINE webhook capture active")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

        try:
            data = json.loads(body)
            for event in data.get("events", []):
                uid = (event.get("source") or {}).get("userId", "")
                if uid and uid not in found_ids:
                    found_ids.add(uid)
                    print(f"\n{'='*50}")
                    print(f"  LINE User ID: {uid}")
                    print(f"{'='*50}\n")
        except Exception as e:
            print(f"parse error: {e}")

    def log_message(self, fmt, *args):
        pass  # silence request logs


if __name__ == "__main__":
    print(f"Listening on port {PORT}...")
    print("Next: run  ngrok http 8765  in another terminal")
    print("Then paste the ngrok URL into LINE Developers -> Webhook URL")
    HTTPServer(("", PORT), Handler).serve_forever()
