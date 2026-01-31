import asyncio
from typing import Optional

from .prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .copilot_client import NL2CmdCopilot, ClientUnavailable


def _build_prompt(text: str) -> str:
    user = USER_PROMPT_TEMPLATE.format(text=text.strip())
    return f"{SYSTEM_PROMPT}\n\n{user}"


async def translate_nl_to_cmd(text: str, model: str = "gpt-5-mini") -> str:
    prompt = _build_prompt(text)

    try:
        copilot = NL2CmdCopilot(model=model)
        await copilot.start()
        try:
            cmd = await copilot.ask(prompt)
        finally:
            await copilot.stop()
        return cmd.strip()
    except ClientUnavailable:
        # Fallback if Copilot SDK not installed; provide a naive echo
        safe_text = text.replace("'", "\'")
        return f"echo 'NL2CMD fallback: {safe_text}'"
    except Exception:
        return "echo 'Translation failed'"
