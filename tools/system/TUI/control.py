from __future__ import annotations

import asyncio
import shutil
import logging
import os
from typing import Dict, List, Optional

from copilot.tools import define_tool
from pydantic import BaseModel, Field, field_validator, model_validator


# Small delay to let the shell produce output before a subsequent capture.
# Small delays help output flush without slowing interactions too much.
_POST_SEND_DELAY_SEC = 0.1


# Structured logger (enable via FAIRY_TUI_LOG=1, disable with 0/false/no)
_LOG_ENABLED = os.getenv("FAIRY_TUI_LOG", "1").lower() not in {"0", "false", "no"}
_logger = logging.getLogger("fairy.tui")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[TUI] %(asctime)s %(levelname)s: %(message)s"))
    _logger.addHandler(_handler)
_logger.setLevel(logging.DEBUG if _LOG_ENABLED else logging.WARNING)
_logger.propagate = False


async def _run_tmux(args: List[str]) -> str:
    if shutil.which("tmux") is None:
        raise RuntimeError("tmux is not installed or not on PATH")

    _logger.debug("exec: tmux %s", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        "tmux", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", "replace") or stdout.decode("utf-8", "replace")
        _logger.error("tmux failed rc=%s args=%s detail=%r", proc.returncode, args, detail.strip())
        raise RuntimeError(f"tmux {' '.join(args)} failed: {detail.strip()}")
    out = stdout.decode("utf-8", "replace")
    if out.strip():
        _logger.debug("tmux stdout: %r", out.strip())
    return out


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
        _logger.info("session missing, creating: %s", params.session)
        await _run_tmux([
            "new-session",
            "-d",
            "-s",
            params.session,
            params.start_command,
        ])
    if exists:
        _logger.info("session exists: %s", params.session)

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
    """Convert human-friendly key combos (e.g. ctrl+c, C-c, <C-c>) to tmux key names.

    Rules follow tmux key naming:
    - Modifiers: C- (Ctrl), M- (Alt/Meta), S- (Shift)
    - Special keys accepted by tmux: Up/Down/Left/Right, BSpace, BTab, DC (Delete),
      End, Enter, Escape, F1..F12, Home, IC (Insert), NPage/PageDown/PgDn,
      PPage/PageUp/PgUp, Space, Tab
    """
    key = raw.strip()
    if not key:
        raise ValueError("key cannot be empty")

    # Remove surrounding angle brackets often used in docs: <C-c>
    if key.startswith("<") and key.endswith(">"):
        key = key[1:-1]

    # Normalize common words and separators to a unified form
    norm = (
        key.replace("Control", "Ctrl").replace("control", "ctrl")
        .replace("Meta", "Alt").replace("meta", "alt")
        .replace(" ", "-").replace("+", "-")
    )
    parts = [p for p in norm.split("-") if p]

    # If only a simple key without modifiers, map synonyms and return
    def _map_base_name(name: str) -> str:
        lower = name.lower()
        base_map = {
            # arrows
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
            # paging (tmux recognizes PPage/PageUp/PgUp and NPage/PageDown/PgDn)
            "pageup": "PageUp",
            "page_up": "PageUp",
            "pgup": "PgUp",
            "pagedown": "PageDown",
            "page_down": "PageDown",
            "pgdn": "PgDn",
            # editing
            "backspace": "BSpace",
            "bspace": "BSpace",
            "delete": "DC",
            "del": "DC",
            "insert": "IC",
            # navigation
            "home": "Home",
            "end": "End",
            # whitespace / control
            "enter": "Enter",
            "return": "Enter",
            "space": "Space",
            "spacebar": "Space",
            "tab": "Tab",
            "shift+tab": "BTab",
            "s-tab": "BTab",
            "backtab": "BTab",
            "btab": "BTab",
            # escape
            "esc": "Escape",
            "escape": "Escape",
        }
        # Function keys f1..f12
        if lower.startswith("f") and lower[1:].isdigit():
            return f"F{int(lower[1:])}"
        return base_map.get(lower, name)

    if len(parts) == 1:
        mapped = _map_base_name(parts[0])
        if mapped != raw:
            _logger.debug("key map: %r -> %r", raw, mapped)
        return mapped

    mods_map = {"c": "C", "ctrl": "C", "m": "M", "alt": "M", "s": "S", "shift": "S"}
    mods: List[str] = []
    base = parts[-1]
    for p in parts[:-1]:
        key_mod = mods_map.get(p.lower())
        if key_mod:
            mods.append(key_mod)
        else:
            # If a non-modifier sneaks in (e.g. user wrote "C"), keep as-is
            mods.append(p)

    base_mapped = _map_base_name(base)
    result = "-".join([*mods, base_mapped])
    if result != raw:
        _logger.debug("key combo map: %r -> %r", raw, result)
    return result


async def tmux_send_keys_impl(params: SendKeysParams) -> Dict[str, object]:
    _logger.info(
        "send_keys target=%s cmds=%s text=%s keys=%s enter=%s",
        params.target,
        params.commands,
        [len(t) for t in (params.text or [])] if params.text else [],
        params.keys,
        params.press_enter,
    )
    # Send commands as literal text, then optional Enter
    if params.commands:
        for command in params.commands:
            _logger.debug("send-keys -l %r", command)
            await _run_tmux(["send-keys", "-t", params.target, "-l", command])
            if params.press_enter:
                _logger.debug("send-keys Enter")
                await _run_tmux(["send-keys", "-t", params.target, "Enter"])
            await asyncio.sleep(_POST_SEND_DELAY_SEC)

    # Send free text literally (-l)
    if params.text:
        for fragment in params.text:
            if fragment:
                _logger.debug("send-keys -l (len=%d)", len(fragment))
                await _run_tmux(["send-keys", "-t", params.target, "-l", fragment])
                await asyncio.sleep(_POST_SEND_DELAY_SEC)

    # Batch-send key sequences in one call to preserve timing and order
    if params.keys:
        batched: List[str] = []
        for raw_key in params.keys:
            if raw_key and raw_key.strip():
                batched.append(_format_tmux_key(raw_key))
        if batched:
            _logger.debug("send-keys keys=%s", batched)
            await _run_tmux(["send-keys", "-t", params.target, *batched])
            await asyncio.sleep(_POST_SEND_DELAY_SEC)

    # Final small pause to allow the pane to update
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
    _logger.info("kill-session: %s", params.session)
    await _run_tmux(["kill-session", "-t", params.session])
    return {
        "session": params.session,
        "killed": True,
    }


kill_session = define_tool(
    description="使用交互式命令行的工具，杀死指定 tmux 会话"
)(tmux_kill_session_impl)
