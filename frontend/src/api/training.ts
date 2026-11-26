/** 联邦训练轮次资格相关接口：候选配置、轮次看板、入选单、资格核对与节点回报。 */
import { request } from './client'

export type AnyRecord = Record<string, any>

async function parse<T = AnyRecord>(response: Response): Promise<T> {
  const text = await response.text()
  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(`接口返回异常（HTTP ${response.status}）：${text.slice(0, 120)}`)
  }
}

function taskPath(taskRef: string | number): string {
  return `/api/federated_train/${encodeURIComponent(String(taskRef))}`
}

export async function fetchBoard(
  taskRef: string | number,
  roundNo?: string | number | null,
): Promise<AnyRecord> {
  const query = roundNo !== undefined && roundNo !== null && roundNo !== ''
    ? `?round_no=${encodeURIComponent(String(roundNo))}`
    : ''
  const response = await request(`${taskPath(taskRef)}/board${query}`)
  return parse(response)
}

export async function fetchCandidates(taskRef: string | number): Promise<AnyRecord> {
  const response = await request(`${taskPath(taskRef)}/candidates`)
  return parse(response)
}

export async function createRound(taskRef: string | number, roundNo?: string | number): Promise<AnyRecord> {
  const response = await request(`${taskPath(taskRef)}/rounds`, {
    method: 'POST',
    body: JSON.stringify({ round_no: roundNo ?? null }),
  })
  return parse(response)
}

export async function saveSelection(
  taskRef: string | number,
  roundNo: string | number,
  configIds: Array<string | number>,
  replace?: boolean,
): Promise<AnyRecord> {
  const response = await request(`${taskPath(taskRef)}/selection`, {
    method: 'POST',
    body: JSON.stringify({ round_no: roundNo, config_ids: configIds, replace }),
  })
  return parse(response)
}

export async function confirmRound(
  taskRef: string | number,
  roundNo: string | number,
  configIds?: Array<string | number>,
): Promise<AnyRecord> {
  const response = await request(`${taskPath(taskRef)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ round_no: roundNo, config_ids: configIds }),
  })
  return parse(response)
}

export async function closeRound(taskRef: string | number, roundNo: string | number): Promise<AnyRecord> {
  const response = await request(`${taskPath(taskRef)}/close`, {
    method: 'POST',
    body: JSON.stringify({ round_no: roundNo }),
  })
  return parse(response)
}

export async function checkEligibility(params: {
  taskRef: string | number
  roundNo: string | number
  node: string
  configRef?: string | number | null
}): Promise<AnyRecord> {
  const search = new URLSearchParams({
    round_no: String(params.roundNo),
    node: params.node,
  })
  if (params.configRef !== undefined && params.configRef !== null && params.configRef !== '') {
    search.set('config_id', String(params.configRef))
  }
  const response = await request(`${taskPath(params.taskRef)}/eligibility?${search.toString()}`)
  return parse(response)
}

export async function submitReport(params: {
  taskRef: string | number
  roundNo: string | number
  node: string
  configRef?: string | number | null
  autoAccept?: boolean
}): Promise<AnyRecord> {
  const response = await request(`${taskPath(params.taskRef)}/reports`, {
    method: 'POST',
    body: JSON.stringify({
      round_no: params.roundNo,
      node: params.node,
      config_id: params.configRef ?? null,
      auto_accept: params.autoAccept ?? false,
    }),
  })
  return parse(response)
}

export async function acceptReport(reportId: string | number): Promise<AnyRecord> {
  const response = await request(`/api/federated_train/reports/${encodeURIComponent(String(reportId))}/accept`, {
    method: 'POST',
  })
  return parse(response)
}
