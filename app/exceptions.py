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
