"""UDP 랑데부 서버 (홀펀칭 보조).

디바이스가 UDP로 register하면 그 패킷의 src 주소(reflexive UDP 주소)를 학습하고,
connect 요청 시 같은 사용자의 두 디바이스에게 서로의 reflexive 주소 + punch 신호를
교환한다. 토큰은 access JWT를 decode_token으로 검증하며, 같은 user_id 디바이스
간에만 중개한다(전송 보안 모델 일관). 데이터는 다루지 않는다(주소/식별자만 —
zero-knowledge 유지).

메시지는 UDP 위의 JSON 한 패킷:
- {"op":"register","token":..,"device_id":..} → {"op":"registered","reflexive":"ip:port"}
- {"op":"connect","token":..,"device_id":..,"peer":peer_id}
    요청자에게 {"op":"peer","addr":"ip:port"}, peer에게 {"op":"punch","addr":"ip:port"}
    peer 미등록/타 사용자면 요청자에게 {"op":"peer_unavailable"}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

# 등록 항목이 이보다 오래되면(초) 중개 대상에서 제외한다.
REGISTRATION_TTL_SECONDS = 120.0


class RendezvousProtocol(asyncio.DatagramProtocol):
    """UDP 랑데부 프로토콜. reflexive 주소 학습 + 같은 사용자 디바이스 중개."""

    def __init__(self, verify_token: Callable[[str], str | None]) -> None:
        self._verify = verify_token
        # device_id -> {"addr": (ip, port), "user_id": uid, "ts": monotonic}
        self._registry: dict[str, dict] = {}
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(msg, dict):
            return

        user_id = self._verify(msg.get("token", ""))
        if user_id is None:
            self._send(addr, {"op": "error", "error": "unauthorised"})
            return

        op = msg.get("op")
        if op == "register":
            self._handle_register(addr, msg, user_id)
        elif op == "connect":
            self._handle_connect(addr, msg, user_id)

    def _handle_register(
        self, addr: tuple[str, int], msg: dict, user_id: str
    ) -> None:
        device_id = msg.get("device_id")
        if not device_id:
            return
        self._registry[device_id] = {
            "addr": addr, "user_id": user_id, "ts": time.monotonic(),
        }
        self._send(addr, {"op": "registered", "reflexive": _fmt(addr)})

    def _handle_connect(
        self, addr: tuple[str, int], msg: dict, user_id: str
    ) -> None:
        device_id = msg.get("device_id")
        peer_id = msg.get("peer")
        # 요청자 주소를 최신화(refresh)한다.
        if device_id:
            self._registry[device_id] = {
                "addr": addr, "user_id": user_id, "ts": time.monotonic(),
            }
        peer = self._registry.get(peer_id)
        if (
            peer is None
            or peer["user_id"] != user_id
            or (time.monotonic() - peer["ts"]) > REGISTRATION_TTL_SECONDS
        ):
            # 같은 사용자의 온라인 디바이스만 중개한다.
            self._send(addr, {"op": "peer_unavailable"})
            return
        peer_addr = peer["addr"]
        # 요청자에게 peer 주소를, peer에게는 punch 신호 + 요청자 주소를 보낸다.
        self._send(addr, {"op": "peer", "addr": _fmt(peer_addr)})
        self._send(
            peer_addr,
            {"op": "punch", "addr": _fmt(addr), "peer": device_id},
        )

    def _send(self, addr: tuple[str, int], obj: dict) -> None:
        if self.transport is not None:
            self.transport.sendto(json.dumps(obj).encode("utf-8"), addr)


def _fmt(addr: tuple[str, int]) -> str:
    return f"{addr[0]}:{addr[1]}"


class RendezvousServer:
    """UDP 랑데부 서버 라이프사이클 래퍼."""

    def __init__(
        self, host: str, port: int, verify_token: Callable[[str], str | None]
    ) -> None:
        self._host = host
        self._port = port
        self._verify = verify_token
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: RendezvousProtocol | None = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: RendezvousProtocol(self._verify),
            local_addr=(self._host, self._port),
        )
        logger.info("Rendezvous(UDP) 서버 시작: %s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            self._protocol = None
            logger.info("Rendezvous(UDP) 서버 중지")

    @property
    def port(self) -> int:
        """실제 바인딩된 포트(0으로 시작 시 OS 할당값)."""
        if self._transport is not None:
            return self._transport.get_extra_info("sockname")[1]
        return self._port
