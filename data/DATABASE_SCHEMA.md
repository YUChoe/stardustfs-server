# StardustFS Central Server - Database Schema

데이터베이스: `data/stardustfs.db` (SQLite, WAL 모드)

스키마 정의 위치: `app/database.py`의 `SCHEMA_SQL`

## 테이블

### users
사용자 계정.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | TEXT | PK, 기본값 lower(hex(randomblob(16))) | 사용자 ID |
| email | TEXT | NOT NULL, UNIQUE | 이메일 |
| password_hash | TEXT | | bcrypt 해시 (OAuth 전용 계정은 NULL) |
| oauth_provider | TEXT | | google / github 등 |
| oauth_id | TEXT | | OAuth 제공자 측 사용자 ID |
| created_at | TEXT | NOT NULL, 기본값 datetime('now') | 생성 시각 |

### devices
사용자 디바이스 레지스트리.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | TEXT | PK, 기본값 lower(hex(randomblob(16))) | 디바이스 ID |
| user_id | TEXT | NOT NULL, FK users(id) ON DELETE CASCADE | 소유자 |
| name | TEXT | NOT NULL | 디바이스 이름 |
| os | TEXT | NOT NULL | OS 정보 |
| connection_address | TEXT | NOT NULL | P2P 접속 주소 (IP:port) |
| last_heartbeat | TEXT | NOT NULL, 기본값 datetime('now') | 마지막 heartbeat |
| is_online | INTEGER | NOT NULL, 기본값 1 | 온라인 여부 |
| created_at | TEXT | NOT NULL, 기본값 datetime('now') | 생성 시각 |

인덱스: `idx_devices_user_id (user_id)`

### metadata_backups
사용자별 암호화된 metadata DB blob 백업 (user_id당 1개 유지, version 기반 CAS).

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| user_id | TEXT | NOT NULL, FK users(id) ON DELETE CASCADE | 소유자 |
| encrypted_blob | BLOB | NOT NULL | AES-256-GCM 암호화된 metadata DB |
| version | INTEGER | NOT NULL, 기본값 1 | 낙관적 잠금(CAS) 버전 |
| uploaded_at | TEXT | NOT NULL, 기본값 datetime('now') | 업로드 시각 |

인덱스: `idx_metadata_backups_user_id (user_id)`, `idx_metadata_backups_user_version (user_id, version) UNIQUE`

### key_backups
사용자별 암호화된 master_key 백업 (user_id당 1개, upsert).

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| user_id | TEXT | NOT NULL, UNIQUE, FK users(id) ON DELETE CASCADE | 소유자 |
| encrypted_blob | BLOB | NOT NULL | PBKDF2+AES-256-GCM 암호화된 master_key |
| uploaded_at | TEXT | NOT NULL, 기본값 datetime('now') | 업로드 시각 |

### refresh_tokens
JWT refresh 토큰.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| user_id | TEXT | NOT NULL, FK users(id) ON DELETE CASCADE | 소유자 |
| token_hash | TEXT | NOT NULL, UNIQUE | 토큰 해시 |
| is_revoked | INTEGER | NOT NULL, 기본값 0 | 폐기 여부 |
| created_at | TEXT | NOT NULL, 기본값 datetime('now') | 생성 시각 |
| expires_at | TEXT | NOT NULL | 만료 시각 |

인덱스: `idx_refresh_tokens_user_id (user_id)`, `idx_refresh_tokens_token_hash (token_hash)`

### shares (MVP5)
파일 공유 토큰. 특정 디바이스의 특정 물리 경로 하나에 대한 읽기 전용 접근을 인가.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| token | TEXT | PK | secrets.token_urlsafe(32) 공유 토큰 |
| owner_user_id | TEXT | NOT NULL, FK users(id) ON DELETE CASCADE | 발급자(소유자) |
| device_id | TEXT | NOT NULL | 대상 디바이스 ID |
| physical_path | TEXT | NOT NULL | 공유 대상 물리 경로 (이 경로에만 접근 허용) |
| created_at | TEXT | NOT NULL, 기본값 datetime('now') | 발급 시각 |
| expires_at | TEXT | NOT NULL | 만료 시각 (ISO 8601) |

인덱스: `idx_shares_owner (owner_user_id)`

### hosting (리플리케이션)
디바이스별 제공/보관 용량 회계. 무료 사용자는 provided_bytes의 50%까지 타 사용자
복제 보관에 제공한다(상호 보관 한도). zero-knowledge: 용량 숫자만 보관.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| device_id | TEXT | PK, FK devices(id) ON DELETE CASCADE | 디바이스 |
| provided_bytes | INTEGER | NOT NULL, 기본값 0 | 신고한 제공 용량 |
| hosted_bytes | INTEGER | NOT NULL, 기본값 0 | 현재 타 사용자 보관 중인 합 |
| updated_at | TEXT | NOT NULL, 기본값 datetime('now') | 갱신 시각 |

### chunks (리플리케이션)
암호문 청크의 위치 레지스트리(소유자/크기 메타데이터만, 내용 미보관).

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| chunk_id | TEXT | PK | 클라이언트 생성 청크 식별자 |
| owner_user_id | TEXT | NOT NULL, FK users(id) ON DELETE CASCADE | 소유자 |
| file_ref | TEXT | NOT NULL | 불투명 파일 참조(경로 비노출) |
| idx | INTEGER | NOT NULL | 파일 내 청크 인덱스 |
| size | INTEGER | NOT NULL | 청크 크기(바이트) |
| created_at | TEXT | NOT NULL, 기본값 datetime('now') | 생성 시각 |

인덱스: `idx_chunks_owner (owner_user_id)`, `idx_chunks_file (owner_user_id, file_ref)`

### replicas (리플리케이션)
청크별 홀더(복제본 보관 디바이스) 매핑.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| chunk_id | TEXT | NOT NULL, FK chunks(chunk_id) ON DELETE CASCADE | 대상 청크 |
| holder_device_id | TEXT | NOT NULL, FK devices(id) ON DELETE CASCADE | 보관 디바이스 |
| status | TEXT | NOT NULL, 기본값 'active' | active/stale |
| updated_at | TEXT | NOT NULL, 기본값 datetime('now') | 갱신 시각 |

제약: `UNIQUE(chunk_id, holder_device_id)`. 인덱스: `idx_replicas_chunk (chunk_id)`,
`idx_replicas_holder (holder_device_id)`

마이그레이션: 위 3개 테이블은 `CREATE TABLE IF NOT EXISTS`(init_db)로 추가되는
신규 테이블이며 기존 데이터에 영향이 없다(추가형, 별도 백업/롤백 불필요).
