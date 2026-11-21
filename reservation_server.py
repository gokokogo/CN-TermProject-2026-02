"""Threaded TCP reservation server used by the Streamlit cinema frontend."""
import json
import secrets
import socketserver
import sqlite3
import threading
import time
from pathlib import Path

ROWS = "ABCDE"
COLUMNS = 8
HOLD_SECONDS = 300
MAX_FRAME = 16_384
DB_PATH = Path(__file__).parent / "cinema_demo.db"


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=20, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def init_database():
    with _connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS seats (
            screening TEXT NOT NULL,
            seat TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING','RESERVED')),
            user_id TEXT NOT NULL,
            hold_id TEXT,
            booking_code TEXT,
            expires_at REAL,
            PRIMARY KEY(screening, seat)
        );
        CREATE INDEX IF NOT EXISTS idx_seats_user ON seats(user_id);
        """)


def _expire_holds(db):
    db.execute("DELETE FROM seats WHERE status='PENDING' AND expires_at <= ?", (time.time(),))


def _response(ok=True, message="", **data):
    return {"ok": ok, "message": message, **data}


class ReservationService:
    """All reservation state is accessed by TCP server worker threads."""
    def handle(self, request):
        op = request.get("op")
        if op == "GET_SEATS":
            return self.get_seats(request["screening"], request["user_id"])
        if op == "CREATE_HOLD":
            return self.create_hold(request["screening"], request["seat"], request["user_id"])
        if op == "PAY_HOLD":
            return self.pay_hold(request["hold"], request["user_id"])
        if op == "RELEASE_HOLD":
            return self.release_hold(request["hold"], request["user_id"])
        if op == "RESERVATIONS":
            return self.reservations(request["user_id"])
        if op == "CANCEL_RESERVATION":
            return self.cancel_reservation(request["screening"], request["seat"], request["code"], request["user_id"])
        return _response(False, "알 수 없는 TCP 명령입니다.")

    def get_seats(self, screening, user_id):
        with _connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _expire_holds(db)
            rows = db.execute("SELECT * FROM seats WHERE screening=?", (screening,)).fetchall()
            db.commit()
        by_seat = {r["seat"]: r for r in rows}
        result = []
        for row in ROWS:
            for col in range(1, COLUMNS + 1):
                seat = f"{row}{col}"
                item = by_seat.get(seat)
                if item is None:
                    result.append({"seat": seat, "status": "AVAILABLE"})
                else:
                    result.append({
                        "seat": seat,
                        "status": item["status"],
                        "mine": item["user_id"] == user_id,
                        "remaining": max(0, int(item["expires_at"] - time.time() + .999))
                        if item["status"] == "PENDING" else None,
                    })
        return _response(seats=result)

    def create_hold(self, screening, seat, user_id):
        with _connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _expire_holds(db)
            exists = db.execute(
                "SELECT 1 FROM seats WHERE screening=? AND seat=?", (screening, seat)
            ).fetchone()
            if exists:
                db.rollback()
                return _response(False, "이미 다른 사용자가 선택했거나 예약한 좌석입니다.")
            hold_id = secrets.token_urlsafe(18)
            expires = time.time() + HOLD_SECONDS
            db.execute(
                "INSERT INTO seats VALUES (?, ?, 'PENDING', ?, ?, NULL, ?)",
                (screening, seat, user_id, hold_id, expires),
            )
            db.commit()
        return _response(True, "좌석을 5분간 임시 점유했습니다.", hold={
            "screening": screening, "seat": seat, "hold_id": hold_id, "expires_at": expires
        })

    def pay_hold(self, hold, user_id):
        with _connect() as db:
            db.execute("BEGIN IMMEDIATE")
            _expire_holds(db)
            row = db.execute(
                "SELECT * FROM seats WHERE screening=? AND seat=?",
                (hold["screening"], hold["seat"]),
            ).fetchone()
            if (not row or row["status"] != "PENDING" or row["user_id"] != user_id
                    or row["hold_id"] != hold["hold_id"]):
                db.rollback()
                return _response(False, "임시 점유가 만료되었거나 유효하지 않습니다.")
            code = secrets.token_urlsafe(9).upper()
            db.execute("""UPDATE seats SET status='RESERVED', hold_id=NULL,
                          booking_code=?, expires_at=NULL WHERE screening=? AND seat=?""",
                       (code, hold["screening"], hold["seat"]))
            db.commit()
        return _response(True, "모의 결제가 완료되어 예매가 확정되었습니다.", code=code)

    def release_hold(self, hold, user_id):
        with _connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""DELETE FROM seats WHERE screening=? AND seat=? AND status='PENDING'
                          AND user_id=? AND hold_id=?""",
                       (hold["screening"], hold["seat"], user_id, hold["hold_id"]))
            changed = db.execute("SELECT changes()").fetchone()[0]
            db.commit()
        return _response(released=(changed == 1))

    def reservations(self, user_id):
        with _connect() as db:
            rows = db.execute("""SELECT screening, seat, booking_code FROM seats
                              WHERE user_id=? AND status='RESERVED' ORDER BY screening, seat""",
                              (user_id,)).fetchall()
        return _response(reservations=[dict(row) for row in rows])

    def cancel_reservation(self, screening, seat, code, user_id):
        with _connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""DELETE FROM seats WHERE screening=? AND seat=? AND status='RESERVED'
                          AND user_id=? AND booking_code=?""",
                       (screening, seat, user_id, code))
            changed = db.execute("SELECT changes()").fetchone()[0]
            db.commit()
        return _response(cancelled=(changed == 1))


class TCPHandler(socketserver.StreamRequestHandler):
    """One TCP connection = one request, handled in a dedicated worker thread."""
    def handle(self):
        try:
            raw = self.rfile.readline(MAX_FRAME + 1)
            if not raw or len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
                result = _response(False, "잘못된 TCP 메시지 형식입니다.")
            else:
                request = json.loads(raw.decode("utf-8"))
                if not isinstance(request, dict):
                    result = _response(False, "JSON 객체가 필요합니다.")
                else:
                    result = self.server.service.handle(request)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            result = _response(False, f"요청 형식 오류: {exc}")
        except Exception:
            result = _response(False, "예약 서버 내부 오류가 발생했습니다.")
        try:
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8") + b"\n")
            self.wfile.flush()
        except OSError:
            pass


class ThreadedReservationTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, address=("127.0.0.1", 0)):
        self.service = ReservationService()
        super().__init__(address, TCPHandler)


class ServerRuntime:
    """Starts the TCP listener once per Streamlit Python process."""
    def __init__(self):
        init_database()
        self.server = ThreadedReservationTCPServer()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True,
                                       name="cinema-tcp-acceptor")
        self.thread.start()
        self.address = self.server.server_address

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def tcp_request(address, op, **fields):
    payload = json.dumps({"op": op, **fields}, ensure_ascii=False).encode("utf-8") + b"\n"
    with __import__("socket").create_connection(address, timeout=10) as sock:
        sock.settimeout(10)
        sock.sendall(payload)
        stream = sock.makefile("rb")
        raw = stream.readline(MAX_FRAME + 1)
        if not raw or len(raw) > MAX_FRAME:
            raise ConnectionError("TCP 예약 서버의 응답이 없거나 너무 큽니다.")
        result = json.loads(raw.decode("utf-8"))
    if not result.get("ok", True):
        return result
    return result
