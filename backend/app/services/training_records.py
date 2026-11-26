"""轮次 / 入选单 / 节点回报的通用资源服务。

核心规则仍在 round_board；这里让三张新表也具备与其它模块一致的
GET 列表 / 详情 / actions 入口，方便按通用资源约定调用。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services import round_board as rb


class TrainRoundService(BaseModuleService):
    MODULE = "train_round"
    ENTITY = "训练轮次"
    LIST_FIELDS = ["task_code", "round_no", "轮次", "status", "confirmed_at", "closed_at"]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = [rb.ROUND_DRAFT, rb.ROUND_OPEN, rb.ROUND_CLOSED]
    ACTION_RULES = {"确认轮次": rb.ROUND_OPEN, "关闭轮次": rb.ROUND_CLOSED}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id, action, payload=None):
        payload = payload or {}
        row = self.get_entry(entry_id)
        if row is None:
            return None, f"训练轮次 {entry_id} 不存在"
        if action in {"确认轮次", "确认轮次并生成入选单", "生成轮次入选单"}:
            data, message = rb.confirm_round(row.get("task_id"), row.get("round_no"))
            return (row if data is None else {**row, "__result_extra__": {"data": data}}), message
        if action in {"关闭轮次", "结束轮次"}:
            data, message = rb.close_round(row.get("task_id"), row.get("round_no"))
            return (row if data is None else {**row, "__result_extra__": {"data": data}}), message
        return super().run_action(entry_id, action, payload)


class RoundSelectionService(BaseModuleService):
    MODULE = "round_selection"
    ENTITY = "轮次入选单条目"
    LIST_FIELDS = ["task_id", "round_no", "配置编号", "配置版本", "加密方案", "密钥长度", "source"]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = ["轮次确认", "补选配置", "预选配置"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = []


class NodeReportService(BaseModuleService):
    MODULE = "node_report"
    ENTITY = "节点回报"
    LIST_FIELDS = ["node", "round_no", "配置编号", "配置版本", "status", "qualified", "reason"]
    REQUIRED_FIELDS = ["node"]
    STATUS_ORDER = [rb.REPORT_PENDING, rb.REPORT_ACCEPTED, rb.REPORT_REJECTED]
    ACTION_RULES = {"接受": rb.REPORT_ACCEPTED, "接受回报": rb.REPORT_ACCEPTED}
    NEGATIVE_ACTIONS = ["拒绝回报"]

    def run_action(self, entry_id, action, payload=None):
        if action in {"接受", "接受回报", "接受节点回报", "确认接受回报"}:
            report, message, extra = rb.accept_report(entry_id)
            if report is None:
                return None, message
            accepted = report  # 商店里的原始 dict，不含下面的透传标记，避免自引用
            wrapped = dict(report)
            wrapped["__result_extra__"] = {"report": accepted, "data": extra.get("board")}
            return wrapped, message
        return super().run_action(entry_id, action, payload)
