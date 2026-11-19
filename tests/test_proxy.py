import asyncio

from app.proxy import start_tcp_proxy


def test_tcp_proxy_forwards_bytes():
    async def run() -> None:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            data = await reader.read(1024)
            writer.write(b"PONG:" + data)
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        backend = await asyncio.start_server(handle, "127.0.0.1", 0)
        backend_port = backend.sockets[0].getsockname()[1]
        proxy = await start_tcp_proxy("127.0.0.1", 0, "127.0.0.1", backend_port)
        proxy_port = proxy.sockets[0].getsockname()[1]
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
            writer.write(b"ping")
            await writer.drain()
            resp = await reader.read(1024)
            writer.close()
            await writer.wait_closed()
        finally:
            proxy.close()
            await proxy.wait_closed()
            backend.close()
            await backend.wait_closed()
        assert resp == b"PONG:ping"

    asyncio.run(run())
