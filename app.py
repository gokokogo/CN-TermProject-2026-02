import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="CINEMA | 영화 예매", page_icon="🎬", layout="wide")

DB_PATH = Path(__file__).parent / "cinema_demo.db"
HOLD_SECONDS = 300
ROWS = "ABCDE"
COLUMNS = 8
MOVIES = [
    {"title": "Orbit Station", "genre": "SF", "minutes": 108,
     "screenings": [{"id": "O1", "time": "14:00"}, {"id": "O2", "time": "19:30"}]},
    {"title": "A Letter to Spring", "genre": "Drama", "minutes": 96,
     "screenings": [{"id": "L1", "time": "16:30"}, {"id": "L2", "time": "21:00"}]},
]

st.markdown("""
<style>
.main .block-container {max-width: 1100px; padding-top: 1.8rem;}
.screen {text-align:center; padding:9px; margin:12px auto 24px; max-width:75%;
 border:1px solid #aaa; border-radius:50% 50% 8px 8px; color:gray; letter-spacing:5px;}
.seat-grid {display:grid; grid-template-columns:repeat(8,minmax(0,1fr)); gap:7px;}
.seat-legend {display:flex; gap:18px; flex-wrap:wrap; margin:10px 0 18px;}
</style>
""", unsafe_allow_html=True)


@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=20, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=20000")
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
    finally:
        conn.close()


def init_db():
    with db_conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at REAL NOT NULL
        );
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
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_seats_user ON seats(user_id)")


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        candidate = password_hash(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def register(username, display_name, password):
    username, display_name = username.strip(), display_name.strip()
    if len(username) < 4 or len(username) > 24 or not username.replace("_", "").isalnum():
        return False, "아이디는 영문·숫자·밑줄로 4~24자 입력해주세요."
    if len(display_name) < 1 or len(display_name) > 40:
        return False, "이름을 1~40자로 입력해주세요."
    if len(password) < 8:
        return False, "비밀번호는 8자 이상이어야 합니다."
    try:
        with db_conn() as db:
            db.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                       (secrets.token_urlsafe(18), username, display_name,
                        password_hash(password), time.time()))
        return True, "회원가입이 완료되었습니다. 로그인해주세요."
    except sqlite3.IntegrityError:
        return False, "이미 사용 중인 아이디입니다."


def login(username, password):
    with db_conn() as db:
        user = db.execute("SELECT * FROM users WHERE username=?",
                          (username.strip(),)).fetchone()
    if user and verify_password(password, user["password_hash"]):
        return {"id": user["id"], "name": user["display_name"]}
    return None


def expire_holds(db):
    db.execute("DELETE FROM seats WHERE status='PENDING' AND expires_at <= ?", (time.time(),))


def get_seats(screening, user_id):
    with db_conn() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_holds(db)
        rows = db.execute("SELECT * FROM seats WHERE screening=?", (screening,)).fetchall()
        db.commit()
    by_seat = {r["seat"]: r for r in rows}
    result = []
    for row in ROWS:
        for col in range(1, COLUMNS + 1):
            seat = f"{row}{col}"
            item = by_seat.get(seat)
            if not item:
                result.append({"seat": seat, "status": "AVAILABLE"})
            else:
                result.append({
                    "seat": seat, "status": item["status"],
                    "mine": item["user_id"] == user_id,
                    "remaining": max(0, int(item["expires_at"] - time.time() + .999))
                    if item["status"] == "PENDING" else None
                })
    return result


def create_hold(screening, seat, user_id):
    with db_conn() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_holds(db)
        exists = db.execute("SELECT 1 FROM seats WHERE screening=? AND seat=?",
                            (screening, seat)).fetchone()
        if exists:
            db.rollback()
            return False, "이미 다른 사용자가 선택했거나 예약한 좌석입니다.", None
        hold_id = secrets.token_urlsafe(18)
        expires = time.time() + HOLD_SECONDS
        db.execute("INSERT INTO seats VALUES (?, ?, 'PENDING', ?, ?, NULL, ?)",
                   (screening, seat, user_id, hold_id, expires))
        db.commit()
    return True, "좌석을 5분간 임시 점유했습니다.", {"screening": screening, "seat": seat,
                                                    "hold_id": hold_id, "expires_at": expires}


