from __future__ import annotations

import asyncio
import shutil
from typing import Dict, Tuple

import pyte
from copilot.tools import define_tool
from pydantic import BaseModel, Field, field_validator


class ScreenParams(BaseModel):
    target: str = Field(
        default="fairy:0.0",
        description="Tmux target, e.g. session:window.pane",
    )
    lines: int = Field(
        default=200,
        ge=1,
        le=2000,
        description="Number of lines from the bottom of the pane to capture",
    )
    include_ansi: bool = Field(
        default=False,
        description="Return the raw ANSI buffer alongside parsed text",
    )
    normalize: bool = Field(
        default=True,
        description="Trim leading/trailing spaces per line and drop empty lines for readability",
    )
    join_wrapped: bool = Field(
        default=True,
        description="If True, tmux will join soft-wrapped lines to avoid mid-word breaks",
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
    return "\n".join(lines)


async def tmux_view_screen_impl(params: ScreenParams) -> Dict[str, object]:
    width, height = await _pane_size(params.target)
    ansi = await _capture_pane(params.target, params.lines, params.join_wrapped)
    # Inflate height so pyte keeps as much scrollback as requested.
    plain_text = _ansi_to_text(ansi, width, max(height, params.lines))
    if params.normalize:
        plain_text = _normalize_text(plain_text)

    result: Dict[str, object] = {
        "pane": params.target,
        "width": width,
        "height": height,
        "lines_captured": params.lines,
        "plain_text": plain_text,
    }

    if params.include_ansi:
        result["raw_ansi"] = ansi

    return result


# Tool exposed to the LLM runtime. keep impl separate so it can be called directly in Python.
tmux_view_screen = define_tool(
    description="Capture a tmux pane, parse ANSI, and return readable text"
)(tmux_view_screen_impl)
