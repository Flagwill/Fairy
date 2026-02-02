from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from copilot import CopilotClient
from copilot.generated.session_events import SessionEventType

StreamHandler = Callable[[str], None]


class LLMGateway:
    """Lightweight wrapper around Copilot sessions for text and tool calls."""

    def __init__(
        self,
        model: str = "gpt-4.1",
        *,
        streaming: bool = True,
        tools: Optional[Sequence[Any]] = None,
        session_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.model = model
        self.streaming = streaming
        self.tools = list(tools) if tools else []
        self.session_options = dict(session_options or {})

        self._client = CopilotClient()
        self._session = None
        self._stream_handlers: List[StreamHandler] = []

    async def __aenter__(self) -> "LLMGateway":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start the Copilot client and create a session."""
        if self._session:
            return

        await self._client.start()
        session_payload: Dict[str, Any] = {
            "model": self.model,
            "streaming": self.streaming,
            "tools": self.tools,
        }
        session_payload.update(self.session_options)

        self._session = await self._client.create_session(session_payload)

        if self.streaming:
            self._session.on(self._handle_event)

    async def stop(self) -> None:
        """Stop the Copilot client and release resources."""
        if self._client:
            await self._client.stop()
        self._session = None

    def add_stream_handler(self, handler: StreamHandler) -> None:
        """Register a callback that receives delta tokens during streaming."""
        if not self.streaming:
            raise RuntimeError("Streaming is disabled for this gateway instance.")
        self._stream_handlers.append(handler)

    def remove_stream_handler(self, handler: StreamHandler) -> None:
        if handler in self._stream_handlers:
            self._stream_handlers.remove(handler)

    def _handle_event(self, event: Any) -> None:
        if event.type != SessionEventType.ASSISTANT_MESSAGE_DELTA:
            return

        delta = getattr(event.data, "delta_content", "")
        if not delta:
            return

        for handler in list(self._stream_handlers):
            handler(delta)

    async def ask(
        self,
        prompt: str,
        *,
        messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send a prompt (and optional history) and wait for completion."""
        if not self._session:
            raise RuntimeError("Session not started. Call start() first.")

        payload: Dict[str, Any] = {"prompt": prompt}
        if messages:
            payload["messages"] = messages
        if metadata:
            payload["metadata"] = metadata

        return await self._session.send_and_wait(payload)

    async def ask_and_collect(
        self,
        prompt: str,
        *,
        messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a prompt and collect streamed deltas into a single string."""
        if not self.streaming:
            raise RuntimeError("ask_and_collect requires streaming=True.")

        buffer: List[str] = []

        def collector(delta: str) -> None:
            buffer.append(delta)

        self.add_stream_handler(collector)
        try:
            await self.ask(prompt, messages=messages, metadata=metadata)
        finally:
            self.remove_stream_handler(collector)

        return "".join(buffer)
