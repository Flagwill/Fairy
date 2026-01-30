import re
from typing import Tuple


_BLOCK_PATTERNS: Tuple[str, ...] = (
    r"\brm\b.*\b-rf\b\s*/\b",  # rm -rf /
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\b.*\bof=/dev/(sd|nvme|mmc)\w+",
    r"\bshutdown\b|\breboot\b|\bpoweroff\b",
    r"\bchown\b\s+-R\b\s+root\b",
    r"\buserdel\b\s+--force\b",
    r"\b:(){:|:&};:\b",  # fork bomb
)


def is_safe(command: str) -> bool:
    text = command.strip().lower()
    for pat in _BLOCK_PATTERNS:
        if re.search(pat, text):
            return False
    return True
