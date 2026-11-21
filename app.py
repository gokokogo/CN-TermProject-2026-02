import time
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from reservation_server import ServerRuntime, tcp_request

st.set_page_config(page_title="CINEMA | 영화 예매", page_icon="🎬", layout="wide")

HOLD_SECONDS = 300
ROWS = "ABCDE"
COLUMNS = 8

MOVIES = [
    {"title": "폭설", "genre": "Drama · Mystery", "minutes": 89,
     "image": "https://cdn.cgv.co.kr/cgvpomsfilm/Movie/Thumbnail/Poster/030001/30001643/30001643_320.jpg",
     "screenings": [{"id": "B1", "time": "14:00"}, {"id": "B2", "time": "19:30"}]},
    {"title": "치이카와", "genre": "Animation", "minutes": 90,
     "image": "https://image.starnewskorea.com/cdn-cgi/image/f%3Dauto%2Cw%3D1200%2Ch%3D1715%2Cfit%3Dcover%2Cq%3Dhigh%2Csharpen%3D2/21/2026/10/2026100107233725467_1.jpg",
     "screenings": [{"id": "C1", "time": "16:30"}, {"id": "C2", "time": "21:00"}]},
    {"title": "라라랜드", "genre": "Musical · Romance", "minutes": 128,
     "image": "https://cdn.cgv.co.kr/cgvpomsfilm/Movie/Thumbnail/StillCut/000085/85672/85672200257_727.jpg",
     "screenings": [{"id": "L1", "time": "13:00"}, {"id": "L2", "time": "18:00"}]},
]

