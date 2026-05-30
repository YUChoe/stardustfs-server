# Implementation Plan: MVP2 Central Server

## Overview

StardustFS Central Server를 FastAPI + SQLite 기반으로 구현한다. 프로젝트 초기 설정부터 시작하여 핵심 모듈, 인증, 디바이스 관리, 동기화, 라우팅, 랜딩 페이지 순서로 점진적으로 구축한다.

## Tasks

- [ ] 1. 프로젝트 초기 설정
  - [ ] 1.1 프로젝트 구조 및 의존성 설정
    - `requirements.txt` 생성 (fastapi, uvicorn, aiosqlite, python-jose[cryptography], passlib[bcrypt], authlib, httpx, pydantic[email-validator], pydantic-settings, jinja2, python-multipart)
    - `pyproject.toml` 생성 (pytest, pytest-asyncio, httpx, hypothesis 개발 의존성 포함)
    - 디렉토리 구조 생성: `app/`, `app/routers/`, `app/services/`, `static/`, `templates/`, `tests/`
    - 각 패키지에 `__init__.py` 생성
    - _Requirements: 15.1~15.6_

  - [ ] 1.2 설정 및 데이터베이스 모듈 구현
    - `app/config.py`: pydantic-settings 기반 Settings 클래스 (JWT 시크릿, DB 경로, OAuth 설정, heartbeat 타임아웃)
    - `app/database.py`: aiosqlite 연결 관리, 스키마 초기화 (users, devices, metadata_backups, key_backups, refresh_tokens 테이블), 인덱스 및 제약 조건 포함
    - `.env.example` 생성 (환경변수 템플릿)
    - _Requirements: 15.1~15.6_

  - [ ] 1.3 보안 유틸리티 및 의존성 주입 구현
    - `app/security.py`: hash_password, verify_password (bcrypt), create_access_token, create_refresh_token, decode_token (python-jose)
    - `app/dependencies.py`: get_db (aiosqlite 연결 yield), get_current_user (Bearer 토큰 검증, user_id 추출)
    - `app/schemas.py`: 모든 Pydantic 요청/응답 모델 정의
    - 커스텀 예외 클래스 정의 (StardustException 및 하위 클래스)
    - _Requirements: 1.3, 2.4, 2.5, 14.1~14.4_

- [ ] 2. 인증 기능 구현
  - [ ] 2.1 인증 서비스 및 라우터 구현
    - `app/services/auth_service.py`: register (이메일 중복 검사 + bcrypt 해싱), login (비밀번호 검증)
    - `app/services/token_service.py`: create_token_pair (Access 15분 + Refresh), refresh_tokens (회전 + 재사용 감지 시 전체 무효화), revoke_all_tokens
    - `app/routers/auth.py`: POST /auth/register, POST /auth/login, POST /auth/refresh
    - Refresh Token은 SHA-256 해시로 DB 저장
    - _Requirements: 1.1~1.5, 2.1~2.5, 4.1~4.4_

  - [ ] 2.2 OAuth 로그인 구현
    - `app/services/oauth_service.py`: Google/GitHub 인증 코드 교환, 사용자 정보 조회 (authlib 사용)
    - `app/routers/auth.py`에 POST /auth/oauth/{provider} 추가
    - 신규 사용자 자동 생성, 기존 이메일 계정 연결 로직
    - 미지원 provider 400, 인증 실패 401 처리
    - _Requirements: 3.1~3.5_

  - [ ]* 2.3 인증 Property 테스트 작성
    - **Property 1: 비밀번호 해싱 라운드트립**
    - **Property 2: JWT 토큰 라운드트립**
    - **Property 3: 유효하지 않은 이메일 거부**
    - **Property 4: 짧은 비밀번호 거부**
    - **Property 5: 이메일 중복 가입 거부**
    - **Property 13: Refresh Token 회전 보안**
    - **Property 14: 인증 미들웨어 거부**
    - **Validates: Requirements 1.2~1.5, 2.4, 2.5, 4.3, 4.4, 14.1~14.3**

