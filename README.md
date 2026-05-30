# StardustFS Central Server

멀티디바이스 암호화 파일시스템을 위한 제어 평면(control plane) 서버.

## 기능

- 사용자 인증 (이메일/비밀번호, OAuth)
- JWT 기반 토큰 관리 (발급, 갱신, 회전)
- 디바이스 등록 및 온라인 상태 관리
- 암호화된 메타데이터/키 백업 저장
- 디바이스 라우팅 정보 제공
- 서비스 랜딩 페이지

## 기술 스택

- Python 3.9+
- FastAPI (ASGI)
- SQLite + aiosqlite
- python-jose (JWT)
- passlib[bcrypt] (비밀번호 해싱)
- authlib (OAuth)

## 설치

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# source .venv/Scripts/activate # Windows Git Bash
pip install -r requirements.txt
pip install -e ".[dev]"
```

## 설정

```bash
cp .env.example .env
```

`.env` 파일에서 필수 설정:
- `STARDUST_JWT_SECRET_KEY` — JWT 서명 키 (필수)
- `STARDUST_HOST` — 바인드 주소 (기본: 0.0.0.0)
- `STARDUST_PORT` — 바인드 포트 (기본: 8000)
- `STARDUST_DEBUG` — True이면 auto-reload 활성화

## 실행

```bash
# .env 설정을 읽어서 실행 (권장)
python main.py

# 또는 포트를 직접 지정
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## 테스트

```bash
pytest
```
