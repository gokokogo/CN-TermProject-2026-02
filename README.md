# CINEMA - Streamlit Community Cloud 배포용

## 구성
- `app.py`: Streamlit 홈페이지와 예매 서버 기능을 한 앱으로 통합
- `requirements.txt`: 배포 시 설치할 패키지
- `cinema_demo.db`: 실행 시 자동 생성되는 SQLite 데이터베이스 (저장소에 올리지 않음)

## 로컬 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 주요 기능
- 회원가입 및 로그인 (비밀번호는 PBKDF2 해시로 저장)
- 영화/상영 시간 선택
- 좌석 현황 실시간 갱신
- 5분 임시 점유(pending)
- 모의 결제 후 예매 확정
- 예매 내역 조회 및 취소
- DB 트랜잭션으로 같은 좌석의 동시 중복 점유 방지

## 중요: 시연용 저장소 주의
이 버전은 간편한 수업 시연을 위해 SQLite 파일을 앱 폴더에 저장합니다. Streamlit Community Cloud의 로컬 파일시스템은 영구 저장소로 보장되지 않으므로 앱 재시작, 재배포 또는 재부팅 시 회원/예매 데이터가 초기화될 수 있습니다. 데이터 보존이 필요하면 Supabase 등 외부 PostgreSQL 데이터베이스로 변경해야 합니다.

실제 결제, 실제 개인정보 처리, 상용 서비스 보안 기능은 포함하지 않습니다.