def pay_hold(hold, user_id):
    with db_conn() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_holds(db)
        row = db.execute("""SELECT * FROM seats WHERE screening=? AND seat=?""",
                         (hold["screening"], hold["seat"])).fetchone()
        if not row or row["status"] != "PENDING" or row["user_id"] != user_id or row["hold_id"] != hold["hold_id"]:
            db.rollback()
            return False, "임시 점유가 만료되었거나 유효하지 않습니다.", None
        code = secrets.token_urlsafe(9).upper()
        db.execute("""UPDATE seats SET status='RESERVED', hold_id=NULL,
                      booking_code=?, expires_at=NULL
                      WHERE screening=? AND seat=?""",
                   (code, hold["screening"], hold["seat"]))
        db.commit()
    return True, "모의 결제가 완료되어 예매가 확정되었습니다.", code


def release_hold(hold, user_id):
    with db_conn() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""DELETE FROM seats WHERE screening=? AND seat=? AND status='PENDING'
                      AND user_id=? AND hold_id=?""",
                   (hold["screening"], hold["seat"], user_id, hold["hold_id"]))
        changed = db.execute("SELECT changes()").fetchone()[0]
        db.commit()
    return changed == 1


def reservations(user_id):
    with db_conn() as db:
        rows = db.execute("""SELECT screening, seat, booking_code FROM seats
                             WHERE user_id=? AND status='RESERVED'
                             ORDER BY screening, seat""", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def cancel_reservation(screening, seat, code, user_id):
    with db_conn() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""DELETE FROM seats WHERE screening=? AND seat=? AND status='RESERVED'
                      AND user_id=? AND booking_code=?""",
                   (screening, seat, user_id, code))
        changed = db.execute("SELECT changes()").fetchone()[0]
        db.commit()
    return changed == 1


def screening_label(screening):
    for movie in MOVIES:
        for show in movie["screenings"]:
            if show["id"] == screening:
                return f'{movie["title"]} · {show["time"]}'
    return screening


init_db()
defaults = {"user": None, "hold": None, "selected_screening": "O1", "notice": None}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

st_autorefresh(interval=2000, key="seat_refresh")

with st.sidebar:
    st.title("🎬 CINEMA")
    st.caption("MOVIE SEAT RESERVATION")
    st.divider()
    if st.session_state.user:
        st.success(f'{st.session_state.user["name"]}님 로그인 중')
        if st.button("로그아웃", use_container_width=True):
            if st.session_state.hold:
                release_hold(st.session_state.hold, st.session_state.user["id"])
            st.session_state.user = None
            st.session_state.hold = None
            st.rerun()
    else:
        st.caption("로그인 후 예매할 수 있습니다.")
    st.divider()
    st.caption("결제: 시뮬레이션")
    st.caption("임시 좌석 점유: 5분")

st.title("🎬 CINEMA")
st.caption("원하는 영화를 선택하고 좌석을 예매하세요.")

if not st.session_state.user:
    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])
    with tab_login:
        with st.form("login"):
            uid = st.text_input("아이디")
            pw = st.text_input("비밀번호", type="password")
            submit = st.form_submit_button("로그인", type="primary", use_container_width=True)
        if submit:
            account = login(uid, pw)
            if account:
                st.session_state.user = account
                st.rerun()
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
    with tab_signup:
        with st.form("signup"):
            name = st.text_input("이름")
            new_uid = st.text_input("아이디", help="영문·숫자·밑줄, 4~24자")
            new_pw = st.text_input("비밀번호", type="password", help="8자 이상")
            new_pw2 = st.text_input("비밀번호 확인", type="password")
            submit_signup = st.form_submit_button("회원가입", use_container_width=True)
        if submit_signup:
            if new_pw != new_pw2:
                st.error("비밀번호 확인이 일치하지 않습니다.")
            else:
                ok, message = register(new_uid, name, new_pw)
                (st.success if ok else st.error)(message)
    st.info("시연용 계정을 만든 뒤 로그인해주세요.")
    st.stop()

