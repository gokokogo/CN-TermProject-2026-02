# CINEMA Reservation Application

## 구성
app.py: 홈페이지 UI 및 예매 기능

reservation_server.py: TCP 서버 및 예약 처리

cinema_demo.db: 예약 정보 관리

## 주요 기능
- 회원가입 및 로그인 (비밀번호는 PBKDF2 해시로 저장)
- 영화/상영 시간 선택
- 좌석 현황 실시간 갱신
- 5분 임시 점유(pending)
- 모의 결제 후 예매 확정
- 예매 내역 조회 및 취소
- DB 트랜잭션으로 같은 좌석의 동시 중복 점유 방지

## 중요: 시연용 저장소 주의
간단한 시연을 위해 SQLite DB를 사용하였기 때문에, 재배포, 리부트 시 기존 데이터가 초기화될 수 있습니다.
