from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def start_tcp_proxy(listen_host: str, listen_port: int, target_host: str, target_port: int):
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            remote_reader, remote_writer = await asyncio.open_connection(target_host, target_port)
        except OSError:
            logger.warning("proxy target %s:%s unavailable", target_host, target_port)
            writer.close()
            await writer.wait_closed()
            return

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except Exception:
                pass
            finally:
                dst.close()

        await asyncio.gather(
            pipe(reader, remote_writer),
            pipe(remote_reader, writer),
            return_exceptions=True,
        )

    server = await asyncio.start_server(handle, listen_host, listen_port)
    logger.info("reverse proxy %s:%s -> %s:%s", listen_host, listen_port, target_host, target_port)
    return server
