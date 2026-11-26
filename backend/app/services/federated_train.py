"""联邦训练领域服务：训练任务 CRUD/状态流转 + 指定轮次的配置选择与节点回报资格。

轮次相关业务规则全部在 app.services.round_board，本类只负责把通用动作入口
（POST /api/federated_train/{id}/actions，中文 action + 附加字段）分派过去，
保持与其它 17 个模块一致的调用习惯。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services import round_board as rb
from app.store import store


class FederatedTrainService(BaseModuleService):
    MODULE = "federated_train"
    ENTITY = "训练任务"
    OPERATION_TERM = "聚合"
    LIST_FIELDS = ["任务编号", "参与节点", "模型类型", "聚合算法", "全局轮次", "全局准确率", "开始时间", "训练状态"]
    REQUIRED_FIELDS = ["任务编号", "参与节点", "模型类型"]
    STATUS_ORDER = ["初始化", "训练中", "已收敛", "已终止"]
    ACTION_RULES = {"启动训练": "训练中", "标记收敛": "已收敛", "终止任务": "已终止"}
    NEGATIVE_ACTIONS = []

    # 走轮次资格内核的动作名（兼容几种近义说法）
    SELECT_ACTIONS = {"选择配置", "保存配置选择", "保存选择", "为轮次选择配置", "补选配置"}
    CONFIRM_ACTIONS = {"确认轮次", "确认轮次并生成入选单", "生成轮次入选单", "确认选择"}
    CLOSE_ACTIONS = {"关闭轮次", "结束轮次", "封盘轮次"}
    REPORT_ACTIONS = {"提交回报", "提交节点回报", "节点回报", "上报回报", "提交梯度回报"}
    ACCEPT_ACTIONS = {"接受", "接受回报", "接受节点回报", "确认接受回报", "入选该回报"}

    def run_action(
        self,
        entry_id: int,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        payload = payload or {}
        task = store.find(self.MODULE, entry_id)
        if task is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"

        round_ref = self._pick(payload, "round_no", "round", "轮次", "round_index")
        config_ref = self._config_ref(payload)
        node = self._pick(payload, "node", "node_name", "节点", default="")
        report_id = self._pick(payload, "report_id", "回报id", "id")

        if action in self.SELECT_ACTIONS:
            board_payload, message = rb.save_selection(entry_id, round_ref, config_ref)
            return self._wrap_entry(task, board_payload), message if board_payload else message

        if action in self.CONFIRM_ACTIONS:
            board_payload, message = rb.confirm_round(entry_id, round_ref, config_ref)
            if board_payload is None:
                return None, message
            return self._wrap_entry(task, board_payload), message

        if action in self.CLOSE_ACTIONS:
            board_payload, message = rb.close_round(entry_id, round_ref)
            if board_payload is None:
                return None, message
            return self._wrap_entry(task, board_payload), message

        if action in self.REPORT_ACTIONS:
            auto_accept = bool(self._pick(payload, "auto_accept", "accept", default=False))
            report, message, extra = rb.submit_report(
                entry_id, round_ref, node, config_ref, auto_accept=auto_accept
            )
            if report is None:
                return None, message
            board_payload = extra.get("board")
            wrapped = self._wrap_entry(task, board_payload)
            wrapped["__result_extra__"]["report"] = report
            wrapped["__result_extra__"]["eligible"] = bool(extra.get("eligible"))
            wrapped["__result_extra__"]["rejected"] = bool(extra.get("rejected"))
            return wrapped, message

        if action in self.ACCEPT_ACTIONS:
            if report_id in (None, ""):
                # 没带 report_id 时，尝试接受该任务该轮次唯一待接受回报。
                report_id = self._fallback_pending_report_id(task, round_ref, node)
            report, message, extra = rb.accept_report(report_id)
            if report is None:
                return None, message
            wrapped = self._wrap_entry(task, extra.get("board"))
            wrapped["__result_extra__"]["report"] = report
            return wrapped, message

        return super().run_action(entry_id, action, payload)

    # ------------------------------------------------------------------
    # 语义化方法名：直接编写 Python 校验 / 测试时不必走中文 action 分派。
    # 统一委托给 round_board 内核，保证 UI、HTTP、服务调用是同一份规则。
    # ------------------------------------------------------------------
    @staticmethod
    def candidates_for_task(task_ref: Any) -> list[dict[str, Any]]:
        task = rb.resolve_task(task_ref)
        return rb.eligible_configs(task) if task else []

    @staticmethod
    def round_detail(task_ref: Any, round_no: Any = None) -> tuple[dict[str, Any] | None, str]:
        return rb.board(task_ref, round_no)

    @staticmethod
    def get_round_board(task_ref: Any, round_no: Any = None) -> tuple[dict[str, Any] | None, str]:
        return rb.board(task_ref, round_no)

    @staticmethod
    def select_config(
        task_ref: Any, round_no: Any, config_ids: Any, *, replace: bool | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        return rb.save_selection(task_ref, round_no, config_ids, replace=replace)

    @staticmethod
    def confirm_round(task_ref: Any, round_no: Any = None, config_ids: Any = None):
        return rb.confirm_round(task_ref, round_no, config_ids)

    @staticmethod
    def close_round(task_ref: Any, round_no: Any = None):
        return rb.close_round(task_ref, round_no)

    @staticmethod
    def check_eligibility(task_ref: Any, round_no: Any, node: str, config_ref: Any = None):
        return rb.check_eligibility(task_ref, round_no, node, config_ref)

    @staticmethod
    def submit_node_report(task_ref, round_no, node, config_ref=None, *, auto_accept: bool = False):
        return rb.submit_report(task_ref, round_no, node, config_ref, auto_accept=auto_accept)

    @staticmethod
    def accept_node_report(report_id: Any):
        return rb.accept_report(report_id)

    # ------------------------------------------------------------------
    @staticmethod
    def _pick(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
        values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
        for key in keys:
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
            if key in values and values[key] not in (None, ""):
                return values[key]
        return default

    @classmethod
    def _config_ref(cls, payload: dict[str, Any]) -> Any:
        ids = cls._pick(payload, "config_ids", "selected_config_ids", default=None)
        if ids is not None:
            return ids
        return cls._pick(
            payload, "config_id", "config_code", "配置编号", "config", "version", default=None
        )

    @staticmethod
    def _wrap_entry(task: dict[str, Any], board_payload: dict[str, Any] | None) -> dict[str, Any]:
        """返回任务行的副本并挂上看板载荷；__result_extra__ 供通用路由透传。"""
        entry = dict(task)
        extra: dict[str, Any] = {}
        if board_payload is not None:
            entry["board"] = board_payload
            extra["data"] = board_payload
            for key in ("selection_count", "accepted_count", "qualified_count", "rejected_count"):
                if key in board_payload:
                    extra[key] = board_payload[key]
        entry["__result_extra__"] = extra
        return entry

    def _fallback_pending_report_id(
        self, task: dict[str, Any], round_ref: Any, node: str
    ) -> int | None:
        round_row = rb.resolve_round(task, round_ref)
        if round_row is None:
            return None
        reports = rb.reports_of(round_row)
        if node:
            nkey = rb.node_key(node)
            for report in reports:
                if report.get("node_key") == nkey and report.get("status") == rb.REPORT_PENDING:
                    return int(report["id"])
        pending = [r for r in reports if r.get("status") == rb.REPORT_PENDING]
        return int(pending[0]["id"]) if len(pending) == 1 else (int(pending[0]["id"]) if pending else None)
