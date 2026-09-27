import json
import threading
import unittest
import urllib.request
from datetime import date, datetime, timedelta, timezone

from flight_deals.detector import DealDetector, level_for
from flight_deals.providers import Fare, SimulatedProvider
from flight_deals.scanner import Scanner
from flight_deals.server import serve
from flight_deals.store import DealStore

DEP = date.today() + timedelta(days=40)


def fare(price, dep=DEP, dest="BCN"):
    return Fare("VRN", dest, dep, dep + timedelta(days=4), price, "Test Air", 0)


def trained(prices=(100, 95, 105, 98, 102, 110, 90, 101, 99, 97) * 4):
    det = DealDetector(min_samples=30)
    for p in prices:
        assert det.observe(fare(p)) is None
    return det


class DetectorTest(unittest.TestCase):
    def test_flags_big_unusual_drop(self):
        deal = trained().observe(fare(30))
        self.assertIsNotNone(deal)
        self.assertAlmostEqual(deal.normal_price, 100, delta=1)
        self.assertAlmostEqual(deal.discount, 0.70, delta=0.01)
        self.assertEqual(deal.level, "Super offerta")

    def test_ignores_normal_and_moderate_prices(self):
        det = trained()
        self.assertIsNone(det.observe(fare(88)))
        self.assertIsNone(det.observe(fare(55)))  # 45%: sotto la soglia del 50%

    def test_needs_history_before_flagging(self):
        det = DealDetector(min_samples=30)
        for p in [100] * 29:
            det.observe(fare(p))
        self.assertIsNone(det.observe(fare(10)))

    def test_volatile_route_needs_unusual_drop(self):
        # Rotta molto volatile: un -50% rientra nella variazione tipica.
        det = trained(prices=(40, 160, 60, 150, 100, 45, 170, 100, 55, 140) * 4)
        self.assertIsNone(det.observe(fare(45)))

    def test_anomalies_do_not_pollute_baseline(self):
        det = trained()
        for _ in range(50):
            self.assertIsNotNone(det.observe(fare(20)))
        self.assertAlmostEqual(det.stats(("VRN", "BCN")).median, 100, delta=1)

    def test_levels(self):
        self.assertEqual(level_for(0.52), "Ottimo prezzo")
        self.assertEqual(level_for(0.65), "Super offerta")
        self.assertEqual(level_for(0.85), "Error fare")


class StoreTest(unittest.TestCase):
    def test_upsert_keeps_cheapest_and_filters(self):
        det, store = trained(), DealStore()
        store.upsert(det.observe(fare(40)))
        store.upsert(det.observe(fare(25)))
        store.upsert(det.observe(fare(35)))
        rows = store.query()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], 25)
        self.assertIn("skyscanner.it", rows[0]["links"]["skyscanner"])
        self.assertEqual(store.query(min_discount=0.8), [])
        self.assertEqual(store.query(max_price=20), [])
        self.assertEqual(len(store.query(origin="vrn", month=DEP.strftime("%Y-%m"))), 1)

    def test_expired_deals_are_hidden_and_purged(self):
        det, store = trained(), DealStore(ttl_hours=1)
        store.upsert(det.observe(fare(30)))
        later = datetime.now(timezone.utc) + timedelta(hours=2)
        self.assertEqual(store.query(now=later), [])
        self.assertEqual(store.purge(now=later), 1)


class SimulationTest(unittest.TestCase):
    def test_low_false_positive_rate(self):
        prov = SimulatedProvider(seed=7, anomaly_rate=0)
        scanner = Scanner(prov, DealDetector(), DealStore(), batch_size=5000)
        scanner.warm_up()
        found = sum(scanner.scan_once() for _ in range(20))
        self.assertLessEqual(found, 2, "troppi falsi positivi su tariffe normali")

    def test_finds_injected_anomalies(self):
        prov = SimulatedProvider(seed=3, anomaly_rate=0.01)
        scanner = Scanner(prov, DealDetector(), DealStore(), batch_size=5000)
        scanner.warm_up()
        found = sum(scanner.scan_once() for _ in range(4))
        self.assertGreater(found, 50)  # ~200 anomalie iniettate, ~85% con sconto >= 50%


class ServerTest(unittest.TestCase):
    def test_api_and_page(self):
        scanner = Scanner(SimulatedProvider(seed=1, anomaly_rate=0.01), DealDetector(), DealStore(), batch_size=5000)
        scanner.warm_up(min_combinations=30000)
        httpd = serve(scanner, port=0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            deals = json.load(urllib.request.urlopen(base + "/api/deals?min_discount=0.5&sort=prezzo"))["deals"]
            self.assertTrue(deals)
            self.assertEqual([d["price"] for d in deals], sorted(d["price"] for d in deals))
            status = json.load(urllib.request.urlopen(base + "/api/status"))
            self.assertGreaterEqual(status["combinations"], 30000)
            html = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("Radar Voli", html)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/static/../server.py")
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
