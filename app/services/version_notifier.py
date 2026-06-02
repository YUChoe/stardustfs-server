"""메타데이터 version 변경 알림 (롱폴링용, in-memory).

user_id별로 metadata version 증가를 대기 중인 롱폴러에게 통지한다. 단일 uvicorn
워커를 가정한다(RelayHub와 동일 전제). 다중 워커 확장은 외부 pub/sub가 필요하며
범위 밖이다.

이벤트는 "변경이 있었다"는 신호일 뿐이며, 실제 판정은 호출자가 서버 version을 다시
조회하여 known_version과 비교한다. 따라서 set/clear 경합이나 알림 누락이 있어도
정확성은 version 비교로 보장된다(누락 시 호출자의 주기적 재확인으로 보정).
"""
from __future__ import annotations

import asyncio


class VersionNotifier:
    """user_id별 version 변경 통지 허브."""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def _event(self, user_id: str) -> asyncio.Event:
        """user_id의 Event를 가져오거나 생성한다."""
        event = self._events.get(user_id)
        if event is None:
            event = asyncio.Event()
            self._events[user_id] = event
        return event

    def notify(self, user_id: str) -> None:
        """해당 사용자의 대기자를 모두 깨운다 (엣지 트리거).

        set으로 대기자를 깨운 뒤, 다음 사이클을 위해 새 Event로 교체한다.
        교체 방식이라 깨어난 대기자는 기존 Event 객체를 참조하므로 set 상태가
        유지되어 안전하게 반환된다.
        """
        event = self._events.get(user_id)
        if event is not None:
            event.set()
        # 다음 대기 사이클을 위해 새 Event로 교체
        self._events[user_id] = asyncio.Event()

    async def wait(self, user_id: str, timeout: float) -> bool:
        """버전 변경 알림을 timeout까지 대기한다.

        Returns:
            알림을 받으면 True, 타임아웃이면 False.
        """
        event = self._event(user_id)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
