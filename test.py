import asyncio
import sys

from fairy_llm_gateway import LLMGateway
from tools.system.simple_cmd.terminal_tool import run_shell_command_tool


async def main():
    history = []
    gateway = LLMGateway(model="gpt-4.1", streaming=True, tools=[run_shell_command_tool])

    async with gateway:
        def stream_printer(delta: str) -> None:
            sys.stdout.write(delta)
            sys.stdout.flush()

        gateway.add_stream_handler(stream_printer)

        print("Terminal Assistant (type 'exit' to quit)")
        print("Try: 'Run ls', 'Show current directory (pwd)', or 'List python files in tools'\n")

        while True:
            try:
                user_input = input("You: ")
            except EOFError:
                break

            if user_input.lower() == "exit":
                break

            history.append({"role": "user", "content": user_input})
            sys.stdout.write("Assistant: ")
            assistant_reply = await gateway.ask_and_collect(user_input, messages=history)
            history.append({"role": "assistant", "content": assistant_reply})
            print("\n")


asyncio.run(main())