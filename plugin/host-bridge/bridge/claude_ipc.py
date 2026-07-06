"""IPC server for Claude Code hooks.

Simple request/response: hooks connect, send a JSON action, get a response.

On POSIX the server listens on a Unix domain socket (upstream behaviour).
On Windows, where CPython has no AF_UNIX, it listens on a loopback TCP port
and publishes {"port": N, "pid": N} in config.IPC_PORT_FILE so hook scripts
can find it.
"""

import asyncio
import json
import logging
import os
import socket

from . import config

log = logging.getLogger(__name__)

HAS_AF_UNIX = hasattr(socket, "AF_UNIX")


class ClaudeIPC:
    def __init__(self):
        self._server: asyncio.Server | None = None
        self._on_action = None

    def on_action(self, callback):
        self._on_action = callback

    async def start(self):
        if HAS_AF_UNIX:
            if os.path.exists(config.SOCKET_PATH):
                os.unlink(config.SOCKET_PATH)
            self._server = await asyncio.start_unix_server(
                self._handle_client, path=config.SOCKET_PATH
            )
            os.chmod(config.SOCKET_PATH, 0o666)
            log.info("IPC listening on %s", config.SOCKET_PATH)
        else:
            self._server = await asyncio.start_server(
                self._handle_client, host="127.0.0.1", port=0
            )
            port = self._server.sockets[0].getsockname()[1]
            with open(config.IPC_PORT_FILE, "w", encoding="utf-8") as f:
                json.dump({"port": port, "pid": os.getpid()}, f)
            log.info(
                "IPC listening on 127.0.0.1:%d (port file %s)",
                port,
                config.IPC_PORT_FILE,
            )

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=10.0)
            if not data:
                return

            request = json.loads(data.decode().strip())

            if self._on_action:
                response = await self._on_action(request)
            else:
                response = {"status": "ok"}

            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        except asyncio.TimeoutError:
            log.warning("IPC: read timeout")
        except (ConnectionError, BrokenPipeError):
            log.debug("IPC: client disconnected")
        except Exception as e:
            log.error("IPC: error: %s", e)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if HAS_AF_UNIX:
            if os.path.exists(config.SOCKET_PATH):
                os.unlink(config.SOCKET_PATH)
        else:
            if os.path.exists(config.IPC_PORT_FILE):
                try:
                    os.unlink(config.IPC_PORT_FILE)
                except OSError:
                    pass
