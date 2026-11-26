"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    # 允许把轮次看板 / 回报等附加结果放在顶层返回，方便调用方直接读取。
    model_config = ConfigDict(extra="allow")

    ok: bool
    message: str
    entry: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    eligible: bool | None = None
    selection_count: int | None = None
    accepted_count: int | None = None
    rejected_count: int | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    # 轮次选择 / 节点回报等动作需要 round_no、node、config_id 等附加字段，
    # 全部允许透传给领域服务，避免被 pydantic 丢弃。
    model_config = ConfigDict(extra="allow")

    action: str
    remark: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
