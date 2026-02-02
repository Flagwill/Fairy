# fairy_llm_gateway API

Lightweight wrapper around GitHub Copilot sessions for text generation, streaming output, and tool calls.

## Quick start
```python
import asyncio
from fairy_llm_gateway import LLMGateway
from copilot.tools import define_tool
from pydantic import BaseModel, Field

class EchoParams(BaseModel):
    text: str = Field(description="Text to echo")

@define_tool(description="Echo a string")
async def echo(params: EchoParams) -> dict:
    return {"echo": params.text}

async def main():
    gateway = LLMGateway(model="gpt-4.1", streaming=True, tools=[echo])

    async with gateway:
        def printer(delta: str) -> None:
            print(delta, end="", flush=True)

        gateway.add_stream_handler(printer)
        await gateway.ask_and_collect("Say hello and call the echo tool.")

asyncio.run(main())
```

## Multi-turn chat with history
```python
history = []
async with LLMGateway(streaming=True) as gateway:
    user_prompt = "Summarize GitHub Copilot in one sentence."
    history.append({"role": "user", "content": user_prompt})
    assistant = await gateway.ask_and_collect(user_prompt, messages=history)
    history.append({"role": "assistant", "content": assistant})
```

## API surface
- `LLMGateway(model="gpt-4.1", streaming=True, tools=None, session_options=None, request_timeout=None)`
  - Creates a gateway with the given model and optional tool list.
  - `session_options` is merged into the session payload (for extra Copilot parameters).
  - `request_timeout` sets the default seconds to wait for a response before timing out (overrides the Copilot default of 60s).
- `start()` / `stop()`
  - Manually manage the client lifecycle. Typically use `async with LLMGateway(...)`.
- `add_stream_handler(handler)` / `remove_stream_handler(handler)`
  - Register callbacks that receive delta tokens when `streaming=True`.
- `ask(prompt, messages=None, metadata=None, timeout=None)`
  - Send a prompt (and optional message history or metadata) and wait for completion.
  - `timeout` overrides `request_timeout` for this call only.
  - Returns the raw result from `session.send_and_wait`.
- `ask_and_collect(prompt, messages=None, metadata=None, timeout=None)`
  - Streaming helper that joins all delta tokens into a single string.
  - `timeout` overrides `request_timeout` for this call only.

## Notes
- Tool functions must be decorated with `@define_tool` from `copilot.tools` and must be async.
- When using history, append both user and assistant turns to `messages` to keep context.
- If you do not need streaming, construct the gateway with `streaming=False` and call `ask`.
