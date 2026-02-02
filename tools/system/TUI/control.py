from __future__ import annotations

import asyncio
import shutil
from typing import Dict, List

from copilot.tools import define_tool
from pydantic import BaseModel, Field, field_validator


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
    session: str = Field(default="fairy_demo", description="tmux session name")
    start_command: str = Field(default="bash", description="Command executed in the new session")

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


tmux_create_session = define_tool(
    description="Ensure a tmux session exists; create it if missing"
)(tmux_create_session_impl)


class SendKeysParams(BaseModel):
    target: str = Field(default="fairy_demo:0.0", description="Target pane: session:window.pane")
    commands: List[str] = Field(..., min_length=1, description="Commands to send; Enter appended after each")

    @field_validator("target")
    @classmethod
    def _target_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target cannot be empty")
        return value


async def tmux_send_keys_impl(params: SendKeysParams) -> Dict[str, object]:
    for command in params.commands:
        await _run_tmux(["send-keys", "-t", params.target, command])
        await _run_tmux(["send-keys", "-t", params.target, "Enter"])

    return {
        "target": params.target,
        "sent": params.commands,
    }


tmux_send_keys = define_tool(
    description="Send one or more commands to a tmux pane (each followed by Enter)"
)(tmux_send_keys_impl)
