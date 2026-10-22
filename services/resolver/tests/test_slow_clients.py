import asyncio
import time

import pytest
import uvicorn

from resolver.presentation.body_limit import BodySizeLimitMiddleware
from resolver.presentation.slow_clients import guarded_protocol

TIMEOUT = 0.4
REQUEST = b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n"


async def hello(scope, receive, send):
    if scope["type"] != "http":
        return
    await send(
        {"type": "http.response.start", "status": 200, "headers": [(b"content-length", b"2")]}
    )
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.fixture
async def port():
    config = uvicorn.Config(
        hello,
        host="127.0.0.1",
        port=0,
        http=guarded_protocol(TIMEOUT, max_per_client=50),
        lifespan="off",
        log_level="warning",
        timeout_keep_alive=5,
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    yield server.servers[0].sockets[0].getsockname()[1]
    server.should_exit = True
    await task


async def closed_within(reader, seconds):
    try:
        return await asyncio.wait_for(reader.read(1024), seconds) == b""
    except TimeoutError:
        return False


async def test_a_silent_connection_is_closed(port):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    assert await closed_within(reader, TIMEOUT * 4)
    writer.close()


async def test_headers_sent_too_slowly_get_the_connection_closed(port):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"GET /health HTTP/1.1\r\nHost: x\r\nX-Slow: ")
    await writer.drain()

    assert await closed_within(reader, TIMEOUT * 4)
    writer.close()


async def test_trickling_bytes_does_not_extend_the_deadline(port):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    started = time.monotonic()
    writer.write(b"GET /health HTTP/1.1\r\n")
    closed = False
    for _ in range(40):
        try:
            writer.write(b"X")
            await writer.drain()
        except (ConnectionError, OSError):
            closed = True
            break
        if reader.at_eof():
            closed = True
            break
        await asyncio.sleep(0.1)
    elapsed = time.monotonic() - started

    assert closed or await closed_within(reader, 1)
    assert elapsed < TIMEOUT * 6
    writer.close()


async def test_a_complete_request_is_served_and_the_connection_can_be_reused(port):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    for _ in range(3):
        writer.write(REQUEST)
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
        body = await asyncio.wait_for(reader.readexactly(2), 2)
        assert response.startswith(b"HTTP/1.1 200") and body == b"ok"
        await asyncio.sleep(TIMEOUT * 1.5)
    writer.close()


async def test_a_partial_second_request_on_a_kept_alive_connection_is_also_cut(port):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(REQUEST)
    await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
    await reader.readexactly(2)

    writer.write(b"GET /health HTTP/1.1\r\nHost: x\r\nX-Slow: ")
    await writer.drain()

    assert await closed_within(reader, TIMEOUT * 4)
    writer.close()


async def test_hundreds_of_slow_connections_do_not_block_a_legitimate_client(port):
    slow = []
    for _ in range(300):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /health HTTP/1.1\r\nHost: x\r\nX-Slow: ")
        slow.append((reader, writer))

    reader, writer = await asyncio.open_connection("127.0.0.1", port, local_addr=("127.0.0.2", 0))
    writer.write(REQUEST)
    await writer.drain()
    answer = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
    closed = await asyncio.gather(*(closed_within(r, TIMEOUT * 6) for r, _ in slow))

    assert answer.startswith(b"HTTP/1.1 200")
    assert all(closed)
    for _, w in slow:
        w.close()
    writer.close()


async def test_body_that_arrives_too_slowly_gets_a_408():
    sent = []

    async def reads_body(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def never_arrives():
        await asyncio.sleep(60)

    async def collect(message):
        sent.append(message)

    middleware = BodySizeLimitMiddleware(reads_body, max_bytes=1000, body_timeout=0.2)
    scope = {"type": "http", "headers": [], "path": "/"}

    await asyncio.wait_for(middleware(scope, never_arrives, collect), 3)

    assert sent[0]["status"] == 408


async def test_body_timeout_does_not_affect_requests_that_arrive_in_time():
    sent = []

    async def echo(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def quick():
        return {"type": "http.request", "body": b"hola", "more_body": False}

    async def collect(message):
        sent.append(message)

    middleware = BodySizeLimitMiddleware(echo, max_bytes=1000, body_timeout=1.0)

    await middleware({"type": "http", "headers": [], "path": "/"}, quick, collect)

    assert sent[0]["status"] == 200


@pytest.fixture
async def capped_port():
    config = uvicorn.Config(
        hello,
        host="127.0.0.1",
        port=0,
        http=guarded_protocol(30, max_per_client=10),
        lifespan="off",
        log_level="warning",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    yield server.servers[0].sockets[0].getsockname()[1]
    server.should_exit = True
    await task


async def open_slow(port, count, source="127.0.0.1"):
    connections = []
    for _ in range(count):
        reader, writer = await asyncio.open_connection("127.0.0.1", port, local_addr=(source, 0))
        writer.write(b"GET /health HTTP/1.1\r\nHost: x\r\nX-Slow: ")
        connections.append((reader, writer))
    return connections


async def test_a_client_cannot_hold_more_connections_than_its_cap(capped_port):
    connections = await open_slow(capped_port, 60)
    await asyncio.sleep(0.3)

    closed = [await closed_within(reader, 0.2) for reader, _ in connections]

    assert sum(closed) == 50
    assert not any(closed[:10])
    for _, writer in connections:
        writer.close()


async def test_another_client_is_unaffected_while_one_client_hits_its_cap(capped_port):
    attacker = await open_slow(capped_port, 60)
    await asyncio.sleep(0.2)

    reader, writer = await asyncio.open_connection(
        "127.0.0.1", capped_port, local_addr=("127.0.0.2", 0)
    )
    writer.write(REQUEST)
    await writer.drain()
    answer = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)

    assert answer.startswith(b"HTTP/1.1 200")
    writer.close()
    for _, w in attacker:
        w.close()


async def test_the_cap_is_released_when_connections_close(capped_port):
    for _ in range(3):
        connections = await open_slow(capped_port, 10)
        for _, writer in connections:
            writer.close()
        await asyncio.sleep(0.3)

    reader, writer = await asyncio.open_connection("127.0.0.1", capped_port)
    writer.write(REQUEST)
    await writer.drain()

    assert (await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)).startswith(b"HTTP/1.1 200")
    writer.close()
