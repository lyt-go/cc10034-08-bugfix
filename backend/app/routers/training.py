"""联邦训练轮次资格 API（cc10034）。

提供：候选配置、轮次详情（入选单 + 回报 + 历史）、选择配置 / 确认 / 关闭轮次、
资格核对、节点回报提交与接受。为兼容不同调用习惯，关键动作同时提供多组路径别名，
请求体字段也支持 node/node_name、round_no/round、config_id/config_code 等写法。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.services import round_board as rb

router = APIRouter(prefix="/api", tags=["联邦训练轮次资格"])


async def _body(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """依次从顶层和 values 嵌套对象里取字段。"""
    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
        if key in values and values[key] not in (None, ""):
            return values[key]
    return default


def _round_ref(data: dict[str, Any]) -> Any:
    return _pick(data, "round_no", "round", "轮次", "round_index", default=None)


def _config_ref(data: dict[str, Any]) -> Any:
    ids = _pick(data, "config_ids", "selected_config_ids", default=None)
    if ids is not None:
        return ids
    return _pick(data, "config_id", "config_code", "配置编号", "config", "version", default=None)


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "message": message, **extra}


def _fail(message: str, status_code: int = 200, **extra: Any) -> Any:
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"ok": False, "message": message, **extra})


# ----------------------------------------------------------------------
# 查询：候选 / 轮次看板
# ----------------------------------------------------------------------

@router.get("/gradient_encrypt/candidates")
@router.get("/gradient_encrypt/eligible")
def gradient_candidates_by_query(
    task_id: str | None = None,
    task_code: str | None = None,
    federated_train_id: str | None = None,
    round_no: str | int | None = None,
) -> dict[str, Any]:
    """按 query 参数返回某训练任务（可选轮次）的合法加密候选。"""
    task_ref = task_id or federated_train_id or task_code
    if task_ref is None:
        return {"ok": False, "message": "缺少 task_id / task_code", "candidates": [], "count": 0}
    task, message, candidates = rb.candidate_payload(task_ref)
    if task is None:
        return {"ok": False, "message": message, "candidates": [], "items": [], "count": 0}
    return {
        "ok": True,
        "task_id": task.get("id"),
        "round_no": round_no,
        "candidates": candidates,
        "items": candidates,
        "gradient_configs": candidates,
        "count": len(candidates),
    }


@router.get("/federated_train/{task_ref}/config-candidates")
@router.get("/federated_train/{task_ref}/candidates")
def get_candidates(task_ref: str) -> dict[str, Any]:
    task, message, candidates = rb.candidate_payload(task_ref)
    if task is None:
        return {"ok": False, "message": message, "candidates": [], "items": [], "count": 0}
    return {
        "ok": True,
        "message": "",
        "task_id": task.get("id"),
        "candidates": candidates,
        "items": candidates,
        "gradient_configs": candidates,
        "count": len(candidates),
    }


@router.get("/federated_train/{task_ref}/board")
@router.get("/federated_train/{task_ref}/detail")
@router.get("/federated_train/{task_ref}/round-detail")
def get_board(task_ref: str, round_no: str | int | None = None, round: str | int | None = None) -> dict[str, Any]:
    ref = round_no if round_no is not None else round
    payload, message = rb.board(task_ref, ref)
    if payload is None:
        return {"ok": False, "message": message}
    return {"ok": True, "message": "", "data": payload, **payload}


@router.get("/federated_train/{task_ref}/shortlist")
@router.get("/federated_train/{task_ref}/selection")
@router.get("/federated_train/{task_ref}/round-selection")
def get_shortlist(
    task_ref: str, round_no: str | int | None = None, round: str | int | None = None
) -> dict[str, Any]:
    ref = round_no if round_no is not None else round
    task = rb.resolve_task(task_ref)
    if task is None:
        return {"ok": False, "message": f"训练任务 {task_ref} 不存在", "items": [], "shortlist": [], "count": 0}
    round_row = rb.resolve_round(task, ref)
    if round_row is None:
        return {"ok": False, "message": "轮次不存在", "items": [], "shortlist": [], "count": 0}
    items = [rb._selection_view(s) for s in rb.selections_of(round_row)]
    return {
        "ok": True,
        "round_no": round_row.get("round_no"),
        "status": round_row.get("status"),
        "items": items,
        "shortlist": items,
        "selections": items,
        "count": len(items),
    }


@router.get("/federated_train/{task_ref}/rounds")
def get_rounds(task_ref: str) -> dict[str, Any]:
    task = rb.resolve_task(task_ref)
    if task is None:
        return {"ok": False, "message": f"训练任务 {task_ref} 不存在", "rounds": [], "items": []}
    rounds = rb.list_rounds(task)
    return {"ok": True, "rounds": rounds, "items": rounds, "total": len(rounds)}


@router.post("/federated_train/{task_ref}/rounds")
async def create_round(task_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    board_payload, message = rb.create_round(task_ref, _round_ref(data))
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


@router.get("/federated_train/{task_ref}/rounds/{round_ref}")
def get_round_board(task_ref: str, round_ref: str) -> dict[str, Any]:
    payload, message = rb.board(task_ref, round_ref)
    if payload is None:
        return {"ok": False, "message": message}
    return {"ok": True, "message": "", "data": payload, **payload}


@router.get("/federated_train/{task_ref}/eligibility")
def eligibility_get(
    task_ref: str,
    node: str = "",
    round_no: str | int | None = None,
    round: str | int | None = None,
    config_id: str | None = None,
    config_code: str | None = None,
) -> dict[str, Any]:
    ref = round_no if round_no is not None else round
    config_ref = config_id or config_code
    result, message = rb.check_eligibility(task_ref, ref, node, config_ref)
    if result is None:
        return {"ok": False, "eligible": False, "message": message}
    return {"ok": True, "message": "", **result}


# ----------------------------------------------------------------------
# 选择配置 / 确认 / 关闭
# ----------------------------------------------------------------------

@router.post("/federated_train/{task_ref}/selection")
@router.post("/federated_train/{task_ref}/select-config")
async def save_selection(task_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    round_ref = _round_ref(data)
    config_ref = _config_ref(data)
    replace = _pick(data, "replace", "overwrite", default=None)
    board_payload, message = rb.save_selection(
        task_ref, round_ref, config_ref, replace=replace if isinstance(replace, bool) else None
    )
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


@router.post("/federated_train/{task_ref}/rounds/{round_ref}/selection")
async def save_round_selection(task_ref: str, round_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    config_ref = _config_ref(data)
    replace = _pick(data, "replace", default=None)
    board_payload, message = rb.save_selection(
        task_ref, round_ref, config_ref, replace=replace if isinstance(replace, bool) else None
    )
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


@router.post("/federated_train/{task_ref}/confirm")
@router.post("/federated_train/{task_ref}/confirm-round")
async def confirm_round(task_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    board_payload, message = rb.confirm_round(task_ref, _round_ref(data), _config_ref(data))
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


@router.post("/federated_train/{task_ref}/rounds/{round_ref}/confirm")
async def confirm_round_by_path(task_ref: str, round_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    board_payload, message = rb.confirm_round(task_ref, round_ref, _config_ref(data))
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


@router.post("/federated_train/{task_ref}/close")
@router.post("/federated_train/{task_ref}/close-round")
async def close_round(task_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    board_payload, message = rb.close_round(task_ref, _round_ref(data))
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


@router.post("/federated_train/{task_ref}/rounds/{round_ref}/close")
async def close_round_by_path(task_ref: str, round_ref: str) -> dict[str, Any]:
    board_payload, message = rb.close_round(task_ref, round_ref)
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


# ----------------------------------------------------------------------
# 节点回报
# ----------------------------------------------------------------------

@router.post("/federated_train/{task_ref}/eligibility")
async def eligibility_post(task_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    node = _pick(data, "node", "node_name", "节点", default="")
    result, message = rb.check_eligibility(task_ref, _round_ref(data), node, _config_ref(data))
    if result is None:
        return {"ok": False, "eligible": False, "message": message}
    return {"ok": True, "message": "", **result}


@router.post("/federated_train/{task_ref}/reports")
@router.post("/federated_train/{task_ref}/report")
@router.post("/federated_train/{task_ref}/node-reports")
async def submit_report(task_ref: str, request: Request) -> Any:
    data = await _body(request)
    node = _pick(data, "node", "node_name", "节点", default="")
    auto_accept = bool(_pick(data, "auto_accept", "accept_directly", default=False)) or bool(
        _pick(data, "accept", default=False)
    )
    report, message, extra = rb.submit_report(
        task_ref,
        _round_ref(data),
        node,
        _config_ref(data),
        auto_accept=auto_accept,
        payload_note=str(_pick(data, "remark", "note", default="") or ""),
    )
    if report is None:
        return _fail(message, **{k: v for k, v in extra.items() if k != "board"})
    board_payload = extra.pop("board", None)
    # 不合格落了拒绝记录，但对调用方仍以 ok=False 表达「未入选」。
    ok = not extra.get("rejected", False)
    response: dict[str, Any] = {
        "ok": ok,
        "message": message,
        "report": report,
        "entry": report,
        **extra,
    }
    if board_payload is not None:
        response["data"] = board_payload
        response.update({k: board_payload[k] for k in (
            "selection_count", "accepted_count", "qualified_count", "rejected_count", "pending_count"
        ) if k in board_payload})
    return response


@router.post("/federated_train/reports/{report_id}/accept")
async def accept_report(report_id: int) -> Any:
    report, message, extra = rb.accept_report(report_id)
    if report is None:
        return _fail(message)
    board_payload = extra.get("board")
    response = _ok(message, report=report, entry=report)
    if board_payload is not None:
        response["data"] = board_payload
    return response


@router.post("/node_report/{report_id}/accept")
@router.post("/node_reports/{report_id}/accept")
async def accept_report_alias(report_id: int) -> Any:
    return await accept_report(report_id)


# —— 轮次嵌套风格别名：/federated_train/{task}/rounds/{round}/... ——

@router.get("/federated_train/{task_ref}/rounds/{round_ref}/eligibility")
def eligibility_nested_get(
    task_ref: str,
    round_ref: str,
    node: str = "",
    config_id: str | None = None,
    config_code: str | None = None,
) -> dict[str, Any]:
    result, message = rb.check_eligibility(task_ref, round_ref, node, config_id or config_code)
    if result is None:
        return {"ok": False, "eligible": False, "message": message}
    return {"ok": True, "message": "", **result}


@router.post("/federated_train/{task_ref}/rounds/{round_ref}/eligibility")
async def eligibility_nested_post(task_ref: str, round_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    node = _pick(data, "node", "node_name", "节点", default="")
    result, message = rb.check_eligibility(task_ref, round_ref, node, _config_ref(data))
    if result is None:
        return {"ok": False, "eligible": False, "message": message}
    return {"ok": True, "message": "", **result}


@router.post("/federated_train/{task_ref}/rounds/{round_ref}/reports")
async def submit_report_nested(task_ref: str, round_ref: str, request: Request) -> Any:
    data = await _body(request)
    node = _pick(data, "node", "node_name", "节点", default="")
    auto_accept = bool(_pick(data, "auto_accept", "accept", default=False))
    report, message, extra = rb.submit_report(
        task_ref, round_ref, node, _config_ref(data), auto_accept=auto_accept
    )
    if report is None:
        return _fail(message)
    return {
        "ok": not extra.get("rejected", False),
        "message": message,
        "report": report,
        "entry": report,
        "eligible": extra.get("eligible"),
        "qualified": extra.get("qualified"),
        "rejected": extra.get("rejected"),
    }


@router.post("/federated_train/{task_ref}/rounds/{round_ref}/select-config")
async def select_config_nested(task_ref: str, round_ref: str, request: Request) -> dict[str, Any]:
    data = await _body(request)
    board_payload, message = rb.save_selection(task_ref, round_ref, _config_ref(data))
    if board_payload is None:
        return _fail(message)
    return _ok(message, data=board_payload, **board_payload)


@router.post("/reports/{report_id}/accept")
@router.post("/node-reports/{report_id}/accept")
async def accept_report_root_alias(report_id: int) -> Any:
    return await accept_report(report_id)