- [ ] 3. Checkpoint - 인증 기능 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 디바이스 관리 구현
  - [ ] 4.1 디바이스 서비스 및 라우터 구현
    - `app/services/device_service.py`: register_device (is_online=True, last_heartbeat=now), list_devices, delete_device (소유권 검증), heartbeat (last_heartbeat 갱신, connection_address 선택적 갱신), is_device_online (5분 타임아웃 판정)
    - `app/routers/devices.py`: GET /devices, POST /devices, DELETE /devices/{device_id}, PUT /devices/{device_id}/heartbeat
    - 소유권 불일치 시 403, 미존재 시 404 처리
    - _Requirements: 5.1~5.4, 6.1~6.3, 7.1~7.3, 8.1~8.4_

  - [ ]* 4.2 디바이스 Property 테스트 작성
    - **Property 6: 디바이스 등록 초기 상태**
    - **Property 7: 디바이스 목록 완전성 및 격리**
    - **Property 8: 디바이스 소유권 격리**
    - **Property 9: Heartbeat 갱신**
    - **Property 10: Heartbeat 타임아웃 판정**
    - **Validates: Requirements 5.1~5.4, 6.1~6.3, 7.3, 8.1~8.4, 13.3**

- [ ] 5. 동기화 기능 구현
  - [ ] 5.1 동기화 서비스 및 라우터 구현
    - `app/services/sync_service.py`: upload_metadata (version 증가), download_metadata (최신 blob + version), upload_key (upsert), download_key
    - `app/routers/sync.py`: PUT /sync/metadata, GET /sync/metadata (X-Metadata-Version 헤더), PUT /sync/key, GET /sync/key
    - 빈 body 422, 백업 미존재 404 처리
    - blob은 application/octet-stream으로 송수신
    - _Requirements: 9.1~9.3, 10.1~10.3, 11.1~11.3, 12.1~12.2_

  - [ ]* 5.2 동기화 Property 테스트 작성
    - **Property 11: 메타데이터 백업 라운드트립**
    - **Property 12: 키 백업 라운드트립**
    - **Validates: Requirements 9.1~9.2, 10.1, 10.3, 11.1~11.2, 12.1**

- [ ] 6. 라우팅 기능 구현
  - [ ] 6.1 라우팅 라우터 구현
    - `app/routers/routing.py`: GET /routing/{device_id}
    - DeviceService.is_device_online 활용하여 실시간 온라인 상태 판정
    - 소유권 검증 (403), 미존재 (404), 오프라인 상태 명시
    - _Requirements: 13.1~13.4_

- [ ] 7. 랜딩 페이지 및 앱 통합
  - [ ] 7.1 랜딩 페이지 및 FastAPI 앱 조립
    - `templates/landing.html`: 서비스 소개, 주요 기능 설명, 가입/로그인 링크 포함 HTML
    - `static/` 디렉토리에 기본 CSS 배치
    - `app/routers/pages.py`: GET / (Jinja2 템플릿 렌더링, 인증 불필요)
    - `app/main.py`: FastAPI 앱 생성, 모든 라우터 등록, 전역 예외 핸들러, 정적 파일 마운트, lifespan 이벤트(DB 초기화)
    - _Requirements: 16.1~16.5_

- [ ] 8. Checkpoint - 전체 기능 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. 통합 테스트
  - [ ] 9.1 통합 테스트 및 conftest 작성
    - `tests/conftest.py`: 테스트용 인메모리 DB fixture, AsyncClient fixture, 인증 헬퍼 (테스트 사용자 생성 + 토큰 발급)
    - `tests/test_auth.py`: 회원가입 성공/중복/검증실패, 로그인 성공/실패, 토큰 갱신/재사용 감지
    - `tests/test_devices.py`: 디바이스 등록/목록/삭제/heartbeat, 소유권 격리
    - `tests/test_sync.py`: 메타데이터/키 업로드/다운로드, 빈 body 거부, 미존재 404
    - `tests/test_routing.py`: 라우팅 조회 성공/미존재/권한없음/오프라인
    - `tests/test_pages.py`: 랜딩 페이지 200 응답, HTML 콘텐츠 검증
    - _Requirements: 1~16 전체_

- [ ] 10. Final checkpoint - 최종 검증
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- `*` 표시된 태스크는 선택적이며 빠른 MVP를 위해 건너뛸 수 있음
- 각 태스크는 특정 요구사항을 참조하여 추적 가능성 보장
- Property 테스트는 hypothesis 라이브러리 사용, `@settings(max_examples=100)` 이상
- 통합 테스트는 httpx.AsyncClient + pytest-asyncio 사용
- OAuth 외부 호출은 테스트에서 mock 처리
- 로깅 포맷: `{HH:MM:SS.ms} {LEVEL} [{filename.py:line}] {message}`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["2.1", "4.1", "5.1"] },
    { "id": 4, "tasks": ["2.2", "6.1", "7.1"] },
    { "id": 5, "tasks": ["2.3", "4.2", "5.2"] },
    { "id": 6, "tasks": ["9.1"] }
  ]
}
```
