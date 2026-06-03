"""UDP 랑데부 서버 테스트 (홀펀칭 보조).

실제 UDP 소켓으로 register/connect 왕복을 검증한다. 토큰 검증은 주입한 fake로
대체해 같은 사용자 중개/타 사용자 거부/미인증 거부를 확인한다.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.rendezvous import RendezvousServer


class _Client:
    """테스트용 UDP 클라이언트(한 디바이스의 소켓)."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.transport = None

    async def open(self) -> None:
        loop = asyncio.get_running_loop()
        proto = self

        class _P(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                proto.transport = transport

            def datagram_received(self, data, addr):
                proto.queue.put_nowait((data, addr))

        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: _P(), local_addr=("127.0.0.1", 0)
        )

    @property
    def addr(self):
        return self.transport.get_extra_info("sockname")

    def send(self, server_addr, obj: dict) -> None:
        self.transport.sendto(json.dumps(obj).encode("utf-8"), server_addr)

    async def recv(self, timeout: float = 2.0) -> dict:
        data, _addr = await asyncio.wait_for(self.queue.get(), timeout)
        return json.loads(data.decode("utf-8"))

    def close(self) -> None:
        if self.transport:
            self.transport.close()


def _verifier(mapping: dict[str, str]):
    """token → user_id 매핑(없으면 None=미인증)."""
    return lambda token: mapping.get(token)


@pytest.fixture
async def server():
    # 같은 사용자 u1의 토큰 t1/t2, 다른 사용자 u2의 t3
    verify = _verifier({"t1": "u1", "t2": "u1", "t3": "u2"})
    srv = RendezvousServer("127.0.0.1", 0, verify)
    await srv.start()
    yield srv
    await srv.stop()


@pytest.mark.asyncio
async def test_register_returns_reflexive(server):
    c = _Client()
    await c.open()
    server_addr = ("127.0.0.1", server.port)
    c.send(server_addr, {"op": "register", "token": "t1", "device_id": "d1"})
    msg = await c.recv()
    assert msg["op"] == "registered"
    assert msg["reflexive"] == f"{c.addr[0]}:{c.addr[1]}"
    c.close()


@pytest.mark.asyncio
async def test_connect_exchanges_addresses_and_punch(server):
    server_addr = ("127.0.0.1", server.port)
    a, b = _Client(), _Client()
    await a.open()
    await b.open()
    # 두 디바이스(같은 사용자) 등록
    a.send(server_addr, {"op": "register", "token": "t1", "device_id": "da"})
    assert (await a.recv())["op"] == "registered"
    b.send(server_addr, {"op": "register", "token": "t2", "device_id": "db"})
    assert (await b.recv())["op"] == "registered"

    # a가 b로 connect 요청 → a는 peer 주소, b는 punch 신호 수신
    a.send(server_addr, {"op": "connect", "token": "t1",
                         "device_id": "da", "peer": "db"})
    a_msg = await a.recv()
    assert a_msg["op"] == "peer"
    assert a_msg["addr"] == f"{b.addr[0]}:{b.addr[1]}"

    b_msg = await b.recv()
    assert b_msg["op"] == "punch"
    assert b_msg["addr"] == f"{a.addr[0]}:{a.addr[1]}"
    assert b_msg["peer"] == "da"
    a.close()
    b.close()


@pytest.mark.asyncio
async def test_connect_rejects_other_user_peer(server):
    server_addr = ("127.0.0.1", server.port)
    a, b = _Client(), _Client()
    await a.open()
    await b.open()
    # a=u1, b=u2(다른 사용자)
    a.send(server_addr, {"op": "register", "token": "t1", "device_id": "da"})
    await a.recv()
    b.send(server_addr, {"op": "register", "token": "t3", "device_id": "db"})
    await b.recv()

    a.send(server_addr, {"op": "connect", "token": "t1",
                         "device_id": "da", "peer": "db"})
    msg = await a.recv()
    assert msg["op"] == "peer_unavailable"
    a.close()
    b.close()


@pytest.mark.asyncio
async def test_unauthorised_token_rejected(server):
    c = _Client()
    await c.open()
    server_addr = ("127.0.0.1", server.port)
    c.send(server_addr, {"op": "register", "token": "bogus", "device_id": "d1"})
    msg = await c.recv()
    assert msg["op"] == "error"
    assert msg["error"] == "unauthorised"
    c.close()


@pytest.mark.asyncio
async def test_connect_unregistered_peer_unavailable(server):
    c = _Client()
    await c.open()
    server_addr = ("127.0.0.1", server.port)
    c.send(server_addr, {"op": "register", "token": "t1", "device_id": "da"})
    await c.recv()
    c.send(server_addr, {"op": "connect", "token": "t1",
                         "device_id": "da", "peer": "ghost"})
    msg = await c.recv()
    assert msg["op"] == "peer_unavailable"
    c.close()
