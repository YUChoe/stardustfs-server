"""P2P 릴레이 허브 (메모리 기반 long-polling 중계).

직접 P2P 연결이 불가능한 두 디바이스(이중 NAT/CGNAT) 간에 P2P 작업을 서버가
중계한다. 모든 트래픽이 outbound HTTP이므로 NAT 종류와 무관하게 동작한다.

서버는 payload/result를 불투명 blob으로 중계하며 해석하거나 영속화하지 않는다
(파일 데이터는 클라이언트에서 master_key로 이미 암호화된 암호문).

단일 uvicorn 워커 + 메모리 큐 가정(데모/검증 범위). 다중 워커 확장은 외부 큐
(Redis 등)가 필요하며 범위 밖이다.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RelayMessage:
    """대상 디바이스에게 전달할 릴레이 요청."""

    request_id: str
    op: str
    payload: dict
    requester_device_id: str | None = None


@dataclass
class RelayHub:
    """디바이스별 요청 큐와 요청별 응답 Future를 관리하는 메모리 허브."""

    # device_id -> 그 디바이스 앞으로 온 요청 큐
    _inbox: dict[str, asyncio.Queue] = field(default_factory=dict)
    # request_id -> 요청자가 기다리는 응답 Future
    _pending: dict[str, asyncio.Future] = field(default_factory=dict)

    def _get_inbox(self, device_id: str) -> asyncio.Queue:
        """디바이스 inbox 큐를 가져오거나 생성한다."""
        queue = self._inbox.get(device_id)
        if queue is None:
            queue = asyncio.Queue()
            self._inbox[device_id] = queue
        return queue

    async def submit(
        self,
        target_device_id: str,
        op: str,
        payload: dict,
        requester_device_id: str | None = None,
    ) -> str:
        """요청을 대상 inbox에 적재하고 응답 Future를 등록한다.

        Returns:
            발급된 request_id.
        """
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        self._pending[request_id] = loop.create_future()
        message = RelayMessage(
            request_id=request_id,
            op=op,
            payload=payload,
            requester_device_id=requester_device_id,
        )
        await self._get_inbox(target_device_id).put(message)
        logger.info(
            f"Relay request queued: id={request_id} target={target_device_id} op={op}"
        )
        return request_id

    async def poll(
        self, device_id: str, timeout: float
    ) -> RelayMessage | None:
        """디바이스 inbox에서 요청을 하나 꺼낸다 (long-poll).

        timeout 내 요청이 없으면 None을 반환한다.

        asyncio.wait_for(queue.get())는 타임아웃 시 내부 get 태스크를 취소하는데,
        취소 직전 항목이 dequeue되면 유실될 수 있다. get을 명시적 태스크로 관리해
        타임아웃 시에도 이미 꺼낸 항목은 잃지 않도록 한다.
        """
        queue = self._get_inbox(device_id)
        getter = asyncio.ensure_future(queue.get())
        try:
            return await asyncio.wait_for(asyncio.shield(getter), timeout=timeout)
        except asyncio.TimeoutError:
            # 타임아웃: shield는 wait_for만 취소하고 getter는 계속 살아있다.
            # getter가 그사이 항목을 받았으면 유실하지 않고 반환하고,
            # 아직 대기 중이면 취소해 큐의 orphan waiter를 제거한다.
            # (done() 확인과 cancel() 사이에 await가 없어 원자적이다)
            if getter.done() and not getter.cancelled() and getter.exception() is None:
                return getter.result()
            getter.cancel()
            return None

    async def deliver(self, request_id: str, response: dict) -> bool:
        """대상이 올린 응답을 대기 중인 요청자 Future에 전달한다.

        Returns:
            전달 성공 여부 (해당 request_id의 대기자가 없으면 False).
        """
        future = self._pending.get(request_id)
        if future is None or future.done():
            logger.warning(
                f"Relay deliver: no pending waiter for id={request_id}"
            )
            return False
        future.set_result(response)
        logger.info(f"Relay response delivered: id={request_id}")
        return True

    async def wait_response(
        self, request_id: str, timeout: float
    ) -> dict | None:
        """요청자가 응답 Future를 기다린다 (long-poll).

        timeout 내 응답이 없으면 None을 반환한다. 어떤 경우든 Future를 정리한다.
        """
        future = self._pending.get(request_id)
        if future is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            # 응답 수령 또는 타임아웃 후 정리
            if future.done():
                self._pending.pop(request_id, None)

    def discard(self, request_id: str) -> None:
        """대기 중인 요청을 정리한다."""
        self._pending.pop(request_id, None)
