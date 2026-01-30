import asyncio
import os
import platform
from pathlib import Path
from copilot import CopilotClient
from os.terminal import TerminalRunner
from os.safety import is_safe


PROMPT_PATH = Path("prompts/nl2cmd_system.md")


def load_system_prompt() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # Inject minimal environment hints if needed
    env_info = f"OS={platform.system()} {platform.release()}, Shell=Bash, PWD={os.getcwd()}"
    return text.replace("{{ENV_INFO}}", env_info) if "{{ENV_INFO}}" in text else text


def build_prompt(template: str, user_intent: str, terminal_context: str) -> str:
    prompt = template.replace("{{USER_INTENT}}", user_intent.strip())
    prompt = prompt.replace("{{TERMINAL_CONTEXT}}", terminal_context.strip() or "(空)")
    return prompt


async def ask_copilot(session, prompt_text: str) -> str:
    """
    Send prompt to Copilot session and return last assistant message.
    Follows event-based SDK pattern shown in test.py.
    """
    done = asyncio.Event()
    last_msg: str = ""

    def on_event(event):
        nonlocal last_msg
        if event.type.value == "assistant.message":
            # event.data.content is expected to be the assistant string output
            last_msg = str(event.data.content or "")
        elif event.type.value == "session.idle":
            done.set()

    session.on(on_event)
    await session.send({"prompt": prompt_text})
    await done.wait()
    return last_msg.strip()


def extract_command(text: str) -> str:
    """
    Extract single-line command from potential wrappers.
    Accepts plain text or fenced code blocks. Returns the first non-empty line.
    """
    t = text.strip()
    # Handle fenced blocks
    if "```" in t:
        try:
            inner = t.split("```", 2)[1]
            # strip possible language token like `bash\n`
            inner = inner.split("\n", 1)[1] if "\n" in inner else inner
            t = inner.strip()
        except Exception:
            pass
    # Take first non-empty line
    for line in t.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


async def main():
    # Terminal interface
    terminal = TerminalRunner()

    # Load prompt template
    system_template = load_system_prompt()

    # Copilot client
    client = CopilotClient()
    await client.start()
    session = await client.create_session({"model": "gpt-5-mini"})

    print("[Copilot NL→CMD] 输入自然语言指令；输入空行退出。\n")
    try:
        while True:
            user_intent = input("意图> ").strip()
            if not user_intent:
                break

            # Build context from recent terminal outputs
            ctx = terminal.get_recent_output(last_n=8, max_chars=8000)
            prompt_text = build_prompt(system_template, user_intent, ctx)

            # Ask LLM for command
            assistant_text = await ask_copilot(session, prompt_text)
            command = extract_command(assistant_text)

            if not command:
                print("[警告] 未解析到命令。")
                continue

            if not is_safe(command):
                print(f"[阻止] 检测到潜在危险命令：{command}")
                confirm = input("继续执行？输入 'yes' 确认：").strip().lower()
                if confirm != "yes":
                    print("[已取消]")
                    continue

            print(f"$ {command}")
            result = terminal.execute(command)
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="")
            if result.returncode != 0:
                print(f"[返回码] {result.returncode}")

    finally:
        await session.destroy()
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
