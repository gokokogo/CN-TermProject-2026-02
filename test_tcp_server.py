"""Run with: python -m unittest test_tcp_server.py"""
import concurrent.futures
import tempfile
import unittest
from pathlib import Path

import reservation_server


class TCPConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = reservation_server.DB_PATH
        reservation_server.DB_PATH = Path(self.temp_dir.name) / "test_cinema.db"
        self.runtime = reservation_server.ServerRuntime()

    def tearDown(self):
        self.runtime.close()
        reservation_server.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_two_clients_cannot_hold_same_seat(self):
        def request_hold(user_id):
            return reservation_server.tcp_request(
                self.runtime.address,
                "CREATE_HOLD",
                screening="TEST_SHOW",
                seat="A1",
                user_id=user_id,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(request_hold, ["client-A", "client-B"]))

        self.assertEqual(sum(1 for result in results if result.get("ok")), 1)
        self.assertEqual(sum(1 for result in results if not result.get("ok")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
