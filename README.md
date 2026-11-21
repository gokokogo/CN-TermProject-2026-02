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

## Streamlit Community Cloud 배포
1. GitHub에 새 **Private repository**를 만듭니다.
2. 이 폴더의 `app.py`, `requirements.txt`, `README.md`를 저장소 루트에 올립니다.
3. https://share.streamlit.io/ 에서 GitHub로 로그인합니다.
4. Create app을 선택하고 저장소, 브랜치(`main`), 파일 경로(`app.py`)를 지정해 배포합니다.
5. 배포 후 App settings의 Sharing에서 `Only specific people can view this app`으로 설정하고 시연자 이메일을 초대합니다.
6. 초대받은 사람은 이메일 링크 또는 지원되는 로그인 방식으로 앱을 열 수 있습니다. 앱 내부의 회원가입/로그인은 별도로 진행합니다.

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
