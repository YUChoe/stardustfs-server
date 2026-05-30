# Python 개발 환경 규칙

## 프로젝트 환경
- Python 3.13
- 가상환경: `mud_engine_env`
- 메인 모듈: `src.mud_engine.main`
- Telnet 포트: 4000 / 웹 포트: 8080 (레거시)
- src-layout 구조 (`src/mud_engine/`)

## 기본 원칙
- PEP8 준수, snake_case 네이밍
- 가상 환경 필수, `PYTHONPATH=.` 항상 포함
- Windows 환경에서 Git Bash만 사용 (PowerShell/CMD 금지)
- 비동기 프로그래밍: `async/await` 패턴
- 리포지토리 패턴으로 DB 접근 추상화
- 이벤트 기반 아키텍처 (EventBus)
- 다국어 지원 (en/ko)
- 타입 힌트, enum 적극 활용
- 방어적 프로그래밍, 충분한 로깅

## 정적 검사 (실행 전 필수)
소스 수정 후 서버 실행 전에 mypy + ruff 모두 통과해야 함.

```bash
# mypy 타입 검사 (설정: setup.cfg [mypy])
source mud_engine_env/Scripts/activate && PYTHONPATH=. mypy src/

# ruff 린트 검사 (설정: pyproject.toml [tool.ruff])
source mud_engine_env/Scripts/activate && ruff check src/
```

에러가 있으면 실행 금지.

## 실행 명령어
```bash
# 서버 실행
source mud_engine_env/Scripts/activate && PYTHONPATH=. python -m src.mud_engine.main

# 테스트
source mud_engine_env/Scripts/activate && PYTHONPATH=. pytest

# 스크립트 (scripts/ 디렉토리)
./script_test.sh <스크립트명>
```

## 프로세스 관리
```bash
ps aux | grep python

# 서버 종료 시 반드시 SIGINT(signal 2) 사용 — 정상 종료 절차 수행을 위해
kill -2 <PID>
```
- `kill -9` (SIGKILL) 사용 금지: 서버의 graceful shutdown 핸들러가 실행되지 않음
- `kill -2` (SIGINT) = Ctrl+C와 동일, 서버가 정상 종료 절차를 수행함

## 서버 실행 상태 확인 (필수)
서버를 시작하기 전에 반드시 포트 4000이 이미 사용 중인지 확인할 것.
```bash
# bash 환경에서 포트 사용 확인
ss -tlnp 2>/dev/null | grep 4000 || netstat -an | grep 4000
```
- 포트가 사용 중이면 서버가 이미 실행 중인 것이므로 재시작하지 말 것
- controlPwshProcess로 시작한 서버는 대화 컨텍스트가 바뀌면 terminalId를 잃으므로, 포트 체크로 실행 여부를 판단할 것

## 금지사항
- PowerShell, CMD 사용
- 전역 Python 환경 사용
- 서비스 포트 변경 (프로세스 종료로 해결)
- mypy 또는 ruff 에러 무시하고 실행
