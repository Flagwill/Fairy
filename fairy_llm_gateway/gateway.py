from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from copilot import CopilotClient
from copilot.generated.session_events import SessionEventType

# Streaming handlers receive the text delta and whether it is reasoning.
StreamHandler = Callable[[str, bool], None]


class LLMGateway:
    """Lightweight wrapper around Copilot sessions for text and tool calls."""

    def __init__(
        self,
        model: str = "gpt-4.1",
        *,
        streaming: bool = True,
        tools: Optional[Sequence[Any]] = None,
        session_options: Optional[Dict[str, Any]] = None,
        request_timeout: Optional[float] = None,
        client_options: Optional[Dict[str, Any]] = None,
        system_message: Optional[str] = None,
        infinite_sessions: bool = True,
    ) -> None:
        self.model = model
        self.streaming = streaming
        self.tools = list(tools) if tools else []
        self.session_options = dict(session_options or {})
        self.request_timeout = request_timeout
        self.client_options = dict(client_options or {})
        self.system_message = system_message
        self.infinite_sessions = infinite_sessions

        self._client = CopilotClient(self.client_options)
        self._session = None
        self._started = False
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

        await self._ensure_client_started()
        session_payload = self._build_session_payload()

        self._session = await self._client.create_session(session_payload)

        if self.streaming:
            self._session.on(self._handle_event)

    async def stop(self) -> None:
        """Stop the Copilot client and release resources."""
        if self._client:
            await self._client.stop()
        self._session = None
        self._started = False

    def add_stream_handler(self, handler: StreamHandler) -> None:
        """Register a callback that receives delta tokens during streaming."""
        if not self.streaming:
            raise RuntimeError("Streaming is disabled for this gateway instance.")
        self._stream_handlers.append(handler)

    def remove_stream_handler(self, handler: StreamHandler) -> None:
        if handler in self._stream_handlers:
            self._stream_handlers.remove(handler)

    def _handle_event(self, event: Any) -> None:
        if event.type not in (
            SessionEventType.ASSISTANT_MESSAGE_DELTA,
            SessionEventType.ASSISTANT_REASONING_DELTA,
        ):
            return

        delta = getattr(event.data, "delta_content", "")
        if not delta:
            return

        is_reasoning = event.type == SessionEventType.ASSISTANT_REASONING_DELTA
        # Providers may inject markers like "[reasoning]" into tokens; strip
        # them so downstream handlers control formatting.
        delta = delta.replace("[reasoning]", "")

        for handler in list(self._stream_handlers):
            handler(delta, is_reasoning)

    async def _ensure_client_started(self) -> None:
        if self._started:
            return
        await self._client.start()
        self._started = True

    def _build_session_payload(
        self,
        *,
        model: Optional[str] = None,
        streaming: Optional[bool] = None,
        tools: Optional[Sequence[Any]] = None,
        session_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "streaming": self.streaming if streaming is None else streaming,
            "tools": list(self.tools if tools is None else tools),
        }
        payload.update(self.session_options)
        if session_options:
            payload.update(session_options)
        if self.system_message and "system_message" not in payload:
            payload["system_message"] = {"content": self.system_message}
        payload.setdefault("infinite_sessions", {"enabled": self.infinite_sessions})
        return payload

    @staticmethod
    def _build_messages(prompt: Optional[str], messages: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
        merged: List[Dict[str, str]] = list(messages) if messages else []
        if prompt:
            merged.append({"role": "user", "content": prompt})
        return merged

    @staticmethod
    def _extract_prompt(messages: List[Dict[str, str]]) -> str:
        """Copilot SDK requires a top-level prompt even when messages are provided."""
        for msg in reversed(messages):
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str) and content.strip():
                return content
        return ""

    async def ask(
        self,
        prompt: str,
        *,
        messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        attachments: Optional[Sequence[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Send a prompt (and optional history) and wait for completion."""
        if not self._session:
            raise RuntimeError("Session not started. Call start() first.")

        message_list = self._build_messages(prompt, messages)
        if not message_list:
            raise ValueError("prompt or messages must be provided")

        payload: Dict[str, Any] = {
            "messages": message_list,
            "prompt": self._extract_prompt(message_list),
        }
        if metadata:
            payload["metadata"] = metadata
        if attachments:
            payload["attachments"] = list(attachments)

        effective_timeout = timeout if timeout is not None else self.request_timeout
        return await self._session.send_and_wait(payload, timeout=effective_timeout)

    async def ask_and_collect(
        self,
        prompt: str,
        *,
        messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        attachments: Optional[Sequence[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Send a prompt and collect streamed deltas (including reasoning) into a single string."""
        if not self.streaming:
            raise RuntimeError("ask_and_collect requires streaming=True.")

        buffer: List[str] = []

        def collector(delta: str, is_reasoning: bool) -> None:  # noqa: ARG001
            buffer.append(delta)

        self.add_stream_handler(collector)
        try:
            await self.ask(
                prompt,
                messages=messages,
                metadata=metadata,
                attachments=attachments,
                timeout=timeout,
            )
        finally:
            self.remove_stream_handler(collector)

        return "".join(buffer)

    async def create_child_session(
        self,
        *,
        model: Optional[str] = None,
        streaming: Optional[bool] = None,
        tools: Optional[Sequence[Any]] = None,
        session_options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create a short-lived session, inheriting defaults but allowing overrides."""

        await self._ensure_client_started()
        payload = self._build_session_payload(
            model=model,
            streaming=streaming,
            tools=tools,
            session_options=session_options,
        )
        session = await self._client.create_session(payload)
        return session

    async def delegate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        streaming: Optional[bool] = None,
        tools: Optional[Sequence[Any]] = None,
        session_options: Optional[Dict[str, Any]] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        attachments: Optional[Sequence[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Dispatch a prompt to a new child session and return its response.

        Useful when a parent agent needs to offload work to a fresh context
        (e.g., different model or tool set) without disturbing the primary
        conversation state.
        """

        child = await self.create_child_session(
            model=model,
            streaming=streaming,
            tools=tools,
            session_options=session_options,
        )

        message_list = self._build_messages(prompt, messages)
        if not message_list:
            raise ValueError("prompt or messages must be provided")

        payload: Dict[str, Any] = {
            "messages": message_list,
            "prompt": self._extract_prompt(message_list),
        }
        if metadata:
            payload["metadata"] = metadata
        if attachments:
            payload["attachments"] = list(attachments)

        effective_timeout = timeout if timeout is not None else self.request_timeout
        use_streaming = streaming if streaming is not None else self.streaming

        if use_streaming:
            buffer: List[str] = []

            def _fanout(event: Any) -> None:
                if event.type not in (
                    SessionEventType.ASSISTANT_MESSAGE_DELTA,
                    SessionEventType.ASSISTANT_REASONING_DELTA,
                ):
                    return
                delta = getattr(event.data, "delta_content", "")
                if not delta:
                    return
                is_reasoning = event.type == SessionEventType.ASSISTANT_REASONING_DELTA
                buffer.append(delta.replace("[reasoning]", ""))
                for handler in list(self._stream_handlers):
                    handler(delta, is_reasoning)

            child.on(_fanout)
            try:
                await child.send_and_wait(payload, timeout=effective_timeout)
            finally:
                await child.destroy()

            return {
                "model": model or self.model,
                "streaming": True,
                "content": "".join(buffer),
            }

        try:
            response = await child.send_and_wait(payload, timeout=effective_timeout)
        finally:
            await child.destroy()

        content = getattr(response, "content", response)
        return {
            "model": model or self.model,
            "streaming": False,
            "content": content,
            "raw_response": response,
        }
