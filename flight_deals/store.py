"""Archivio SQLite delle offerte trovate (thread-safe)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

from .airports import BY_CODE
from .detector import Deal, level_for

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    depart TEXT NOT NULL,
    ret TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL,
    normal_price REAL NOT NULL,
    discount REAL NOT NULL,
    zscore REAL NOT NULL,
    min_seen REAL NOT NULL,
    samples INTEGER NOT NULL,
    airline TEXT,
    stops INTEGER,
    currency TEXT,
    found_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE (origin, destination, depart, ret)
);
CREATE INDEX IF NOT EXISTS ix_deals_expires ON deals (expires_at);
"""

SORTS = {
    "sconto": "discount DESC",
    "prezzo": "price ASC",
    "recenti": "found_at DESC",
    "partenza": "depart ASC",
}


def booking_links(origin: str, dest: str, depart: str, ret: str) -> dict[str, str]:
    d = depart.replace("-", "")[2:]
    r = ret.replace("-", "")[2:] if ret else ""
    sky = f"https://www.skyscanner.it/trasporti/voli/{origin.lower()}/{dest.lower()}/{d}/"
    if r:
        sky += f"{r}/"
    q = f"Voli da {origin} a {dest} il {depart}" + (f" ritorno {ret}" if ret else "")
    google = "https://www.google.com/travel/flights?hl=it&q=" + q.replace(" ", "%20")
    return {"skyscanner": sky, "google": google}


class DealStore:
    def __init__(self, path: str = ":memory:", ttl_hours: float = 48) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.ttl = timedelta(hours=ttl_hours)

    def upsert(self, deal: Deal) -> None:
        f = deal.fare
        found = deal.found_at.isoformat()
        expires = (deal.found_at + self.ttl).isoformat()
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO deals (origin, destination, depart, ret, price, normal_price, discount,
                                   zscore, min_seen, samples, airline, stops, currency, found_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (origin, destination, depart, ret) DO UPDATE SET
                    price = excluded.price, normal_price = excluded.normal_price,
                    discount = excluded.discount, zscore = excluded.zscore,
                    min_seen = excluded.min_seen, samples = excluded.samples,
                    airline = excluded.airline, stops = excluded.stops,
                    found_at = excluded.found_at, expires_at = excluded.expires_at
                WHERE excluded.price < deals.price OR deals.expires_at < excluded.found_at
                """,
                (f.origin, f.destination, f.depart.isoformat(), f.ret.isoformat() if f.ret else "",
                 f.price, deal.normal_price, deal.discount, deal.zscore, deal.min_seen,
                 deal.samples, f.airline, f.stops, f.currency, found, expires),
            )

    def purge(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        with self.lock, self.conn:
            cur = self.conn.execute(
                "DELETE FROM deals WHERE expires_at < ? OR depart < ?",
                (now.isoformat(), now.date().isoformat()),
            )
            return cur.rowcount

    def query(
        self,
        origin: str = "",
        destination: str = "",
        min_discount: float = 0.0,
        max_price: float | None = None,
        month: str = "",
        sort: str = "sconto",
        limit: int = 200,
        now: datetime | None = None,
    ) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        where = ["expires_at >= ?", "depart >= ?", "discount >= ?"]
        args: list = [now.isoformat(), now.date().isoformat(), min_discount]
        if origin:
            where.append("origin = ?")
            args.append(origin.upper())
        if destination:
            where.append("destination = ?")
            args.append(destination.upper())
        if max_price is not None:
            where.append("price <= ?")
            args.append(max_price)
        if month:
            where.append("substr(depart, 1, 7) = ?")
            args.append(month)
        sql = f"SELECT * FROM deals WHERE {' AND '.join(where)} ORDER BY {SORTS.get(sort, SORTS['sconto'])} LIMIT ?"
        args.append(int(limit))
        with self.lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [self._to_dict(r) for r in rows]

    def summary(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        with self.lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n, AVG(discount) AS avg_d, MAX(discount) AS max_d, MIN(price) AS min_p "
                "FROM deals WHERE expires_at >= ? AND depart >= ?",
                (now.isoformat(), now.date().isoformat()),
            ).fetchone()
        return {
            "active_deals": row["n"],
            "avg_discount": round(row["avg_d"] or 0, 4),
            "max_discount": round(row["max_d"] or 0, 4),
            "min_price": row["min_p"],
        }

    @staticmethod
    def _to_dict(r: sqlite3.Row) -> dict:
        d = dict(r)
        o, t = BY_CODE.get(d["origin"]), BY_CODE.get(d["destination"])
        d["origin_city"] = o.city if o else d["origin"]
        d["destination_city"] = t.city if t else d["destination"]
        d["destination_country"] = t.country if t else ""
        d["level"] = level_for(d["discount"])
        d["saving"] = round(d["normal_price"] - d["price"], 2)
        d["nights"] = (date.fromisoformat(d["ret"]) - date.fromisoformat(d["depart"])).days if d["ret"] else None
        d["links"] = booking_links(d["origin"], d["destination"], d["depart"], d["ret"])
        return d
