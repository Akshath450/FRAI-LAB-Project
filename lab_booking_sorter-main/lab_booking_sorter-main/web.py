import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import urlparse

import main


HOST = "127.0.0.1"
PORT = 8000
CONFIRMED_BOOKINGS = [("2026-10-16", "AN", "LAB3")]
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/styles.css": "styles.css",
}

lock = threading.Lock()
taken = list(CONFIRMED_BOOKINGS)
results = []


def load_demo():
    global taken, results
    taken = list(CONFIRMED_BOOKINGS)
    results = []
    for number, sample in enumerate(main.REQUESTS, 1):
        details = main.classify(sample, use_ai=False)
        status, reason = main.decide(details, taken)
        details.update(
            id="Q" + str(number).zfill(2),
            request=sample[0],
            status=status,
            reason=reason,
        )
        results.append(details)
    return results


class RequestHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/demo":
            with lock:
                self.send_json(200, {"results": load_demo()})
            return

        filename = STATIC_FILES.get(path)
        if filename is None:
            self.send_error(404, "Not found")
            return

        content = (main.FOLDER / filename).read_bytes()
        content_type = guess_type(filename)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if urlparse(self.path).path != "/api/book":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16384:
                self.send_json(400, {"error": "Invalid request size."})
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            self.send_json(400, {"error": "Request must contain valid JSON."})
            return

        request = payload.get("request")
        lab = payload.get("lab")
        day = payload.get("date")
        slot = payload.get("slot")
        students = payload.get("students")
        if not isinstance(request, str) or not request.strip() or len(request) > 300:
            self.send_json(400, {"error": "Enter a request description up to 300 characters."})
            return
        if lab not in main.LABS:
            self.send_json(400, {"error": "Choose a valid lab."})
            return
        if slot not in ("FN", "AN"):
            self.send_json(400, {"error": "Choose a valid time slot."})
            return
        try:
            parsed_day = date.fromisoformat(day)
        except (TypeError, ValueError):
            self.send_json(400, {"error": "Choose a valid date."})
            return
        if parsed_day.isoformat() != day or not date(2026, 8, 1) <= parsed_day <= date(2026, 12, 31):
            self.send_json(400, {"error": "Date must be between August and December 2026."})
            return
        if type(students) is not int or students <= 0:
            self.send_json(400, {"error": "Enter a positive whole number of students."})
            return

        details = {
            "lab": lab,
            "date": day,
            "slot": slot,
            "students": students,
            "summary": "Lab session",
        }
        with lock:
            status, reason = main.decide(details, taken)
            details.update(
                id="N" + str(sum(item["id"].startswith("N") for item in results) + 1).zfill(2),
                request=request.strip(),
                status=status,
                reason=reason,
            )
            results.insert(0, details)
            self.send_json(200, {"result": details})

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))


if __name__ == "__main__":
    print("Open http://127.0.0.1:8000 in your browser. Stop with Ctrl+C.")
    ThreadingHTTPServer((HOST, PORT), RequestHandler).serve_forever()
