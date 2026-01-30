import os
import subprocess
import shutil
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


class TerminalRunner:
    """
    A lightweight interface to execute shell commands and collect outputs.

    - Uses /bin/bash to ensure Bash semantics.
    - Captures stdout/stderr and keeps a history for context injection to LLM.
    - Provides aggregated context text of prior outputs.
    """

    def __init__(self, env: Optional[dict] = None):
        self._history: List[CommandResult] = []
        # Start from process environment; allow override
        self._env = dict(os.environ)
        if env:
            self._env.update(env)

        # Hint: ensure $BROWSER is respected; if not set, try to infer
        if not self._env.get("BROWSER"):
            # Prefer system-provided opener if available
            for candidate in ("xdg-open", "gio open", "gnome-open", "kde-open"):
                exe = candidate.split()[0]
                if shutil.which(exe):
                    self._env["BROWSER"] = candidate
                    break

    def execute(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        """Execute a shell command via bash and record the result."""
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable="/bin/bash",
            env=self._env,
        )
        result = CommandResult(
            command=command.strip(),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        self._history.append(result)
        return result

    def history(self) -> List[CommandResult]:
        return list(self._history)

    def get_full_output(self, max_chars: int = 20000) -> str:
        """
        Aggregate all recorded outputs into a single text blob suitable for LLM context.
        Limits size to max_chars for prompt safety.
        """
        chunks: List[str] = []
        for item in self._history:
            chunks.append(f"$ {item.command}\n")
            if item.stdout:
                chunks.append(item.stdout)
            if item.stderr:
                chunks.append("[stderr]\n")
                chunks.append(item.stderr)
            chunks.append("\n")
        text = "".join(chunks)
        if len(text) > max_chars:
            return text[-max_chars:]  # keep the most recent tail
        return text

    def get_recent_output(self, last_n: int = 5, max_chars: int = 8000) -> str:
        """Aggregate the outputs of the last N commands."""
        selected = self._history[-last_n:]
        chunks: List[str] = []
        for item in selected:
            chunks.append(f"$ {item.command}\n")
            if item.stdout:
                chunks.append(item.stdout)
            if item.stderr:
                chunks.append("[stderr]\n")
                chunks.append(item.stderr)
            chunks.append("\n")
        text = "".join(chunks)
        if len(text) > max_chars:
            return text[-max_chars:]
        return text
