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
source .venv/Scripts/activate  # Windows Git Bash
pip install -r requirements.txt
pip install -e ".[dev]"
```

## 실행

```bash
cp .env.example .env
# .env 파일에서 STARDUST_JWT_SECRET_KEY 설정
uvicorn app.main:app --reload
```

## 테스트

```bash
pytest
```
