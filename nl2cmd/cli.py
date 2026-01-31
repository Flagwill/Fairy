import argparse
import asyncio
import os
import sys

from .translator import translate_nl_to_cmd
from .executor import execute_command, is_dangerous


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="trans",
        description="Translate natural language to terminal command via Copilot",
    )
    parser.add_argument("text", nargs="?", help="Natural language command to translate")
    parser.add_argument("extra", nargs=argparse.REMAINDER, help="Extra text if missing quotes")
    parser.add_argument("--shell", default=os.environ.get("NL2CMD_SHELL", "/bin/bash"), help="Shell to execute with")
    parser.add_argument("--no-exec", action="store_true", help="Do not execute, only print")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm execution without prompt")
    parser.add_argument("--dry-run", action="store_true", help="Show command and skip execution")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return parser.parse_args(argv)


def prompt_choice(cmd: str, auto_yes: bool, dangerous: bool):
    if auto_yes:
        return "e"
    print("\nProposed command:\n")
    print(cmd)
    print("\nOptions: [e]xecute, [m]odify, [c]ancel, [p]rint only")
    if dangerous:
        print("Warning: detected potentially dangerous command.")
    while True:
        choice = input("Your choice (e/m/c/p): ").strip().lower()
        if choice in {"e", "m", "c", "p"}:
            return choice


async def run(argv=None):
    args = parse_args(argv)
    text = args.text or " ".join(args.extra).strip()
    if not text:
        print("Please provide a natural language command, e.g.: trans \"列出当前目录所有隐藏文件\"")
        return 2

    if args.verbose:
        print(f"Translating: {text}")

    cmd = await translate_nl_to_cmd(text)
    if args.verbose:
        print(f"Model suggested: {cmd}")

    if args.no_exec or args.dry_run:
        print(cmd)
        return 0

    dangerous = is_dangerous(cmd)
    choice = prompt_choice(cmd, args.yes, dangerous)

    if choice == "m":
        cmd = input("Enter modified command: ").strip()
        dangerous = is_dangerous(cmd)

    if choice in {"p"}:
        print(cmd)
        return 0
    if choice in {"c"}:
        print("Canceled.")
        return 0

    if dangerous and not args.yes:
        confirm = input("Command looks dangerous. Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return 1

    rc = execute_command(cmd, shell=args.shell)
    return rc


def main():
    try:
        exit_code = asyncio.run(run())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        exit_code = 130
    sys.exit(exit_code if isinstance(exit_code, int) else 0)


if __name__ == "__main__":
    main()