st.markdown("""
<style>
.main .block-container {max-width: 1100px; padding-top: 1.8rem;}
.screen {text-align:center; padding:9px; margin:12px auto 24px; max-width:75%;
 border:1px solid #aaa; border-radius:50% 50% 8px 8px; color:gray; letter-spacing:5px;}
.seat-legend {display:flex; gap:18px; flex-wrap:wrap; margin:10px 0 18px;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_tcp_runtime():
    return ServerRuntime()


_tcp_runtime = get_tcp_runtime()
TCP_ADDRESS = _tcp_runtime.address


def rpc(op, **fields):
    result = tcp_request(TCP_ADDRESS, op, **fields)
    if not result.get("ok", True):
        return result
    return result


def get_seats(screening, user_id):
    result = rpc("GET_SEATS", screening=screening, user_id=user_id)
    if not result.get("ok", True):
        raise RuntimeError(result.get("message", "좌석 조회 실패"))
    return result["seats"]


def create_hold(screening, seat, user_id):
    result = rpc("CREATE_HOLD", screening=screening, seat=seat, user_id=user_id)
    return result.get("ok", False), result.get("message", ""), result.get("hold")


def pay_hold(hold, user_id):
    result = rpc("PAY_HOLD", hold=hold, user_id=user_id)
    return result.get("ok", False), result.get("message", ""), result.get("code")


def release_hold(hold, user_id):
    result = rpc("RELEASE_HOLD", hold=hold, user_id=user_id)
    return result.get("released", False)


def reservations(user_id):
    result = rpc("RESERVATIONS", user_id=user_id)
    if not result.get("ok", True):
        raise RuntimeError(result.get("message", "예매 내역 조회 실패"))
    return result["reservations"]


def cancel_reservation(screening, seat, code, user_id):
    result = rpc("CANCEL_RESERVATION", screening=screening, seat=seat,
                 code=code, user_id=user_id)
    return result.get("cancelled", False)


def screening_label(screening):
    for movie in MOVIES:
        for show in movie["screenings"]:
            if show["id"] == screening:
                return f'{movie["title"]} · {show["time"]}'
    return screening


defaults = {
    "user": None, "hold": None, "selected_movie": MOVIES[0]["title"],
    "selected_screening": MOVIES[0]["screenings"][0]["id"],
    "selected_seat": None, "last_booking": None, "page": "영화 선택",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

st_autorefresh(interval=1000, key="cinema_refresh")

def movie_by_screening(screening):
    for m in MOVIES:
        for s in m["screenings"]:
            if s["id"] == screening:
                return m, s
    return MOVIES[0], MOVIES[0]["screenings"][0]

def go(page):
    st.session_state.page = page
    st.rerun()

with st.sidebar:
    st.title("🎬 CINEMA")
    st.caption("MOVIE SEAT RESERVATION")
    st.divider()
    if st.session_state.user:
        st.success(f'{st.session_state.user["id"]}님으로 이용 중')
        if st.button("사용자 변경 / 로그아웃", use_container_width=True):
            if st.session_state.hold:
                release_hold(st.session_state.hold, st.session_state.user["id"])
            st.session_state.user = None
            st.session_state.hold = None
            st.session_state.page = "영화 선택"
            st.rerun()
    st.divider()
    pages = ["영화 선택", "좌석 선택", "결제 대기", "나의 예매 내역"]
    page_choice = st.radio(
        "페이지 이동",
        pages,
        index=pages.index(st.session_state.page),
    )
    # 페이지 이동용 radio는 별도의 위젯 상태를 사용합니다.
    # st.session_state.page를 radio의 key로 직접 연결하면 버튼에서 go()가
    # 페이지 값을 바꿀 때 이미 생성된 위젯 상태와 충돌할 수 있습니다.
    if page_choice != st.session_state.page:
        st.session_state.page = page_choice
        st.rerun()
    st.caption("결제: 시뮬레이션")
    st.caption("임시 좌석 점유: 5분")
    st.caption("통신: TCP Socket · Thread-per-connection")

st.title("🎬 CINEMA")
st.caption("원하는 영화를 선택하고 좌석을 예매하세요.")

if not st.session_state.user:
    with st.form("user_id_form"):
        uid = st.text_input("사용자 아이디", placeholder="예: student01").strip()
        submit = st.form_submit_button("입장하기", type="primary", use_container_width=True)
    if submit:
        if not uid:
            st.error("아이디를 입력해주세요.")
        elif len(uid) > 30:
            st.error("아이디는 30자 이하로 입력해주세요.")
        else:
            st.session_state.user = {"id": uid, "name": uid}
            st.rerun()
    st.info("시연용 간편 입장입니다. 다른 사람과 겹치지 않는 아이디를 사용해주세요.")
    st.stop()

user_id = st.session_state.user["id"]
st.subheader(f'{st.session_state.user["name"]}님, 환영합니다!')
selected_screening = st.session_state.selected_screening
movie_for_show, show_for_show = movie_by_screening(selected_screening)

if st.session_state.page == "영화 선택":
    st.header("1. 영화 및 상영 시간 선택")
    st.write("관람할 영화를 선택해주세요.")
    cols = st.columns(3)
    for i, movie in enumerate(MOVIES):
        with cols[i]:
            st.image(movie["image"], use_container_width=True)
            st.markdown(f'**{movie["title"]}**')
            st.caption(f'{movie["genre"]} · {movie["minutes"]}분')
            if st.button("선택됨 ✓" if st.session_state.selected_movie == movie["title"] else "선택하기",
                         key=f'movie_{i}', use_container_width=True,
                         type="primary" if st.session_state.selected_movie == movie["title"] else "secondary"):
                st.session_state.selected_movie = movie["title"]
                st.session_state.selected_screening = movie["screenings"][0]["id"]
                st.rerun()

    movie = next(m for m in MOVIES if m["title"] == st.session_state.selected_movie)
    st.divider()
    st.subheader("상영 시간 선택")
    left, right = st.columns([1, 2])
    with left:
        st.image(movie["image"], use_container_width=True)
    with right:
        st.markdown(f'### {movie["title"]}')
        st.caption(f'{movie["genre"]} · {movie["minutes"]}분')
        for show in movie["screenings"]:
            if st.button(f'🕒 {show["time"]} 상영', key=f'show_{show["id"]}',
                         type="primary" if st.session_state.selected_screening == show["id"] else "secondary",
                         use_container_width=True):
                st.session_state.selected_screening = show["id"]
                st.rerun()
        current = next(s for s in movie["screenings"] if s["id"] == st.session_state.selected_screening)
        st.success(f'선택한 상영 시간: {current["time"]}')
    if st.button("다음: 좌석 선택 →", type="primary", use_container_width=True):
        st.session_state.selected_seat = None
        go("좌석 선택")

elif st.session_state.page == "좌석 선택":
    st.header("2. 좌석 선택")
    st.image(movie_for_show["image"], width=150)
    st.markdown(f'**{movie_for_show["title"]}** · {show_for_show["time"]}')
    st.caption("좌석을 하나 선택한 뒤 다음 단계로 이동하세요.")
    st.markdown('<div class="screen">SCREEN</div>', unsafe_allow_html=True)
    st.markdown('<div class="seat-legend"><span>🟩 선택 가능</span><span>🟨 결제 대기</span><span>🟥 예매 완료</span></div>', unsafe_allow_html=True)
    seat_data = get_seats(selected_screening, user_id)
    for row in ROWS:
        cols = st.columns(COLUMNS)
        for col_idx in range(COLUMNS):
            seat = f"{row}{col_idx+1}"
            item = next(x for x in seat_data if x["seat"] == seat)
            status = item["status"]
            if status == "AVAILABLE":
                label, disabled = f"🟩 {seat}", bool(st.session_state.hold)
            elif status == "PENDING":
                label, disabled = (f"🟨 {seat}" if item.get("mine") else f"⏳ {seat}"), True
            else:
                label, disabled = f"🟥 {seat}", True
            if st.session_state.selected_seat == seat and status == "AVAILABLE":
                label = f"🔵 {seat}"
            with cols[col_idx]:
                if st.button(label, key=f"seat_{selected_screening}_{seat}",
                             disabled=disabled, use_container_width=True):
                    st.session_state.selected_seat = seat
                    st.rerun()
    if st.session_state.selected_seat:
        st.info(f'선택한 좌석: **{st.session_state.selected_seat}**')
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← 이전 단계", use_container_width=True):
            go("영화 선택")
    with c2:
        if st.button("다음: 결제 대기 →", type="primary",
                     disabled=not st.session_state.selected_seat, use_container_width=True):
            ok, message, hold = create_hold(selected_screening, st.session_state.selected_seat, user_id)
            if ok:
                st.session_state.hold = hold
                go("결제 대기")
            else:
                st.error(message)
                st.rerun()

elif st.session_state.page == "결제 대기":
    st.header("3. 결제 대기")
    hold = st.session_state.hold
    if not hold:
        st.warning("현재 결제 대기 중인 예매가 없습니다. 영화를 선택하고 좌석을 예약해주세요.")
        if st.button("영화 선택으로 이동", type="primary"):
            go("영화 선택")
    else:
        movie, show = movie_by_screening(hold["screening"])
        remaining = max(0, int(hold["expires_at"] - time.time() + .999))
        with db_conn() as db:
            row = db.execute("""SELECT * FROM seats WHERE screening=? AND seat=? AND status='PENDING'
                                AND user_id=? AND hold_id=?""",
                             (hold["screening"], hold["seat"], user_id, hold["hold_id"])).fetchone()
        if not row or remaining <= 0:
            st.session_state.hold = None
            st.session_state.selected_seat = None
            st.error("임시 점유 시간이 만료되었습니다. 좌석을 다시 선택해주세요.")
        else:
            left, right = st.columns([1, 2])
            with left:
                st.image(movie["image"], use_container_width=True)
            with right:
                st.subheader(movie["title"])
                st.write(f'상영 시간: **{show["time"]}**')
                st.write(f'좌석 정보: **{hold["seat"]}**')
                st.write(f'사용자 ID: **{user_id}**')
                st.metric("결제 가능 남은 시간", f"{remaining // 60:02d}:{remaining % 60:02d}")
            st.warning("5분 안에 모의 결제를 완료해주세요. 시간이 지나면 좌석이 자동 반환됩니다.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💳 모의 결제하기", type="primary", use_container_width=True):
                    ok, message, code = pay_hold(hold, user_id)
                    if ok:
                        st.session_state.hold = None
                        st.session_state.last_booking = (hold["screening"], hold["seat"], code)
                        st.success(message)
                        go("나의 예매 내역")
                    else:
                        st.error(message)
                        st.session_state.hold = None
                        st.rerun()
            with c2:
                if st.button("예매 취소 및 좌석 반환", use_container_width=True):
                    release_hold(hold, user_id)
                    st.session_state.hold = None
                    st.session_state.selected_seat = None
                    go("영화 선택")

elif st.session_state.page == "나의 예매 내역":
    st.header("나의 예매 내역")
    if st.session_state.last_booking:
        screening, seat, code = st.session_state.last_booking
        st.success(f"최근 예매 완료: {screening_label(screening)} · {seat} · 예매번호 {code}")
    my_reservations = reservations(user_id)
    if not my_reservations:
        st.info("확정된 예매 내역이 없습니다.")
    else:
        for booking in my_reservations:
            movie, show = movie_by_screening(booking["screening"])
            with st.container(border=True):
                a, b = st.columns([1, 3])
                with a:
                    st.image(movie["image"], use_container_width=True)
                with b:
                    st.subheader(movie["title"])
                    st.write(f'상영 시간: **{show["time"]}**')
                    st.write(f'좌석: **{booking["seat"]}**')
                    st.write(f'예매번호: `{booking["booking_code"]}`')
                    if st.button("예매 취소", key=f'cancel_{booking["screening"]}_{booking["seat"]}'):
                        if cancel_reservation(booking["screening"], booking["seat"],
                                              booking["booking_code"], user_id):
                            st.success("예매가 취소되었습니다.")
                        st.rerun()

st.divider()
