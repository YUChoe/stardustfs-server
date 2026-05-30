# Requirements Document

## Introduction

StardustFS Central Server는 멀티디바이스 환경에서 사용자 인증, 디바이스 관리, 메타데이터/키 백업, 디바이스 라우팅을 제공하는 중앙 서버이다. FastAPI + SQLite 기반으로 구현되며, 실제 파일 데이터는 클라이언트 간 P2P로 전송하고 서버는 제어 평면(control plane)만 담당한다.

## Glossary

- **Central_Server**: FastAPI 기반 중앙 서버 애플리케이션. 인증, 디바이스 관리, 동기화 백업, 라우팅 기능을 제공한다.
- **User**: Central_Server에 가입한 사용자 계정. 이메일과 비밀번호 또는 OAuth로 인증한다.
- **Device**: User가 등록한 클라이언트 장치. 이름, OS, 접속 주소를 가진다.
- **Access_Token**: JWT 형식의 단기 인증 토큰. 15분 만료.
- **Refresh_Token**: Access_Token 갱신을 위한 장기 토큰. 회전(rotation) 방식으로 관리된다.
- **Metadata_Backup**: 클라이언트의 metadata_db를 HKDF 파생 키로 암호화한 불투명 blob. 서버는 복호화 불가.
- **Key_Backup**: 클라이언트의 master key를 사용자 비밀번호(PBKDF2 + AES-256-GCM)로 2차 암호화한 blob. 서버는 복호화 불가.
- **Heartbeat**: 디바이스가 주기적으로 서버에 전송하는 온라인 상태 및 접속 주소 갱신 요청.
- **Connection_Address**: 디바이스의 현재 IP 주소와 포트 조합. P2P 연결에 사용된다.
- **OAuth_Provider**: Google 또는 GitHub 등 외부 인증 제공자.

## Requirements

### 요구사항 1: 이메일/비밀번호 회원가입

**사용자 스토리:** 사용자로서, 이메일과 비밀번호로 계정을 생성하고 싶다. 그래야 Central_Server의 기능을 이용할 수 있다.

#### 인수 조건

1. WHEN 유효한 이메일과 비밀번호가 제출되면, THE Central_Server SHALL 새 User 레코드를 생성하고 201 응답을 반환한다.
2. WHEN 이미 등록된 이메일로 가입을 시도하면, THE Central_Server SHALL 409 Conflict 응답을 반환한다.
3. THE Central_Server SHALL 비밀번호를 bcrypt로 해싱하여 저장한다.
4. WHEN 이메일 형식이 유효하지 않으면, THE Central_Server SHALL 422 응답과 함께 검증 오류 메시지를 반환한다.
5. WHEN 비밀번호가 8자 미만이면, THE Central_Server SHALL 422 응답과 함께 검증 오류 메시지를 반환한다.

### 요구사항 2: 로그인 및 JWT 발급

**사용자 스토리:** 사용자로서, 이메일과 비밀번호로 로그인하여 Access_Token을 받고 싶다. 그래야 인증이 필요한 API를 호출할 수 있다.

#### 인수 조건

1. WHEN 올바른 이메일과 비밀번호가 제출되면, THE Central_Server SHALL Access_Token과 Refresh_Token을 발급하여 반환한다.
2. WHEN 존재하지 않는 이메일로 로그인을 시도하면, THE Central_Server SHALL 401 Unauthorized 응답을 반환한다.
3. WHEN 비밀번호가 일치하지 않으면, THE Central_Server SHALL 401 Unauthorized 응답을 반환한다.
4. THE Central_Server SHALL Access_Token의 만료 시간을 15분으로 설정한다.
5. THE Central_Server SHALL Access_Token에 user_id 클레임을 포함한다.

### 요구사항 3: OAuth 로그인

**사용자 스토리:** 사용자로서, Google 또는 GitHub 계정으로 로그인하고 싶다. 그래야 별도 비밀번호 없이 편리하게 인증할 수 있다.

#### 인수 조건

1. WHEN 유효한 OAuth 인증 코드와 provider 이름이 제출되면, THE Central_Server SHALL OAuth_Provider에서 사용자 정보를 조회하고 Access_Token과 Refresh_Token을 발급한다.
2. WHEN OAuth로 처음 로그인하는 사용자이면, THE Central_Server SHALL 새 User 레코드를 자동 생성한다.
3. WHEN 이미 동일 이메일로 가입된 User가 존재하면, THE Central_Server SHALL 기존 계정에 OAuth 정보를 연결한다.
4. WHEN 지원하지 않는 provider가 요청되면, THE Central_Server SHALL 400 Bad Request 응답을 반환한다.
5. WHEN OAuth_Provider로부터 인증 실패 응답을 받으면, THE Central_Server SHALL 401 Unauthorized 응답을 반환한다.

### 요구사항 4: 토큰 갱신

**사용자 스토리:** 사용자로서, 만료된 Access_Token을 Refresh_Token으로 갱신하고 싶다. 그래야 재로그인 없이 서비스를 계속 이용할 수 있다.

