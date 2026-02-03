"""Minimal tmux demo: create session, send commands, capture screen, ask LLM."""

from __future__ import annotations

import asyncio

from fairy_llm_gateway import LLMGateway
from tools.system.TUI import (
    create_session,
    send_keys,
    view_screen,
    kill_session
)


async def main() -> None:

    try:
        async with LLMGateway(
            model="gpt-5",
            streaming=True,
            tools=[create_session, view_screen, send_keys, kill_session],
            request_timeout=600.0,
        ) as gateway:
            prompt = "使用nano命令打开文本编辑器，查看并输出Readme.md中的内容。"

            reasoning_started = False

            def stream_printer(delta: str, is_reasoning: bool) -> None:
                nonlocal reasoning_started
                if is_reasoning and not reasoning_started:
                    print("[思考过程] ", end="", flush=True)
                    reasoning_started = True
                elif not is_reasoning and reasoning_started:
                    print("\n[回答] ", end="", flush=True)
                    reasoning_started = False
                print(delta, end="", flush=True)

            gateway.add_stream_handler(stream_printer)
            try:
                summary = await gateway.ask_and_collect(prompt)
            finally:
                gateway.remove_stream_handler(stream_printer)

            print("\n--- 收到完整回复 ---")
            print(summary)
    except Exception as exc:  # noqa: BLE001 - demo-friendly surface of errors
        print(f"Demo failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())