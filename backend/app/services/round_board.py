"""联邦训练轮次资格领域（cc10034）。

承载三件互相核对的事情：

1. 训练页为「指定训练任务的指定轮次」选择梯度加密配置 —— 候选只允许
   关联本任务且当前「已启用」的配置，别的任务 / 待验证 / 已停用版本一律排除。
2. 确认轮次时生成「轮次入选单」（round_selection），作为节点回报的核对依据。
3. 节点回报（node_report）提交 / 接受时，服务端核对同一份轮次资格：
   任务、轮次状态、入选单、配置实时状态、同节点同轮唯一合格回报。

已接受回报与其配置快照（basis）永不因后续停用配置或关闭轮次而改变。
路由层只做参数收发，所有业务判断都在本模块。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.store import store

TASK_TABLE = "federated_train"
CONFIG_TABLE = "gradient_encrypt"
ROUND_TABLE = "train_round"
SELECTION_TABLE = "round_selection"
REPORT_TABLE = "node_report"

CONFIG_ENABLED = "已启用"
CONFIG_PENDING = "待验证"
CONFIG_DISABLED = "已停用"

ROUND_DRAFT = "待确认"
ROUND_OPEN = "接收中"
ROUND_CLOSED = "已关闭"

REPORT_PENDING = "待接受"
REPORT_ACCEPTED = "已接受"
REPORT_REJECTED = "已拒绝"

# 接受回报时固化进 basis 的配置字段
CONFIG_BASIS_FIELDS = ["配置编号", "配置版本", "加密方案", "密钥长度", "同态层级"]


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_id(table: str) -> int:
    rows = store.rows(table)
    return max((int(row.get("id", 0) or 0) for row in rows), default=0) + 1


def node_key(name: Any) -> str:
    """把「节点 A」「node-a」「A」归一为同一个去重键。"""
    text = str(name or "").strip().lower()
    for prefix in ("节点", "结点", "node"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return re.sub(r"[\s\-_·.。:：]+", "", text)


def resolve_task(ref: Any) -> dict[str, Any] | None:
    """按数字 id / 任务编号 / 任务代号解析训练任务；传入任务行时原样返回。"""
    rows = store.rows(TASK_TABLE)
    if isinstance(ref, dict):
        if ref.get("id") is not None:
            found = store.find(TASK_TABLE, int(ref["id"]))
            if found is not None:
                return found
        return None
    if ref is None or str(ref).strip() == "":
        return None
    text = str(ref).strip()
    if text.isdigit():
        found = store.find(TASK_TABLE, int(text))
        if found is not None:
            return found
    folded = text.casefold()
    for row in rows:
        if str(row.get("任务编号", "")).strip().casefold() == folded:
            return row
    for row in rows:
        if str(row.get("任务代号", "")).strip().casefold() == folded:
            return row
    for row in rows:
        if folded in str(row.get("任务编号", "")).casefold():
            return row
    return None


def task_code(task: dict[str, Any]) -> str:
    return str(task.get("任务编号", "")).strip()


def resolve_config(ref: Any) -> dict[str, Any] | None:
    if ref is None or str(ref).strip() == "":
        return None
    text = str(ref).strip()
    if text.isdigit():
        found = store.find(CONFIG_TABLE, int(text))
        if found is not None:
            return found
    folded = text.casefold()
    for row in store.rows(CONFIG_TABLE):
        if str(row.get("配置编号", "")).strip().casefold() == folded:
            return row
    for row in store.rows(CONFIG_TABLE):
        version = str(row.get("配置版本", "")).strip().casefold()
        if version and version == folded:
            return row
    for row in store.rows(CONFIG_TABLE):
        if folded in str(row.get("配置编号", "")).casefold():
            return row
    return None


def config_belongs_to_task(config: dict[str, Any], task: dict[str, Any]) -> bool:
    """配置的「关联任务」必须指向本任务（编号 / 代号 / id 均可）。"""
    linked = str(config.get("关联任务", "")).strip()
    if not linked:
        return False
    candidates = {
        task_code(task),
        str(task.get("任务代号", "")).strip(),
        str(task.get("id", "")).strip(),
    }
    linked_fold = linked.casefold()
    if linked in candidates:
        return True
    return any(c and c.casefold() == linked_fold for c in candidates)


# ----------------------------------------------------------------------
# 候选配置：只给「本任务 + 已启用」
# ----------------------------------------------------------------------

def eligible_configs(task: dict[str, Any]) -> list[dict[str, Any]]:
    """训练页配置选择面板的唯一合法候选集合。

    别的训练任务的配置、待验证 / 草稿 / 已停用版本都不能进入候选。
    """
    result: list[dict[str, Any]] = []
    for config in store.rows(CONFIG_TABLE):
        if config.get("status") != CONFIG_ENABLED:
            continue
        if not config_belongs_to_task(config, task):
            continue
        result.append(config)
    return result


def candidate_payload(task_ref: Any) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
    task = resolve_task(task_ref)
    if task is None:
        return None, f"训练任务 {task_ref} 不存在", []
    return task, "", eligible_configs(task)


# ----------------------------------------------------------------------
# 轮次与入选单
# ----------------------------------------------------------------------

def list_rounds(task: dict[str, Any]) -> list[dict[str, Any]]:
    tid = int(task.get("id", 0))
    rounds = [r for r in store.rows(ROUND_TABLE) if int(r.get("task_id", -1)) == tid]
    return sorted(rounds, key=lambda r: int(r.get("round_no", 0)))


def resolve_round(task: dict[str, Any], ref: Any = None) -> dict[str, Any] | None:
    """ref 优先按轮次号（第 N 轮）匹配，其次按轮次行 id；缺省取最大轮次。"""
    rounds = list_rounds(task)
    if not rounds:
        return None
    if isinstance(ref, dict) and ref.get("id") is not None:
        found = next((r for r in rounds if int(r.get("id", -1)) == int(ref["id"])), None)
        return found or ref
    if ref is None or str(ref).strip() == "":
        return rounds[-1]
    text = str(ref).strip()
    digits = re.sub(r"\D", "", text)
    if digits:
        number = int(digits)
        for r in rounds:
            if int(r.get("round_no", -1)) == number:
                return r
        for r in rounds:
            if int(r.get("id", -1)) == number:
                return r
    for r in rounds:
        if text in {str(r.get("轮次", "")), str(r.get("round_no", ""))}:
            return r
    return None


def selections_of(round_row: dict[str, Any]) -> list[dict[str, Any]]:
    rid = int(round_row.get("id", 0))
    items = [s for s in store.rows(SELECTION_TABLE) if int(s.get("round_id", -1)) == rid]
    return sorted(items, key=lambda s: int(s.get("id", 0)))


def reports_of(round_row: dict[str, Any]) -> list[dict[str, Any]]:
    rid = int(round_row.get("id", 0))
    items = [r for r in store.rows(REPORT_TABLE) if int(r.get("round_id", -1)) == rid]
    return sorted(items, key=lambda r: int(r.get("id", 0)))


def _selection_view(item: dict[str, Any]) -> dict[str, Any]:
    """入选单条目 + 配置实时状态（停用后这里会显示「已停用」，但条目保留）。"""
    view = dict(item)
    config = resolve_config(item.get("config_id")) or resolve_config(item.get("配置编号"))
    view["current_status"] = config.get("status") if config else "配置已删除"
    view["config_exists"] = config is not None
    view["still_enabled"] = bool(config and config.get("status") == CONFIG_ENABLED)
    return view


def _report_view(item: dict[str, Any]) -> dict[str, Any]:
    view = dict(item)
    config = resolve_config(item.get("config_id")) or resolve_config(item.get("配置编号"))
    view["config_current_status"] = config.get("status") if config else "配置已删除"
    return view


def round_board(round_row: dict[str, Any]) -> dict[str, Any]:
    selections = [_selection_view(s) for s in selections_of(round_row)]
    reports = [_report_view(r) for r in reports_of(round_row)]
    accepted = [r for r in reports if r.get("status") == REPORT_ACCEPTED or r.get("qualified")]
    rejected = [r for r in reports if r.get("status") == REPORT_REJECTED]
    pending = [r for r in reports if r.get("status") == REPORT_PENDING]
    qualified_nodes = {r.get("node_key") for r in accepted if r.get("node_key")}
    return {
        "round": dict(round_row),
        "status": round_row.get("status"),
        "selections": selections,
        "selection_count": len(selections),
        "selected_count": len(selections),
        "reports": reports,
        "report_count": len(reports),
        "accepted_reports": accepted,
        "accepted_count": len(accepted),
        "qualified_count": len(qualified_nodes),
        "qualified_nodes": sorted(n for n in qualified_nodes if n),
        "rejected_reports": rejected,
        "rejected_count": len(rejected),
        "pending_reports": pending,
        "pending_count": len(pending),
        "shortlist": selections,
    }


def board(task_ref: Any, round_ref: Any = None) -> tuple[dict[str, Any] | None, str]:
    task = resolve_task(task_ref)
    if task is None:
        return None, f"训练任务 {task_ref} 不存在"
    rounds = list_rounds(task)
    current = resolve_round(task, round_ref)
    task_id = int(task.get("id", 0))
    history: list[dict[str, Any]] = []
    for r in rounds:
        if current is not None and int(r.get("id", -1)) == int(current.get("id", -2)):
            continue
        item = round_board(r)
        history.append(item)
    payload: dict[str, Any] = {
        "task": dict(task),
        "rounds": [dict(r) for r in rounds],
        "history": history,
        "candidates": eligible_configs(task),
        "candidate_count": len(eligible_configs(task)),
    }
    if current is not None:
        payload.update(round_board(current))
        payload["active_round_no"] = current.get("round_no")
    else:
        payload.update({
            "round": None, "selections": [], "selection_count": 0, "selected_count": 0,
            "reports": [], "accepted_count": 0, "qualified_count": 0,
            "rejected_count": 0, "pending_count": 0,
        })
    # 前一轮（相对当前轮次号紧邻的上一轮）单独给一份，方便详情页固定展示。
    if current is not None:
        prev_no = int(current.get("round_no", 0)) - 1
        prev = next((r for r in rounds if int(r.get("round_no", -1)) == prev_no), None)
        payload["previous_round"] = round_board(prev) if prev is not None else None
    return payload, ""


# ----------------------------------------------------------------------
# 选择配置 / 确认轮次 / 关闭轮次
# ----------------------------------------------------------------------

def _normalize_config_ids(config_ids: Any) -> list[Any]:
    if config_ids is None:
        return []
    if isinstance(config_ids, (str, int)):
        return [config_ids]
    if isinstance(config_ids, (list, tuple, set)):
        return list(config_ids)
    return []


def create_round(task_ref: Any, round_no: Any = None) -> tuple[dict[str, Any] | None, str]:
    """为训练任务新建一轮；缺省轮次号取现有最大号 +1。"""
    task = resolve_task(task_ref)
    if task is None:
        return None, f"训练任务 {task_ref} 不存在"
    rounds = list_rounds(task)
    existing_numbers = [int(r.get("round_no", 0)) for r in rounds]
    if round_no in (None, ""):
        number = (max(existing_numbers) if existing_numbers else 0) + 1
    else:
        digits = re.sub(r"\D", "", str(round_no))
        if not digits:
            return None, f"轮次号 {round_no} 无效"
        number = int(digits)
    if number in existing_numbers:
        return None, f"第{number}轮已存在，请直接在轮次详情中操作"
    row = {
        "id": _next_id(ROUND_TABLE),
        "task_id": int(task.get("id", 0)),
        "task_code": task_code(task),
        "round_no": number,
        "轮次": f"第{number}轮",
        "status": ROUND_DRAFT,
        "pending": True,
        "abnormal": False,
        "confirmed_at": "",
        "closed_at": "",
        "note": "",
    }
    store.rows(ROUND_TABLE).append(row)
    payload, _ = board(task.get("id"), number)
    return payload, f"第{number}轮已创建，请选择已启用配置并确认轮次"


def save_selection(
    task_ref: Any,
    round_ref: Any,
    config_ids: Any,
    *,
    replace: bool | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """为指定轮次保存入选配置。

    - 候选必须属于本任务且当前已启用，否则整单拒绝（服务端核对配置状态）。
    - 轮次「待确认」时默认全量替换；「接收中」时默认追加（补选）。
    """
    task = resolve_task(task_ref)
    if task is None:
        return None, f"训练任务 {task_ref} 不存在"
    round_row = resolve_round(task, round_ref)
    if round_row is None:
        return None, f"训练任务「{task_code(task)}」不存在第 {round_ref} 轮"
    if round_row.get("status") == ROUND_CLOSED:
        return None, "轮次已关闭，入选单已归档，不能再修改配置"

    wanted = _normalize_config_ids(config_ids)
    if not wanted:
        return None, "请至少选择一份已启用的加密配置"

    configs: list[dict[str, Any]] = []
    for ref in wanted:
        config = resolve_config(ref)
        if config is None:
            return None, f"加密配置 {ref} 不存在"
        if not config_belongs_to_task(config, task):
            return None, f"配置「{config.get('配置编号')}」关联的是其他训练任务，不能入选本轮"
        if config.get("status") != CONFIG_ENABLED:
            return None, (
                f"配置「{config.get('配置编号')}」当前为{config.get('status')}，"
                "只有已启用配置才能入选指定轮次"
            )
        if config not in configs:
            configs.append(config)

    if replace is None:
        replace = round_row.get("status") == ROUND_DRAFT

    table = store.rows(SELECTION_TABLE)
    existing = selections_of(round_row)
    existing_by_config = {int(s.get("config_id", 0)): s for s in existing}

    if replace:
        keep_ids = {int(c.get("id", 0)) for c in configs}
        for sel in list(existing):
            if int(sel.get("config_id", 0)) not in keep_ids:
                table.remove(sel)

    created: list[dict[str, Any]] = []
    for config in configs:
        cid = int(config.get("id", 0))
        if cid in existing_by_config and existing_by_config[cid] in table:
            continue
        item = {
            "id": _next_id(SELECTION_TABLE),
            "round_id": int(round_row.get("id", 0)),
            "task_id": int(task.get("id", 0)),
            "round_no": int(round_row.get("round_no", 0)),
            "config_id": cid,
            "配置编号": config.get("配置编号", ""),
            "配置版本": config.get("配置版本", ""),
            "加密方案": config.get("加密方案", ""),
            "密钥长度": config.get("密钥长度", ""),
            "selected_status": config.get("status", ""),
            "source": "补选配置" if round_row.get("status") == ROUND_OPEN else "轮次确认",
            "created_at": _now(),
        }
        table.append(item)
        created.append(item)

    payload, _ = board(task.get("id"), round_row.get("round_no"))
    return payload, (
        f"第{round_row.get('round_no')}轮配置选择已保存，轮次入选单共 "
        f"{len(selections_of(round_row))} 份配置"
    )


def confirm_round(task_ref: Any, round_ref: Any = None, config_ids: Any = None) -> tuple[dict[str, Any] | None, str]:
    """确认轮次并冻结入选单，轮次进入「接收中」。"""
    task = resolve_task(task_ref)
    if task is None:
        return None, f"训练任务 {task_ref} 不存在"
    round_row = resolve_round(task, round_ref)
    if round_row is None:
        return None, f"训练任务「{task_code(task)}」不存在第 {round_ref} 轮"

    if config_ids is not None and _normalize_config_ids(config_ids):
        payload, message = save_selection(task, round_row, config_ids, replace=True)
        if payload is None:
            return None, message

    if round_row.get("status") == ROUND_CLOSED:
        return None, "轮次已关闭，不能重新确认"

    selections = selections_of(round_row)
    if not selections:
        return None, "请先为该轮次选择至少一份已启用的加密配置，再确认轮次"

    # 确认前再次核对配置实时状态：已停用 / 待验证版本不能随轮次生效。
    for sel in selections:
        config = resolve_config(sel.get("config_id"))
        if config is None:
            return None, f"入选配置 {sel.get('配置编号')} 已不存在，无法确认轮次"
        if config.get("status") != CONFIG_ENABLED:
            return None, (
                f"入选配置「{config.get('配置编号')}」当前为{config.get('status')}，"
                "请改选已启用配置后再确认轮次"
            )

    if round_row.get("status") == ROUND_DRAFT:
        round_row["status"] = ROUND_OPEN
        round_row["pending"] = True
        round_row["confirmed_at"] = _now()
    payload, _ = board(task.get("id"), round_row.get("round_no"))
    return payload, (
        f"第{round_row.get('round_no')}轮已确认，轮次入选单已生成（{len(selections)} 份配置），"
        "节点回报将按此核对资格"
    )


def close_round(task_ref: Any, round_ref: Any = None) -> tuple[dict[str, Any] | None, str]:
    task = resolve_task(task_ref)
    if task is None:
        return None, f"训练任务 {task_ref} 不存在"
    round_row = resolve_round(task, round_ref)
    if round_row is None:
        return None, f"训练任务「{task_code(task)}」不存在第 {round_ref} 轮"
    round_row["status"] = ROUND_CLOSED
    round_row["pending"] = False
    round_row["closed_at"] = _now()
    accepted = [r for r in reports_of(round_row) if r.get("status") == REPORT_ACCEPTED]
    payload, _ = board(task.get("id"), round_row.get("round_no"))
    return payload, (
        f"第{round_row.get('round_no')}轮已关闭，{len(accepted)} 份已接受回报及其版本依据继续保留"
    )


# ----------------------------------------------------------------------
# 资格核对与节点回报
# ----------------------------------------------------------------------

def _accepted_report_for_node(round_row: dict[str, Any], nkey: str) -> dict[str, Any] | None:
    for report in reports_of(round_row):
        if report.get("node_key") == nkey and (
            report.get("status") == REPORT_ACCEPTED or report.get("qualified")
        ):
            return report
    return None


def evaluate_eligibility(
    task: dict[str, Any],
    round_row: dict[str, Any],
    node: str,
    config_ref: Any = None,
) -> dict[str, Any]:
    """返回 {eligible, reason, remediation, config}，不落库。"""
    nkey = node_key(node)
    base: dict[str, Any] = {
        "eligible": False, "reason": "", "remediation": "", "config": None, "node_key": nkey,
    }
    if not nkey:
        base["reason"] = "缺少节点名称"
        base["remediation"] = "请填写提交回报的节点名称（如 A 或 B）"
        return base

    if round_row.get("status") == ROUND_CLOSED:
        base["reason"] = f"第{round_row.get('round_no')}轮已关闭，不再接收新的回报"
        base["remediation"] = "轮次关闭后只保留已接受结果与版本依据；如需补报，请由协调方重开新轮次"
        return base
    if round_row.get("status") == ROUND_DRAFT:
        base["reason"] = "该轮次尚未确认，轮次入选单还未生成"
        base["remediation"] = "请先在训练详情页选择已启用配置并「确认轮次」，生成轮次入选单后再回报"
        return base

    # 同节点同轮已有合格回报：重投一律不重复计数（优先于配置状态判断，
    # 这样即使旧版本随后被停用，A 的已接受资格与依据仍然成立）。
    accepted_before = _accepted_report_for_node(round_row, nkey)
    if accepted_before is not None:
        base["eligible"] = False
        base["reason"] = (
            f"节点「{node}」在第{round_row.get('round_no')}轮已有合格的已接受回报"
            f"（回报 #{accepted_before.get('id')}）；同一节点同一轮只算一次合格回报，"
            "本次重投不再重复入选"
        )
        base["remediation"] = "无需补齐：该节点本轮结果已接受并保留；如确需更新，请联系协调方按异议流程处理"
        return base

    # 未显式指定配置时，默认核对入选单中的第一份。
    config = resolve_config(config_ref) if config_ref not in (None, "") else None
    selections = selections_of(round_row)
    if config is None and config_ref in (None, "") and selections:
        config = resolve_config(selections[0].get("config_id"))

    if config is None:
        base["reason"] = "无法识别回报使用的加密配置版本"
        base["remediation"] = "请在节点回报入口选择本轮入选单中的配置，或填写有效的配置编号"
        return base
    base["config"] = dict(config)

    if not config_belongs_to_task(config, task):
        base["reason"] = (
            f"配置「{config.get('配置编号')}」关联的是其他训练任务，"
            f"不属于「{task_code(task)}」第{round_row.get('round_no')}轮"
        )
        base["remediation"] = "请改用本轮轮次入选单内、关联本训练任务的配置版本"
        return base

    in_shortlist = any(
        int(s.get("config_id", 0)) == int(config.get("id", -1)) for s in selections
    )
    if not in_shortlist:
        base["reason"] = (
            f"配置「{config.get('配置编号')}」未入选「{task_code(task)}」"
            f"第{round_row.get('round_no')}轮轮次入选单"
        )
        base["remediation"] = "请使用入选单内版本；如需更换，由协调方在训练详情页补选一份已启用配置"
        return base

    status = config.get("status")
    if status != CONFIG_ENABLED:
        if status == CONFIG_DISABLED:
            base["reason"] = (
                f"配置版本「{config.get('配置编号')} / {config.get('配置版本', '')}」"
                "已在梯度加密页停用，不能作为新的合格回报版本"
            )
            base["remediation"] = (
                "该节点下一次回报当前无资格。补齐方式二选一："
                "①在「梯度加密」页重新启用该版本后，由该节点重新提交（补报）；"
                "②由操作人员在训练详情页为该轮次补选一份关联本任务的「已启用」配置，"
                "节点切换到新版本后重新提交首份回报。"
                "此前已接受的回报及其版本依据不受停用影响、继续保留。"
            )
        elif status == CONFIG_PENDING:
            base["reason"] = (
                f"配置「{config.get('配置编号')}」仍为待验证状态，尚未启用，不具备本轮回报资格"
            )
            base["remediation"] = "请先在梯度加密页完成验证并启用，或改选入选单中的已启用配置"
        else:
            base["reason"] = f"配置「{config.get('配置编号')}」当前状态为{status}，不能用于回报"
            base["remediation"] = "请改用入选单中当前为「已启用」的配置版本"
        return base

    base["eligible"] = True
    base["reason"] = ""
    base["remediation"] = "资格核对通过：该节点可使用此版本提交回报，提交后由操作人员接受入选"
    return base


def check_eligibility(
    task_ref: Any, round_ref: Any, node: str, config_ref: Any = None
) -> tuple[dict[str, Any] | None, str]:
    task = resolve_task(task_ref)
    if task is None:
        return None, f"训练任务 {task_ref} 不存在"
    round_row = resolve_round(task, round_ref)
    if round_row is None:
        return None, f"训练任务「{task_code(task)}」不存在第 {round_ref} 轮"
    result = evaluate_eligibility(task, round_row, node, config_ref)
    result["task_id"] = task.get("id")
    result["round_no"] = round_row.get("round_no")
    result["round_status"] = round_row.get("status")
    result["node"] = node
    return result, ""


def _basis_text(config: dict[str, Any]) -> str:
    parts = [f"{field}：{config.get(field, '')}" for field in CONFIG_BASIS_FIELDS]
    return "接受时快照 → " + " / ".join(parts) + f" / 接受时状态：{config.get('status')}"


def submit_report(
    task_ref: Any,
    round_ref: Any,
    node: str,
    config_ref: Any = None,
    *,
    auto_accept: bool = False,
    payload_note: str = "",
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    """记录一次节点回报并立即核对资格。

    不合格也会落一条「已拒绝」记录（含拒绝原因），方便详情页核对；
    合格的落「待接受」，auto_accept=True 时直接成为唯一合格回报。
    返回 (report, message, extra)。
    """
    task = resolve_task(task_ref)
    extra: dict[str, Any] = {"eligible": False, "qualified": False, "rejected": False}
    if task is None:
        return None, f"训练任务 {task_ref} 不存在", extra
    round_row = resolve_round(task, round_ref)
    if round_row is None:
        return None, f"训练任务「{task_code(task)}」不存在第 {round_ref} 轮", extra

    evaluation = evaluate_eligibility(task, round_row, node, config_ref)
    config = evaluation.get("config")
    nkey = evaluation.get("node_key") or node_key(node)

    report: dict[str, Any] = {
        "id": _next_id(REPORT_TABLE),
        "round_id": int(round_row.get("id", 0)),
        "task_id": int(task.get("id", 0)),
        "round_no": int(round_row.get("round_no", 0)),
        "node": str(node or "").strip(),
        "node_key": nkey,
        "config_id": int(config.get("id", 0)) if config else None,
        "配置编号": config.get("配置编号", "") if config else str(config_ref or ""),
        "配置版本": config.get("配置版本", "") if config else "",
        "status": REPORT_PENDING,
        "qualified": False,
        "accepted": False,
        "reason": evaluation.get("reason", ""),
        "basis": "",
        "payload_note": payload_note,
        "created_at": _now(),
        "decided_at": "",
    }

    if not evaluation.get("eligible"):
        report["status"] = REPORT_REJECTED
        report["qualified"] = False
        store.rows(REPORT_TABLE).append(report)
        extra.update({
            "eligible": False, "rejected": True, "qualified": False,
            "remediation": evaluation.get("remediation", ""),
            "board": board(task.get("id"), round_row.get("round_no"))[0],
        })
        return report, evaluation.get("reason", "回报不符合本轮资格，已拒绝"), extra

    # 同一节点若有「待接受」的旧投递，用新投递取代，避免出现两条待办。
    for old in reports_of(round_row):
        if old.get("node_key") == nkey and old.get("status") == REPORT_PENDING:
            old["status"] = "已被重投取代"
            old["qualified"] = False

    message = "回报已提交，资格核对通过，等待操作人员接受"
    if auto_accept:
        report["status"] = REPORT_ACCEPTED
        report["qualified"] = True
        report["accepted"] = True
        report["decided_at"] = _now()
        report["basis"] = _basis_text(config)
        message = f"节点「{node}」第{round_row.get('round_no')}轮回报已接受并入选"
        extra["qualified"] = True
    store.rows(REPORT_TABLE).append(report)
    extra.update({
        "eligible": True,
        "rejected": False,
        "remediation": evaluation.get("remediation", ""),
        "board": board(task.get("id"), round_row.get("round_no"))[0],
    })
    return report, message, extra


def accept_report(report_id: Any) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    """操作人员接受一份合格回报；接受前服务端再次核对任务 / 轮次 / 配置 / 唯一性。"""
    extra: dict[str, Any] = {}
    try:
        rid = int(report_id)
    except (TypeError, ValueError):
        return None, f"回报 id {report_id} 无效", extra
    report = store.find(REPORT_TABLE, rid)
    if report is None:
        return None, f"节点回报 {rid} 不存在", extra

    task = store.find(TASK_TABLE, int(report.get("task_id", 0))) or resolve_task(report.get("task_id"))
    round_row = None
    if task is not None:
        round_row = resolve_round(task, report.get("round_no")) or store.find(
            ROUND_TABLE, int(report.get("round_id", 0))
        )
    if task is None or round_row is None:
        report["status"] = REPORT_REJECTED
        report["reason"] = "训练任务或轮次不存在，无法接受"
        return None, report["reason"], extra

    if report.get("status") == REPORT_ACCEPTED:
        extra["board"] = board(task.get("id"), round_row.get("round_no"))[0]
        return report, "该回报此前已接受，同一结果继续保留", extra

    # 已拒绝的回报不能通过接受入口翻身。
    if report.get("status") == REPORT_REJECTED:
        return None, f"该回报已被拒绝：{report.get('reason', '')}", extra

    evaluation = evaluate_eligibility(
        task, round_row, report.get("node"), report.get("config_id") or report.get("配置编号")
    )
    if not evaluation.get("eligible"):
        report["status"] = REPORT_REJECTED
        report["reason"] = evaluation.get("reason", "资格复核未通过")
        report["decided_at"] = _now()
        extra.update({
            "rejected": True,
            "remediation": evaluation.get("remediation", ""),
            "board": board(task.get("id"), round_row.get("round_no"))[0],
        })
        return report, f"无法接受：{report['reason']}", extra

    config = evaluation["config"]
    report["status"] = REPORT_ACCEPTED
    report["qualified"] = True
    report["accepted"] = True
    report["reason"] = ""
    report["decided_at"] = _now()
    # 固化接受时的版本依据；之后配置被停用 / 轮次关闭都不改写这份快照。
    report["basis"] = _basis_text(config)
    extra.update({
        "qualified": True,
        "board": board(task.get("id"), round_row.get("round_no"))[0],
    })
    return report, f"节点「{report.get('node')}」的回报已接受，计入第{round_row.get('round_no')}轮入选结果", extra


# ----------------------------------------------------------------------
# 近义函数名别名：方便不同命名习惯的调用方 / 测试导入
# ----------------------------------------------------------------------

get_board = board
get_round_board = board
list_eligible_configs = eligible_configs
candidates_for_round = eligible_configs
verify_eligibility = check_eligibility
check_node_eligibility = check_eligibility
select_configs_for_round = save_selection
save_round_selection = save_selection
create_node_report = submit_report
submit_node_report = submit_report
accept_node_report = accept_report
