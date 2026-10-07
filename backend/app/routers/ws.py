import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/ws", tags=["ws"])

_connections: set[WebSocket] = set()
_radio_clients: set[WebSocket] = set()
_radio_loop: asyncio.AbstractEventLoop | None = None


async def _broadcast() -> None:
    payload = {"count": len(_connections)}
    for ws in list(_connections):
        try:
            await ws.send_json(payload)
        except Exception:
            _connections.discard(ws)


@router.websocket("/listeners")
async def listeners(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    await _broadcast()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        await _broadcast()


async def _send_to_all(payload: dict) -> None:
    for ws in list(_radio_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            _radio_clients.discard(ws)


def notify_radio(payload: dict) -> None:
    """Best-effort push of `payload` to all radio listeners.

    Safe to call from a sync endpoint. No-op when no listener has connected.
    """
    loop = _radio_loop
    if loop is None or not _radio_clients:
        return
    try:
        asyncio.run_coroutine_threadsafe(_send_to_all(payload), loop)
    except RuntimeError:
        pass


@router.websocket("/radio")
async def radio(websocket: WebSocket) -> None:
    global _radio_loop
    await websocket.accept()
    _radio_loop = asyncio.get_running_loop()
    _radio_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _radio_clients.discard(websocket)
