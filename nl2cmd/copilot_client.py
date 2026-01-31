import asyncio
from typing import Optional

try:
    from copilot import CopilotClient  # type: ignore
except Exception:  # pragma: no cover
    CopilotClient = None  # type: ignore


class ClientUnavailable(Exception):
    pass


class NL2CmdCopilot:
    def __init__(self, model: str = "gpt-5-mini"):
        self._client: Optional[CopilotClient] = None
        self._model = model
        self._session = None

    async def start(self):
        if CopilotClient is None:
            raise ClientUnavailable(
                "Copilot SDK not available. Install and configure credentials."
            )
        self._client = CopilotClient()
        await self._client.start()
        self._session = await self._client.create_session({"model": self._model})

    async def stop(self):
        if self._session:
            await self._session.destroy()
            self._session = None
        if self._client:
            await self._client.stop()
            self._client = None

    async def ask(self, prompt: str, timeout: float = 30.0) -> str:
        if not self._session:
            raise ClientUnavailable("Session not initialized. Call start() first.")

        result: Optional[str] = None
        done = asyncio.Event()

        def on_event(event):
            nonlocal result
            ev_type = getattr(event.type, "value", None)
            if ev_type == "assistant.message":
                content = getattr(event.data, "content", "")
                if isinstance(content, str) and content.strip():
                    result = content.strip()
            elif ev_type == "session.idle":
                done.set()

        self._session.on(on_event)
        await self._session.send({"prompt": prompt})

        try:
            await asyncio.wait_for(done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("Copilot translation timed out")

        return result or "echo 'No response from model'"
