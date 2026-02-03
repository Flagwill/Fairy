"""Debug orchestrator loop: verbose logging of manager prompts and child delegates."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from copilot.tools import define_tool
from fairy_llm_gateway import LLMGateway


def _load_delegate_module():
    root = Path(__file__).parent
    delegate_file = root / "tools" / "2_llms" / "delegate.py"
    spec = importlib.util.spec_from_file_location("delegate_mod", delegate_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load delegate tool from {delegate_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


delegate_mod = _load_delegate_module()
DelegateTaskParams = delegate_mod.DelegateTaskParams


@define_tool(description="调试版委派工具：打印入参与结果")
async def delegate_task_debug(params: DelegateTaskParams) -> Dict[str, Any]:
    print(f"\n[DEBUG] delegate_task called: model={params.model}, streaming={params.streaming}, tool_refs={params.tool_refs}")
    result = await delegate_mod.delegate_task_impl(params)
    print(f"[DEBUG] delegate_task result: {result}\n")
    return result


@dataclass
class TaskItem:
    tid: int
    description: str
    status: str = "todo"
    notes: str = ""
    result: Optional[str] = None


class ManagerAgent:
    def __init__(self, tasks: List[str]) -> None:
        self.tasks: List[TaskItem] = [TaskItem(i + 1, desc.strip()) for i, desc in enumerate(tasks) if desc.strip()]
        self.step = 0
        self.max_steps = 30
        self.sub_tool_refs = [
            "tools.system.TUI.control.create_session",
            "tools.system.TUI.control.send_keys",
            "tools.system.TUI.control.kill_session",
            "tools.system.TUI.screen.view_screen",
        ]

    def _system_message(self) -> str:
        return (
            "你是主理智能体，持续跟踪任务进度并输出下一步决策。"
            "你不能直接调用任何外置工具；若需执行操作，请通过 delegate_task 调用下级智能体并分配工具。"
            "保持输出简洁，但请在调试模式下清晰回应。每一轮回复都必须包含 STATE JSON；认为完成时要把对应任务标记为 done。"
        )

    def _snapshot(self) -> str:
        lines = []
        for task in self.tasks:
            lines.append(f"[{task.tid}] {task.status}: {task.description} | notes={task.notes or '-'}")
        return "\n".join(lines) if lines else "(no tasks)"

    def _build_prompt(self) -> str:
        pending = any(task.status != "done" for task in self.tasks)
        goal_hint = "任务未全部完成" if pending else "全部任务已完成，可收尾"
        allowed_tools = ", ".join(self.sub_tool_refs)
        return (
            f"当前进度:\n{self._snapshot()}\n"
            f"目标: {goal_hint}\n"
            f"子智能体可用工具: {allowed_tools}\n"
            "请输出下一步行动；若需下级智能体，请调用 delegate_task，tool_refs 使用上述列表，你自己不要直接调用这些工具。"
            "务必输出 STATE JSON，格式例如: ```state\n{\"tasks\": [{\"id\":1,\"status\":\"doing\",\"notes\":\"...\"}]}\n```"
            "在你认为任务完成时，请果断结束"
        )

    def _apply_state_update(self, text: str) -> None:
        match = re.search(r"```state\n(.*?)```", text, flags=re.S)
        if not match:
            return
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
                "请输出下一步行动；若需下级智能体，请调用 delegate_task，tool_refs 使用上述列表，你自己不要直接调用这些工具。"
                "每一轮必须输出 STATE JSON；若任务完成，务必在 STATE JSON 中将对应任务 status 设为 done。格式例如: ```state\n{\"tasks\": [{\"id\":1,\"status\":\"done\",\"notes\":\"result.md 写入 helloworld 并验证\"}]}\n```"
        indexed: Dict[int, TaskItem] = {task.tid: task for task in self.tasks}
        for item in updates:
            if not isinstance(item, dict):
                continue
            tid = item.get("id") or item.get("tid")
            if tid not in indexed:
                continue
            task = indexed[tid]
            if "status" in item:
                task.status = str(item["status"])
            if "notes" in item:
                task.notes = str(item["notes"])
            if "result" in item:
                task.result = str(item["result"])

    def _all_done(self) -> bool:
        return all(task.status == "done" for task in self.tasks) if self.tasks else False

    async def run(self) -> None:
        stream_header_shown = False

        def stream_printer(delta: str, is_reasoning: bool) -> None:
            nonlocal stream_header_shown
            if is_reasoning and not stream_header_shown:
                print("[manager reasoning] ", end="", flush=True)
                stream_header_shown = True
            print(delta, end="", flush=True)

        async with LLMGateway(
            model="gpt-5",
            streaming=True,
            tools=[delegate_task_debug],
            system_message=self._system_message(),
            request_timeout=900.0,
        ) as gateway:
            gateway.add_stream_handler(stream_printer)
            try:
                while self.step < self.max_steps:
                    self.step += 1
                    prompt = self._build_prompt()
                    print(f"\n=== MANAGER PROMPT (step {self.step}) ===\n{prompt}\n================\n")
                    response = await gateway.ask(
                        prompt,
                        metadata={"step": self.step, "type": "manager_tick", "debug": True},
                    )
                    content = getattr(response, "content", str(response))
                    print(f"\n=== MANAGER RESPONSE (step {self.step}) ===\n{content}\n================\n")
                    self._apply_state_update(content)
                    if self._all_done():
                        print("所有任务已完成，主循环结束。")
                        break
            finally:
                gateway.remove_stream_handler(stream_printer)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the manager agent loop in debug mode")
    parser.add_argument("tasks", nargs="*", help="任务描述，可提供多个")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    seed_tasks = args.tasks or ["示例任务：理解代码仓库并给出改进建议"]
    agent = ManagerAgent(seed_tasks)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
