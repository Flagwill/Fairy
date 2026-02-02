"""Minimal tmux demo: create session, send commands, capture screen, ask LLM."""

from __future__ import annotations

import asyncio

from fairy_llm_gateway import LLMGateway
from tools.system.TUI import (
    CreateSessionParams,
    ScreenParams,
    SendKeysParams,
    tmux_create_session_impl,
    tmux_send_keys_impl,
    tmux_view_screen,
    tmux_view_screen_impl,
)


async def main() -> None:
    session = "fairy_demo"
    target = f"{session}:0.0"

    try:
        await tmux_create_session_impl(CreateSessionParams(session=session, start_command="bash"))
        await tmux_send_keys_impl(
            SendKeysParams(
                target=target,
                commands=[
                    "ls",
                ],
            )
        )

        capture = await tmux_view_screen_impl(ScreenParams(target=target, lines=120, normalize=True))
        print("\n=== Direct tmux capture ===")
        print(capture.get("plain_text") or "Pane is empty or not accessible.")

        print("\n=== LLM-driven capture ===")
        async with LLMGateway(model="gpt-4.1", streaming=True, tools=[tmux_view_screen]) as gateway:
            prompt = (
                f"Call tmux_view_screen with target '{target}', 120 lines, normalize=true; "
                "return plain_text only."
            )
            summary = await gateway.ask_and_collect(prompt)
            print(summary)
    except Exception as exc:  # noqa: BLE001 - demo-friendly surface of errors
        print(f"Demo failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())