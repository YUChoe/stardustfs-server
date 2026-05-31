"""Custom exception classes for StardustFS Central Server."""
from __future__ import annotations


class StardustException(Exception):
    """기본 예외 클래스."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class DuplicateEmailError(StardustException):
    """이메일 중복 가입 시도."""

    def __init__(self) -> None:
        super().__init__(409, "Email already registered")


class InvalidCredentialsError(StardustException):
    """잘못된 자격증명."""

    def __init__(self) -> None:
        super().__init__(401, "Invalid credentials")


class DeviceNotFoundError(StardustException):
    """디바이스 미존재."""

    def __init__(self) -> None:
        super().__init__(404, "Device not found")


class DeviceAccessDeniedError(StardustException):
    """디바이스 접근 권한 없음."""

    def __init__(self) -> None:
        super().__init__(403, "Access denied to this device")


class TokenExpiredError(StardustException):
    """토큰 만료."""

    def __init__(self) -> None:
        super().__init__(401, "Token has expired")


class TokenInvalidError(StardustException):
    """유효하지 않은 토큰."""

    def __init__(self) -> None:
        super().__init__(401, "Invalid token")


class BackupNotFoundError(StardustException):
    """백업 데이터 미존재."""

    def __init__(self, backup_type: str) -> None:
        super().__init__(404, f"{backup_type} backup not found")


class MetadataVersionConflictError(StardustException):
    """메타데이터 낙관적 잠금(CAS) 충돌.

    클라이언트가 보낸 base version이 서버의 현재 version과 일치하지 않을 때
    발생한다. 다른 디바이스가 그 사이에 업로드했음을 의미한다.
    """

    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(
            409,
            f"Metadata version conflict: server is at version {current_version}",
        )


class ShareNotFoundError(StardustException):
    """공유 토큰 미존재."""

    def __init__(self) -> None:
        super().__init__(404, "Share not found")


class ShareExpiredError(StardustException):
    """공유 토큰 만료."""

    def __init__(self) -> None:
        super().__init__(410, "Share has expired")