user_id = st.session_state.user["id"]
st.subheader(f'환영합니다, {st.session_state.user["name"]}님!')

if st.session_state.hold:
    hold = st.session_state.hold
    remaining = max(0, int(hold["expires_at"] - time.time() + .999))
    with db_conn() as db:
        row = db.execute("""SELECT * FROM seats WHERE screening=? AND seat=? AND status='PENDING'
                            AND user_id=? AND hold_id=?""",
                         (hold["screening"], hold["seat"], user_id, hold["hold_id"])).fetchone()
    if not row or remaining <= 0:
        st.session_state.hold = None
        st.warning("임시 점유 시간이 만료되었습니다. 좌석을 다시 선택해주세요.")
        st.rerun()
    with st.container(border=True):
        st.subheader("💳 결제 대기")
        st.write(f'선택 좌석: **{screening_label(hold["screening"])} / {hold["seat"]}**')
        st.metric("남은 시간", f"{remaining // 60:02d}:{remaining % 60:02d}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("모의 결제하기", type="primary", use_container_width=True):
                ok, message, code = pay_hold(hold, user_id)
                if ok:
                    st.session_state.hold = None
                    st.session_state.last_booking = (hold["screening"], hold["seat"], code)
                    st.success(message)
                else:
                    st.error(message)
                    st.session_state.hold = None
                st.rerun()
        with c2:
            if st.button("예매 취소 / 좌석 반환", use_container_width=True):
                release_hold(hold, user_id)
                st.session_state.hold = None
                st.rerun()

if "last_booking" in st.session_state and st.session_state.last_booking:
    screening, seat, code = st.session_state.last_booking
    st.success(f"예매 확정! {screening_label(screening)} · {seat} · 예매번호 {code}")
    if st.button("확인"):
        st.session_state.last_booking = None
        st.rerun()

st.divider()
st.subheader("영화 및 상영 시간 선택")
movie_names = [m["title"] for m in MOVIES]
movie_name = st.selectbox("영화", movie_names)
movie = next(m for m in MOVIES if m["title"] == movie_name)
show_options = {f'{s["time"]} ({s["id"]})': s["id"] for s in movie["screenings"]}
selected_label = st.selectbox("상영 시간", list(show_options))
screening = show_options[selected_label]
st.session_state.selected_screening = screening

st.subheader("좌석 선택")
st.markdown('<div class="screen">SCREEN</div>', unsafe_allow_html=True)
st.markdown("""
<div class="seat-legend">
<span>🟩 선택 가능</span><span>🟨 결제 대기</span><span>🟥 예매 완료</span>
</div>
""", unsafe_allow_html=True)

seat_data = get_seats(screening, user_id)
grid = st.columns(8)
for idx, item in enumerate(seat_data):
    seat = item["seat"]
    status = item["status"]
    if status == "AVAILABLE":
        label, disabled = f"🟩 {seat}", bool(st.session_state.hold)
    elif status == "PENDING":
        label, disabled = (f"🟨 {seat}" if item["mine"] else f"⏳ {seat}"), True
    else:
        label, disabled = f"🟥 {seat}", True
    with grid[idx % 8]:
        if st.button(label, key=f"seat_{screening}_{seat}", disabled=disabled,
                     use_container_width=True):
            ok, message, hold = create_hold(screening, seat, user_id)
            if ok:
                st.session_state.hold = hold
            else:
                st.warning(message)
            st.rerun()

st.divider()
st.subheader("나의 예매 내역")
my_reservations = reservations(user_id)
if not my_reservations:
    st.caption("확정된 예매 내역이 없습니다.")
else:
    for booking in my_reservations:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f'**{screening_label(booking["screening"])}**')
                st.write(f'좌석: {booking["seat"]} · 예매번호: `{booking["booking_code"]}`')
            with c2:
                if st.button("예매 취소", key=f'cancel_{booking["screening"]}_{booking["seat"]}'):
                    if cancel_reservation(booking["screening"], booking["seat"],
                                          booking["booking_code"], user_id):
                        st.success("예매가 취소되었습니다.")
                    st.rerun()
