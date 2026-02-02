import asyncio
import random
import sys

from copilot.tools import define_tool
from pydantic import BaseModel, Field

from fairy_llm_gateway import LLMGateway


class GetWeatherParams(BaseModel):
    city: str = Field(description="The name of the city to get weather for")


@define_tool(description="Get the current weather for a city")
async def get_weather(params: GetWeatherParams) -> dict:
    city = params.city
    conditions = ["sunny", "cloudy", "rainy", "partly cloudy"]
    temp = random.randint(50, 80)
    condition = random.choice(conditions)
    return {"city": city, "temperature": f"{temp}°F", "condition": condition}


async def main():
    history = []
    gateway = LLMGateway(model="gpt-4.1", streaming=True, tools=[get_weather])

    async with gateway:
        def stream_printer(delta: str) -> None:
            sys.stdout.write(delta)
            sys.stdout.flush()

        gateway.add_stream_handler(stream_printer)

        print("Weather Assistant (type 'exit' to quit)")
        print("Try: 'What is the weather in Paris?' or 'Compare weather in NYC and LA'\n")

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