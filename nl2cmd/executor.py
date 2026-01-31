import os
import shlex
import subprocess
from typing import List


DANGEROUS_TOKENS = {
    "rm", "mkfs", "dd", "shutdown", "reboot", ":(){:|:&};:", "chmod 777 -R", "chown -R",
}


def is_dangerous(cmd: str) -> bool:
    lower = cmd.lower()
    if "sudo" in lower:
        return True
    for tok in DANGEROUS_TOKENS:
        if tok in lower:
            return True
    # destructive flags commonly
    if "rm -rf" in lower or "--recursive" in lower and "rm" in lower:
        return True
    return False


def execute_command(cmd: str, shell: str = "/bin/bash") -> int:
    # Execute in a login shell to get PATH/env expansions
    try:
        proc = subprocess.run([shell, "-lc", cmd], check=False)
        return proc.returncode
    except FileNotFoundError:
        print(f"Shell not found: {shell}")
        return 127
    except Exception as e:
        print(f"Execution error: {e}")
        return 1