#### 인수 조건

1. WHEN 유효한 Refresh_Token이 제출되면, THE Central_Server SHALL 새 Access_Token과 새 Refresh_Token을 발급한다.
2. WHEN 만료된 Refresh_Token이 제출되면, THE Central_Server SHALL 401 Unauthorized 응답을 반환한다.
3. WHEN 이미 사용된 Refresh_Token이 제출되면, THE Central_Server SHALL 401 Unauthorized 응답을 반환하고 해당 User의 모든 Refresh_Token을 무효화한다.
4. THE Central_Server SHALL 새 Refresh_Token 발급 시 이전 Refresh_Token을 무효화한다 (토큰 회전).

### 요구사항 5: 디바이스 등록

**사용자 스토리:** 사용자로서, 내 장치를 서버에 등록하고 싶다. 그래야 다른 디바이스에서 이 장치를 찾아 P2P 연결할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 디바이스 이름, OS, Connection_Address를 제출하면, THE Central_Server SHALL 새 Device 레코드를 생성하고 device_id를 반환한다.
2. WHEN 디바이스 이름이 비어있으면, THE Central_Server SHALL 422 응답을 반환한다.
3. THE Central_Server SHALL 생성된 Device의 is_online 상태를 true로 설정한다.
4. THE Central_Server SHALL 생성된 Device의 last_heartbeat를 현재 시각으로 설정한다.

### 요구사항 6: 디바이스 목록 조회

**사용자 스토리:** 사용자로서, 내가 등록한 모든 디바이스 목록을 조회하고 싶다. 그래야 어떤 장치가 등록되어 있고 온라인인지 확인할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 디바이스 목록을 요청하면, THE Central_Server SHALL 해당 User의 모든 Device 정보를 반환한다.
2. THE Central_Server SHALL 각 Device의 id, name, os, connection_address, is_online, last_heartbeat를 포함하여 반환한다.
3. THE Central_Server SHALL 다른 User의 Device 정보를 반환하지 않는다.

### 요구사항 7: 디바이스 제거

**사용자 스토리:** 사용자로서, 더 이상 사용하지 않는 디바이스를 제거하고 싶다. 그래야 디바이스 목록을 깔끔하게 유지할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 자신의 Device 삭제를 요청하면, THE Central_Server SHALL 해당 Device 레코드를 삭제하고 204 응답을 반환한다.
2. WHEN 존재하지 않는 device_id로 삭제를 요청하면, THE Central_Server SHALL 404 Not Found 응답을 반환한다.
3. WHEN 다른 User의 Device 삭제를 요청하면, THE Central_Server SHALL 403 Forbidden 응답을 반환한다.

### 요구사항 8: 디바이스 Heartbeat

**사용자 스토리:** 사용자로서, 내 디바이스의 온라인 상태와 접속 주소를 주기적으로 갱신하고 싶다. 그래야 다른 디바이스가 정확한 연결 정보를 얻을 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 자신의 Device에 heartbeat를 전송하면, THE Central_Server SHALL last_heartbeat를 현재 시각으로 갱신하고 is_online을 true로 설정한다.
2. WHEN heartbeat에 새 Connection_Address가 포함되면, THE Central_Server SHALL Device의 connection_address를 갱신한다.
3. WHEN 다른 User의 Device에 heartbeat를 전송하면, THE Central_Server SHALL 403 Forbidden 응답을 반환한다.
4. WHILE Device의 last_heartbeat가 5분 이상 경과하면, THE Central_Server SHALL 해당 Device의 is_online을 false로 간주한다.

### 요구사항 9: 메타데이터 백업 업로드

**사용자 스토리:** 사용자로서, 암호화된 metadata_db를 서버에 업로드하고 싶다. 그래야 다른 디바이스에서 메타데이터를 복원할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 암호화된 blob을 업로드하면, THE Central_Server SHALL Metadata_Backup 레코드를 생성하고 version을 증가시킨다.
2. THE Central_Server SHALL 업로드된 blob을 불투명 데이터로 저장하며 복호화를 시도하지 않는다.
3. WHEN 업로드 요청의 body가 비어있으면, THE Central_Server SHALL 422 응답을 반환한다.

### 요구사항 10: 메타데이터 백업 다운로드

**사용자 스토리:** 사용자로서, 서버에 저장된 최신 metadata_db를 다운로드하고 싶다. 그래야 새 디바이스에서 메타데이터를 복원할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 메타데이터 다운로드를 요청하면, THE Central_Server SHALL 해당 User의 최신 Metadata_Backup blob을 반환한다.
2. WHEN 해당 User의 Metadata_Backup이 존재하지 않으면, THE Central_Server SHALL 404 Not Found 응답을 반환한다.
3. THE Central_Server SHALL 응답에 version 정보를 헤더 또는 메타데이터로 포함한다.

### 요구사항 11: 암호화 키 백업 업로드

