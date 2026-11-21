# CINEMA Reservation Application

## 구성
cinema_demo.db: 영화 상영 정보, 좌석 예약 및 결제 상태 등의 데이터를 저장하는 SQLite 데이터베이스 파일

reservation_server.py: SQLite DB에 접근해 예약 생성, 조회, 결제, 취소 등의 작업을 처리하는 TCP 서버

app.py: 사용자가 홈페이지에서 영화와 좌석을 선택하고 예약 기능을 이용하는 Streamlit 화면

## 주요 기능
- 로그인
- 영화/상영 시간 선택
- 좌석 현황 실시간 갱신
- 5분 임시 점유(pending)
- 모의 결제 후 예매 확정
- 예매 내역 조회 및 취소
- DB 트랜잭션으로 같은 좌석의 동시 중복 점유 방지

## 중요: 시연용 저장소 주의
간단한 시연을 위해 SQLite DB를 사용하였기 때문에, 재배포, 리부트 시 기존 데이터가 초기화될 수 있습니다.
