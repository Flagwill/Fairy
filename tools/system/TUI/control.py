from __future__ import annotations

import asyncio
import shutil
from typing import Dict, List, Optional

from copilot.tools import define_tool
from pydantic import BaseModel, Field, field_validator, model_validator


# Small delay to let the shell produce output before a subsequent capture.
_POST_SEND_DELAY_SEC = 1.0


async def _run_tmux(args: List[str]) -> str:
    if shutil.which("tmux") is None:
        raise RuntimeError("tmux is not installed or not on PATH")

    proc = await asyncio.create_subprocess_exec(
        "tmux", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", "replace") or stdout.decode("utf-8", "replace")
        raise RuntimeError(f"tmux {' '.join(args)} failed: {detail.strip()}")
    return stdout.decode("utf-8", "replace")


class CreateSessionParams(BaseModel):
    session: str = Field(default="fairy_demo")
    start_command: str = Field(default="bash")

    @field_validator("session")
    @classmethod
    def _session_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session cannot be empty")
        return value


async def tmux_create_session_impl(params: CreateSessionParams) -> Dict[str, object]:
    """Ensure a tmux session exists; create if missing."""
    exists = True
    try:
        await _run_tmux(["has-session", "-t", params.session])
    except RuntimeError:
        exists = False
        await _run_tmux([
            "new-session",
            "-d",
            "-s",
            params.session,
            params.start_command,
        ])

    return {
        "session": params.session,
        "target": f"{params.session}:0.0",
        "created": not exists,
    }


create_session = define_tool(
    description="使用交互式命令行的工具，确保会话存在或创建"
)(tmux_create_session_impl)


class SendKeysParams(BaseModel):
    target: str = Field(default="fairy_demo:0.0")
    commands: Optional[List[str]] = None
    keys: Optional[List[str]] = None
    text: Optional[List[str]] = None
    press_enter: bool = True

    @field_validator("target")
    @classmethod
    def _target_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target cannot be empty")
        return value

    @field_validator("commands", "keys", "text")
    @classmethod
    def _list_not_empty(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        if not value:
            raise ValueError("commands/keys cannot be empty when provided")
        return value

    @model_validator(mode="after")
    def _at_least_one(self) -> "SendKeysParams":
        if not self.commands and not self.keys and not self.text:
            raise ValueError("either commands or keys or text must be provided")
        return self


def _format_tmux_key(raw: str) -> str:
    """Convert human-friendly combos (ctrl+c) to tmux key names."""
    key = raw.strip()
    if not key:
        raise ValueError("key cannot be empty")

    normalized = key.lower().replace(" ", "")
    if normalized in {"shift+tab", "s-tab", "backtab", "btab"}:
        return "BTab"

    parts = key.replace("control", "ctrl").replace("meta", "alt").split("+")
    if len(parts) == 1:
        return parts[0]

    mods_map = {"ctrl": "C", "alt": "M", "shift": "S"}
    mods = []
    for part in parts[:-1]:
        mod = mods_map.get(part.lower())
        mods.append(mod if mod else part)

    base = parts[-1].lower()
    base_map = {
        "pageup": "PageUp",
        "page_up": "PageUp",
        "pgup": "PageUp",
        "pagedown": "PageDown",
        "page_down": "PageDown",
        "pgdn": "PageDown",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "enter": "Enter",
        "return": "Enter",
        "space": "Space",
        "spacebar": "Space",
        "tab": "Tab",
        "esc": "Escape",
        "escape": "Escape",
    }
    base = base_map.get(base, base)
    return "-".join([*mods, base])


async def tmux_send_keys_impl(params: SendKeysParams) -> Dict[str, object]:
    if params.commands:
        for command in params.commands:
            await _run_tmux(["send-keys", "-t", params.target, command])
            if params.press_enter:
                await _run_tmux(["send-keys", "-t", params.target, "Enter"])
            await asyncio.sleep(_POST_SEND_DELAY_SEC)

    if params.text:
        for fragment in params.text:
            await _run_tmux(["send-keys", "-t", params.target, fragment])
            await asyncio.sleep(_POST_SEND_DELAY_SEC)

    if params.keys:
        for raw_key in params.keys:
            tmux_key = _format_tmux_key(raw_key)
            await _run_tmux(["send-keys", "-t", params.target, tmux_key])
            await asyncio.sleep(_POST_SEND_DELAY_SEC)

    await asyncio.sleep(_POST_SEND_DELAY_SEC)

    return {
        "target": params.target,
        "sent_commands": params.commands or [],
        "sent_text": params.text or [],
        "sent_keys": params.keys or [],
    }


send_keys = define_tool(
    description="使用交互式命令行的工具，向窗格发送命令或快捷键"
)(tmux_send_keys_impl)


class KillSessionParams(BaseModel):
    session: str = Field(default="fairy_demo")

    @field_validator("session")
    @classmethod
    def _session_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session cannot be empty")
        return value


async def tmux_kill_session_impl(params: KillSessionParams) -> Dict[str, object]:
    await _run_tmux(["kill-session", "-t", params.session])
    return {
        "session": params.session,
        "killed": True,
    }


kill_session = define_tool(
    description="使用交互式命令行的工具，杀死指定 tmux 会话"
)(tmux_kill_session_impl)
