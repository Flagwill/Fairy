from __future__ import annotations

import asyncio
import shutil
from typing import Dict, List, Tuple

import pyte
from copilot.tools import define_tool
from pydantic import BaseModel, Field, field_validator


class ScreenParams(BaseModel):
    target: str = Field(
        default="fairy_demo:0.0",
    )
    lines: int = Field(
        default=200,
        ge=1,
        le=2000,
    )
    @field_validator("target")
    @classmethod
    def _target_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target cannot be empty")
        return value


async def _run_tmux(args: Tuple[str, ...]) -> str:
    if shutil.which("tmux") is None:
        raise RuntimeError("tmux is not installed or not on PATH")

    process = await asyncio.create_subprocess_exec(
        "tmux",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        details = stderr.decode("utf-8", "replace") or stdout.decode("utf-8", "replace")
        raise RuntimeError(f"tmux {' '.join(args)} failed: {details.strip()}")

    return stdout.decode("utf-8", "replace")


async def _pane_size(target: str) -> Tuple[int, int]:
    output = await _run_tmux(("display-message", "-p", "-t", target, "#{pane_width} #{pane_height}"))
    try:
        width_str, height_str = output.strip().split()
        return int(width_str), int(height_str)
    except ValueError as exc:
        raise RuntimeError(f"Unable to parse pane size for target {target!r}: {output!r}") from exc


async def _capture_pane(target: str, lines: int, join_wrapped: bool) -> str:
    start_offset = f"-{lines}"
    args = ["capture-pane", "-ep", "-t", target, "-S", start_offset]
    if join_wrapped:
        args.insert(1, "-J")
    return await _run_tmux(tuple(args))


def _ansi_to_text(ansi: str, width: int, height: int) -> str:
    # Use a taller screen to avoid losing older lines when the pane height is small.
    effective_height = max(height, 1)
    screen = pyte.Screen(max(width, 1), effective_height)
    stream = pyte.Stream(screen)
    stream.feed(ansi)
    rendered = "\n".join(row.rstrip() for row in screen.display)
    return rendered.rstrip("\n")


def _normalize_text(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    # Drop lines that become empty after trimming
    lines = [ln for ln in lines if ln]
    lines = _drop_leading_echo(lines)
    return "\n".join(lines)


def _drop_leading_echo(lines: List[str]) -> List[str]:
    if len(lines) < 2:
        return lines

    first, second = lines[0], lines[1]
    # If the first line is immediately repeated as the tail of the next line (usually prompt + command), drop it.
    if first and second.endswith(first) and second != first:
        return lines[1:]

    return lines


async def tmux_view_screen_impl(params: ScreenParams) -> Dict[str, object]:
    width, height = await _pane_size(params.target)
    ansi = await _capture_pane(params.target, params.lines, True)
    # Inflate size so pyte keeps as much scrollback as requested and avoid mid-line wraps.
    render_width = max(width, 400)
    render_height = max(height, params.lines)
    plain_text = _ansi_to_text(ansi, render_width, render_height)
    plain_text = _normalize_text(plain_text)

    result: Dict[str, object] = {
        "pane": params.target,
        "width": width,
        "height": height,
        "lines_captured": params.lines,
        "plain_text": plain_text,
    }

    return result


# Tool exposed to the LLM runtime. keep impl separate so it can be called directly in Python.
tmux_view_screen = define_tool(
    description="使用交互式命令行的工具，捕获并返回可读文本"
)(tmux_view_screen_impl)
