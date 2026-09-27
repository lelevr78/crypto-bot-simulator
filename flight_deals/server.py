"""Server HTTP (solo libreria standard): pagina web + API JSON."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .airports import DESTINATIONS, ORIGINS
from .scanner import Scanner

STATIC = Path(__file__).parent / "static"


def _float(value: str | None, default: float | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


def make_handler(scanner: Scanner):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RadarVoli/0.1"

        def log_message(self, *args) -> None:  # silenzia il log per richiesta
            pass

        def _json(self, payload, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, name: str) -> None:
            path = (STATIC / name).resolve()
            if STATIC.resolve() not in path.parents or not path.is_file():
                self._json({"error": "non trovato"}, 404)
                return
            body = path.read_bytes()
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                self._static("index.html")
            elif url.path.startswith("/static/"):
                self._static(url.path.removeprefix("/static/"))
            elif url.path == "/api/deals":
                deals = scanner.store.query(
                    origin=q.get("origin", ""),
                    destination=q.get("destination", ""),
                    min_discount=_float(q.get("min_discount"), 0.0),
                    max_price=_float(q.get("max_price"), None),
                    month=q.get("month", ""),
                    sort=q.get("sort", "sconto"),
                    limit=int(_float(q.get("limit"), 200)),
                )
                self._json({"deals": deals})
            elif url.path == "/api/status":
                self._json(scanner.status())
            elif url.path == "/api/airports":
                self._json({
                    "origins": [{"code": a.code, "city": a.city} for a in ORIGINS],
                    "destinations": [{"code": a.code, "city": a.city, "country": a.country} for a in DESTINATIONS],
                })
            else:
                self._json({"error": "non trovato"}, 404)

    return Handler


def serve(scanner: Scanner, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(scanner))
