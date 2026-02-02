import asyncio
from pathlib import Path

from copilot.tools import define_tool
from pydantic import BaseModel, Field


class ShellCommandParams(BaseModel):
    command: str = Field(description="Shell command to execute")
    cwd: str | None = Field(
        default=None,
        description="Optional working directory for the command",
    )


async def run_shell_command(params: ShellCommandParams) -> dict:
    cwd = Path(params.cwd).expanduser() if params.cwd else None
    process = await asyncio.create_subprocess_shell(
        params.command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_bytes, stderr_bytes = await process.communicate()

    return {
        "command": params.command,
        "cwd": str(cwd) if cwd else None,
        "exit_code": process.returncode,
        "stdout": stdout_bytes.decode().strip(),
        "stderr": stderr_bytes.decode().strip(),
    }


# Tool wrapper for Copilot gateway usage
run_shell_command_tool = define_tool(
    description="Execute a shell command on the Linux system and return its output",
)(run_shell_command)

__all__ = ["ShellCommandParams", "run_shell_command", "run_shell_command_tool"]