**사용자 스토리:** 사용자로서, 2차 암호화된 master key를 서버에 백업하고 싶다. 그래야 새 디바이스에서 키를 복원할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 암호화된 key blob을 업로드하면, THE Central_Server SHALL Key_Backup 레코드를 생성 또는 갱신한다.
2. THE Central_Server SHALL 업로드된 key blob을 불투명 데이터로 저장하며 복호화를 시도하지 않는다.
3. WHEN 업로드 요청의 body가 비어있으면, THE Central_Server SHALL 422 응답을 반환한다.

### 요구사항 12: 암호화 키 백업 다운로드

**사용자 스토리:** 사용자로서, 서버에 저장된 암호화된 master key를 다운로드하고 싶다. 그래야 새 디바이스에서 비밀번호로 복호화하여 사용할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 키 다운로드를 요청하면, THE Central_Server SHALL 해당 User의 Key_Backup blob을 반환한다.
2. WHEN 해당 User의 Key_Backup이 존재하지 않으면, THE Central_Server SHALL 404 Not Found 응답을 반환한다.

### 요구사항 13: 디바이스 라우팅 조회

**사용자 스토리:** 사용자로서, 특정 디바이스의 현재 접속 주소를 조회하고 싶다. 그래야 해당 디바이스에 P2P 연결을 시도할 수 있다.

#### 인수 조건

1. WHEN 인증된 User가 자신의 Device에 대한 라우팅 정보를 요청하면, THE Central_Server SHALL 해당 Device의 connection_address와 is_online 상태를 반환한다.
2. WHEN 요청된 Device가 존재하지 않으면, THE Central_Server SHALL 404 Not Found 응답을 반환한다.
3. WHEN 다른 User의 Device 라우팅 정보를 요청하면, THE Central_Server SHALL 403 Forbidden 응답을 반환한다.
4. WHILE 요청된 Device의 is_online이 false이면, THE Central_Server SHALL 응답에 오프라인 상태임을 명시한다.

### 요구사항 14: 인증 미들웨어

**사용자 스토리:** 개발자로서, 보호된 엔드포인트에 일관된 인증 검증을 적용하고 싶다. 그래야 인증되지 않은 접근을 차단할 수 있다.

#### 인수 조건

1. WHEN Access_Token이 없는 요청이 보호된 엔드포인트에 도달하면, THE Central_Server SHALL 401 Unauthorized 응답을 반환한다.
2. WHEN 만료된 Access_Token이 포함된 요청이 도달하면, THE Central_Server SHALL 401 Unauthorized 응답을 반환한다.
3. WHEN 서명이 유효하지 않은 Access_Token이 포함된 요청이 도달하면, THE Central_Server SHALL 401 Unauthorized 응답을 반환한다.
4. THE Central_Server SHALL Authorization 헤더의 Bearer 스킴으로 Access_Token을 수신한다.

### 요구사항 15: 데이터베이스 스키마

**사용자 스토리:** 개발자로서, 명확한 데이터베이스 스키마를 정의하고 싶다. 그래야 데이터 무결성을 보장하고 효율적으로 쿼리할 수 있다.

#### 인수 조건

1. THE Central_Server SHALL users 테이블에 id, email, password_hash, created_at, oauth_provider, oauth_id 컬럼을 포함한다.
2. THE Central_Server SHALL devices 테이블에 id, user_id, name, os, connection_address, last_heartbeat, is_online, created_at 컬럼을 포함한다.
3. THE Central_Server SHALL metadata_backups 테이블에 id, user_id, encrypted_blob, version, uploaded_at 컬럼을 포함한다.
4. THE Central_Server SHALL key_backups 테이블에 id, user_id, encrypted_blob, uploaded_at 컬럼을 포함한다.
5. THE Central_Server SHALL email 컬럼에 UNIQUE 제약 조건을 적용한다.
6. THE Central_Server SHALL devices.user_id에 users.id를 참조하는 외래 키 제약 조건을 적용한다.

### 요구사항 16: 랜딩 페이지

**사용자 스토리:** 방문자로서, StardustFS 서비스의 소개 페이지를 보고 싶다. 그래야 서비스의 기능을 이해하고 가입을 결정할 수 있다.

#### 인수 조건

1. WHEN 브라우저로 루트 경로(/)에 접근하면, THE Central_Server SHALL HTML 랜딩 페이지를 반환한다.
2. THE Central_Server SHALL 랜딩 페이지에 서비스 소개, 주요 기능 설명, 가입/로그인 링크를 포함한다.
3. THE Central_Server SHALL 랜딩 페이지를 정적 파일(HTML/CSS/JS)로 서빙한다.
4. WHEN 인증되지 않은 사용자가 랜딩 페이지에 접근하면, THE Central_Server SHALL 인증 없이 페이지를 제공한다.
5. THE Central_Server SHALL 랜딩 페이지에서 회원가입 페이지와 로그인 페이지로의 네비게이션을 제공한다.
