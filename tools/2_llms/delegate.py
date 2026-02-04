from __future__ import annotations

from typing import Any, Dict, List, Optional

import importlib
from copilot.tools import define_tool
from pydantic import BaseModel, Field, field_validator

from fairy_llm_gateway import LLMGateway


class DelegateTaskParams(BaseModel):
    task: str = Field(description="要交给下级智能体的自然语言指令")
    model: str = Field(default="gpt-4.1", description="下级智能体使用的模型")
    streaming: bool = Field(default=False, description="是否流式收集子回复")
    tool_refs: Optional[List[str]] = Field(
        default=None,
        description="下级智能体可用工具的列表",
    )
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="为支持的模型选择推理力度：low|medium|high|xhigh",
    )
    system_message: Optional[str] = Field(
        default=None,
        description="可选的系统提示，限定下级智能体的角色或范围",
    )
    timeout: float = Field(
        default=900.0,
        ge=1.0,
        le=3600.0,
        description="子任务的超时时间（秒）",
    )

    @field_validator("task")
    @classmethod
    def _task_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task cannot be empty")
        return value

    @field_validator("tool_refs")
    @classmethod
    def _tool_refs_clean(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            return None
        return cleaned


# Ensure forward refs (when __future__ annotations is on) are resolved before schema generation.
DelegateTaskParams.model_rebuild()


def _load_tools(refs: List[str]) -> List[Any]:
    resolved: List[Any] = []
    for ref in refs:
        try:
            module_path, attr = ref.rsplit(".", 1)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"tool_ref must be 'module.attr', got {ref!r}") from exc
        module = importlib.import_module(module_path)
        tool_obj = getattr(module, attr, None)
        if tool_obj is None:
            raise AttributeError(f"cannot find {attr!r} in module {module_path!r}")
        resolved.append(tool_obj)
    return resolved


async def delegate_task_impl(params: DelegateTaskParams) -> Dict[str, Any]:
    session_options: Dict[str, Any] = {}
    if params.reasoning_effort:
        session_options["reasoning_effort"] = params.reasoning_effort
    if params.system_message:
        session_options["system_message"] = {"content": params.system_message}

    tools = _load_tools(params.tool_refs) if params.tool_refs else None

    try:
        async with LLMGateway(
            model=params.model,
            streaming=params.streaming,
            tools=tools,
            session_options=session_options,
            request_timeout=params.timeout,
        ) as gateway:
            if params.streaming:
                content = await gateway.ask_and_collect(
                    params.task,
                    metadata={"delegated": True},
                )
                return {
                    "ok": True,
                    "model": params.model,
                    "streaming": True,
                    "content": content,
                    "state_hint": "if task completed, set status=done in STATE JSON",
                }

            response = await gateway.ask(
                params.task,
                metadata={"delegated": True},
            )
            content = getattr(response, "content", response)
            note = "任务已由子智能体完成，可在 STATE JSON 中标记为 done。"
            return {
                "ok": True,
                "model": params.model,
                "streaming": False,
                "content": content,
                "state_hint": note,
            }

    except Exception as exc:  # noqa: BLE001 - surface tool failures to orchestrator
        return {
            "ok": False,
            "error": str(exc),
            "model": params.model,
            "streaming": params.streaming,
        }


delegate_task = define_tool(
    description="委派任务给下级智能体，返回子智能体的回复"
)(delegate_task_impl)
