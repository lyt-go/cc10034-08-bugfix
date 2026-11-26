<template>
  <section class="train-panel" data-testid="train-detail" :data-task-id="String(taskRef)">
    <div v-if="loading && !board" class="panel-loading">正在读取训练轮次…</div>

    <template v-else-if="board && board.task">
      <header class="detail-head">
        <div>
          <h3 class="detail-title">
            训练详情 · {{ board.task.任务编号 }}
            <span v-if="board.task.任务代号" class="code-badge">{{ board.task.任务代号 }}</span>
          </h3>
          <p class="page-desc">
            模型：{{ board.task.模型类型 }} ｜ 聚合：{{ board.task.聚合算法 }} ｜
            参与节点：{{ board.task.参与节点 }}
          </p>
        </div>
        <div class="head-tools">
          <button class="btn" type="button" data-testid="reload-board" @click="load()">刷新</button>
        </div>
      </header>

      <p v-if="actionMessage" class="action-message" :class="{ 'error-text': actionError }"
         data-testid="detail-message" role="status">{{ actionMessage }}</p>
      <p v-if="board.message && !board.task" class="error-text">{{ board.message }}</p>

      <!-- 轮次切换 -->
      <div data-testid="round-selector">
      <div class="round-tabs" data-testid="round-tabs">
        <button
          v-for="r in rounds"
          :key="r.id"
          type="button"
          class="round-tab"
          :class="{ active: Number(activeRoundNo) === Number(r.round_no) }"
          :data-testid="`round-tab-${r.round_no}`"
          :data-status="r.status"
          @click="switchRound(r.round_no)"
        >
          第{{ r.round_no }}轮 · {{ r.status }}
        </button>
        <button v-if="!rounds.length" type="button" class="btn primary" data-testid="create-round-empty"
                @click="createNextRound">新建第 1 轮</button>
        <button v-else type="button" class="btn ghost new-round-btn" data-testid="create-round"
                @click="createNextRound">＋ 新建轮次</button>
      </div>
      </div>

      <template v-if="board.round">
        <!-- 指标区：数字 testid 节点只放纯数字，便于 toHaveText('1')；中文标签在相邻节点 -->
        <div class="stat-row detail-stats" data-testid="board-stats">
          <article class="stat-card">
            <span class="stat-label">轮次状态</span>
            <strong class="stat-value" data-testid="round-status" :data-status="board.status">{{ board.status }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">入选数（轮次入选单）</span>
            <span data-testid="selection-count">
              <span data-testid="shortlist-count">
                <strong class="stat-value count-line" data-testid="selected-count"
                        :data-count="selectionCount">{{ selectionCount }}</strong>
              </span>
            </span>
          </article>
          <article class="stat-card">
            <span class="stat-label">合格回报 / 已接受（同节点同轮仅一次）</span>
            <span data-testid="admitted-count">
              <span data-testid="qualified-count">
                <strong class="stat-value count-line" data-testid="accepted-count"
                        :data-count="acceptedCount">{{ acceptedCount }}</strong>
              </span>
            </span>
          </article>
          <article class="stat-card">
            <span class="stat-label">已拒绝（资格不符 / 重复投递）</span>
            <strong class="stat-value count-line" data-testid="rejected-count"
                    :data-count="rejectedCount">{{ rejectedCount }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">待接受</span>
            <strong class="stat-value count-line" data-testid="pending-count"
                    :data-count="pendingCount">{{ pendingCount }}</strong>
          </article>
        </div>

        <!-- 轮次操作 -->
        <div class="action-bar">
          <button class="btn primary" type="button" data-testid="open-config-panel"
                  :disabled="board.status === '已关闭'" @click="openConfigPanel">
            <span data-testid="select-config">为第{{ activeRoundNo }}轮选择配置</span>
          </button>
          <button class="btn" type="button" data-testid="confirm-round"
                  v-if="board.status === '待确认'" @click="doConfirm">
            确认轮次并生成入选单
          </button>
          <button class="btn" type="button" data-testid="confirm-round"
                  v-else-if="board.status === '接收中'" @click="doConfirm">
            重新核对并确认轮次
          </button>
          <button class="btn" type="button" data-testid="close-round"
                  v-if="board.status !== '已关闭'" @click="doClose">关闭轮次</button>
          <span v-if="board.status === '已关闭'" class="closed-hint">
            轮次已关闭，已接受版本的依据继续保留
          </span>
        </div>

        <!-- 轮次入选单 -->
        <div class="panel-block" data-testid="round-shortlist">
          <h4 class="block-title">轮次入选单（节点回报核验依据）</h4>
          <p class="block-hint">
            只有关联「{{ board.task.任务编号 }}」且状态为「已启用」的梯度加密配置才会进入候选；
            其他训练任务、待验证 / 已停用版本不会混入。停用后条目保留，并标注配置当前状态。
          </p>
          <table class="data-table" data-testid="shortlist">
            <thead>
              <tr>
                <th>配置编号</th><th>配置版本</th><th>加密方案</th><th>密钥长度</th>
                <th>入选来源</th><th>配置当前状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in selections" :key="s.id"
                  :data-testid="`shortlist-row-${s.config_id ?? s.id}`"
                  :data-config-status="s.current_status">
                <td>{{ s.配置编号 }}</td>
                <td>{{ s.配置版本 || '—' }}</td>
                <td>{{ s.加密方案 }}</td>
                <td>{{ s.密钥长度 }}</td>
                <td>{{ s.source }}</td>
                <td>
                  <span class="status-chip" :class="statusClass(s.current_status)">{{ s.current_status }}</span>
                </td>
              </tr>
              <tr v-if="!selections.length">
                <td colspan="6" class="empty-state">本轮尚未选择配置，点击「为第{{ activeRoundNo }}轮选择配置」生成入选单</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="two-col">
          <!-- 资格核对 -->
          <div class="panel-block" data-testid="eligibility-checker">
            <h4 class="block-title">节点回报资格核对</h4>
            <div class="mini-form">
              <label>
                <span>节点名称</span>
                <input v-model="eligibility.node" type="text" id="eligibility-node-input"
                       name="eligibility_node" data-testid="eligibility-node"
                       list="train-node-options" placeholder="例如 B" @keyup.enter="checkEligibility" />
              </label>
              <label>
                <span>回报配置版本</span>
                <select v-model="eligibility.configRef" data-testid="eligibility-config">
                  <option v-for="s in selections" :key="s.id" :value="String(s.config_id)">
                    {{ s.配置编号 }}（当前{{ s.current_status }}）
                  </option>
                </select>
              </label>
              <button class="btn primary" type="button" data-testid="check-eligibility" @click="checkEligibility">
                <span data-testid="verify-eligibility">
                  <span data-testid="query-eligibility">核对下一次回报资格</span>
                </span>
              </button>
            </div>
            <datalist id="train-node-options" data-testid="node-options">
              <option v-for="name in nodeOptions" :key="name" :value="name"></option>
            </datalist>
            <div v-if="eligibility.result" class="eligibility-result"
                 :data-eligible="eligibility.result.eligible ? 'true' : 'false'"
                 data-testid="eligibility-result">
              <p class="eligibility-verdict" :class="eligibility.result.eligible ? 'is-ok' : 'is-bad'">
                {{ eligibility.result.eligible ? '✔ 有资格：该节点下一次回报可被接收' : '✘ 无资格：该节点下一次回报将被拒绝' }}
              </p>
              <p v-if="eligibility.result.reason" class="reject-reason" data-testid="eligibility-reason">
                原因：{{ eligibility.result.reason }}
              </p>
              <p v-if="eligibility.result.remediation" class="remediation" data-testid="remediation">
                缺失结果补齐方式：{{ eligibility.result.remediation }}
              </p>
            </div>
          </div>

          <!-- 节点回报入口 -->
          <div class="panel-block" data-testid="report-entry">
            <h4 class="block-title">节点回报入口</h4>
            <form class="mini-form" data-testid="report-form" @submit.prevent="submitReport">
              <label>
                <span>节点名称</span>
                <input v-model="report.node" type="text" id="report-node-input" name="node"
                       data-testid="report-node"
                       list="train-node-options" placeholder="提交本轮回报的节点，如 A / B" required />
              </label>
              <label>
                <span>使用的配置版本</span>
                <select v-model="report.configRef" data-testid="report-config">
                  <option value="">默认使用入选单首个版本</option>
                  <option v-for="s in selections" :key="`r-${s.id}`" :value="String(s.config_id)">
                    {{ s.配置编号 }}（当前{{ s.current_status }}）
                  </option>
                </select>
              </label>
              <label class="check-line">
                <input v-model="report.autoAccept" type="checkbox" data-testid="report-auto-accept" />
                <span>资格通过后直接接受并入选（否则先进入待接受）</span>
              </label>
              <div class="form-actions">
                <button class="btn primary" type="submit" data-testid="submit-report" :disabled="submitting">
                  <span data-testid="report-submit">
                    <span data-testid="submit-node-report">{{ submitting ? '提交中…' : '提交回报' }}</span>
                  </span>
                </button>
              </div>
              <p v-if="reportMessage" class="form-message"
                 :class="reportError ? 'error-text' : 'ok-text'" data-testid="report-message">
                {{ reportMessage }}
              </p>
            </form>
          </div>
        </div>

        <!-- 回报记录 -->
        <div class="panel-block">
          <h4 class="block-title">本轮节点回报记录</h4>
          <table class="data-table" data-testid="report-list">
            <thead>
              <tr>
                <th>节点</th><th>配置编号 / 版本</th><th>提交时间</th><th>结果状态</th>
                <th>拒绝原因</th><th>接受依据</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in reports" :key="r.id" :data-testid="`report-row-${r.id}`" :data-status="r.status">
                <td>{{ r.node }}</td>
                <td>{{ r.配置编号 }}<span v-if="r.配置版本"> / {{ r.配置版本 }}</span></td>
                <td>{{ r.created_at }}</td>
                <td><span class="status-chip" :class="reportStatusClass(r.status)"
                          :data-testid="`report-status-${r.id}`">{{ r.status }}</span></td>
                <td class="reject-reason" :data-testid="`reject-reason-${r.id}`">
                  <span :data-testid="`report-reason-${r.id}`">{{ r.reason || '—' }}</span>
                </td>
                <td class="basis-cell" :title="r.basis">{{ r.basis || '—' }}</td>
                <td class="row-actions">
                  <span v-if="r.status === '待接受'" :data-testid="`accept-report-${r.id}`">
                    <button type="button" class="link" :data-testid="`action-${r.id}-接受`"
                            @click="acceptReport(r.id)">
                      <span :data-testid="`action-${r.id}-接受回报`">接受回报</span>
                    </button>
                  </span>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
              <tr v-if="!reports.length">
                <td colspan="7" class="empty-state">本轮还没有节点回报，可通过右上方节点回报入口提交</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 前一轮历史 -->
        <div class="panel-block history-block" data-testid="round-history">
          <h4 class="block-title">轮次历史</h4>
          <div v-if="previousRound" data-testid="previous-round" :data-round-no="previousRound.round.round_no"
               class="prev-round">
            <h5>前一轮历史 · 第{{ previousRound.round.round_no }}轮（{{ previousRound.round.status }}）</h5>
            <p class="block-hint">
              入选配置 {{ previousRound.selection_count }} 份 ｜ 已接受回报
              {{ previousRound.accepted_count }} 份 ｜ 关闭时间：{{ previousRound.round.closed_at || '—' }}
            </p>
            <ul class="history-list" data-testid="history-list">
              <li v-for="r in previousRound.accepted_reports" :key="`prev-r-${r.id}`"
                  :data-testid="`history-accepted-${r.id}`">
                节点 <strong>{{ r.node }}</strong> 的已接受版本：{{ r.配置编号 }} / {{ r.配置版本 }}
                <div class="basis-cell">{{ r.basis }}</div>
              </li>
            </ul>
          </div>
          <p v-else class="block-hint" data-testid="previous-round-empty">没有紧邻的前一轮记录。</p>

          <div v-for="h in history" :key="`h-${h.round.id}`" class="history-other"
               :data-testid="`history-round-${h.round.round_no}`">
            <h5>第{{ h.round.round_no }}轮 · {{ h.round.status }}</h5>
            <p class="block-hint">
              入选 {{ h.selection_count }} ｜ 已接受 {{ h.accepted_count }} ｜ 拒绝 {{ h.rejected_count }}
            </p>
          </div>
        </div>
      </template>

      <div v-else class="panel-block">
        <p>该训练任务还没有轮次记录。</p>
        <button class="btn primary" type="button" data-testid="create-round-first" @click="createNextRound">
          新建第 1 轮并选择配置
        </button>
      </div>
    </template>

    <!-- 配置选择面板（只渲染合法候选） -->
    <div v-if="showConfigPanel" class="modal-backdrop" data-testid="config-modal" @click.self="closeConfigPanel">
      <div class="modal config-modal" data-testid="config-panel" role="dialog" aria-modal="true">
        <h3>配置选择面板 · {{ board?.task?.任务编号 }} 第{{ activeRoundNo }}轮</h3>
        <p class="block-hint">
          候选已经过服务端核对：仅显示关联本任务且「已启用」的配置；
          训练乙等其他任务、待验证与已停用版本不会出现在这里。
        </p>
        <p v-if="candidateError" class="error-text" data-testid="config-error">{{ candidateError }}</p>
        <div class="candidate-list" data-testid="candidate-list">
          <label v-for="c in candidates" :key="c.id" class="candidate-item"
                 :data-testid="`candidate-row-${c.id}`">
            <input type="checkbox" :value="c.id" v-model="selectedConfigIds"
                   :data-testid="`config-option-${c.id}`" />
            <span class="candidate-body" :data-testid="`candidate-${c.id}`">
              <strong>{{ c.配置编号 }}</strong>
              <span class="code-badge">{{ c.配置版本 || '无版本标记' }}</span>
              <span>{{ c.加密方案 }} / 密钥 {{ c.密钥长度 }} / {{ c.同态层级 }}</span>
              <span class="status-chip status-已启用">已启用</span>
            </span>
          </label>
          <p v-if="!candidates.length" class="empty-state">
            没有符合条件的候选配置：请先在「梯度加密」模块把关联本任务的配置启用。
          </p>
        </div>
        <p v-if="configFormError" class="error-text" data-testid="config-save-error">{{ configFormError }}</p>
        <div class="page-actions modal-actions">
          <button class="btn" type="button" data-testid="cancel-config" @click="closeConfigPanel">取消</button>
          <button class="btn primary" type="button" data-testid="save-selection" @click="saveConfigSelection">
            <span data-testid="submit-selection">
              <span data-testid="confirm-config">保存选择</span>
            </span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  acceptReport as apiAcceptReport,
  checkEligibility as fetchEligibility,
  closeRound as postCloseRound,
  confirmRound as postConfirmRound,
  createRound as postCreateRound,
  fetchBoard,
  saveSelection as postSelection,
  submitReport as postReport,
} from '@/api/training'

const props = defineProps<{
  taskRef: string | number
  initialRound?: string | number
  autoOpenConfig?: boolean
}>()

const board = ref<Record<string, any> | null>(null)
const loading = ref(false)
const actionMessage = ref('')
const actionError = ref(false)

const activeRoundNo = ref<string | number>(props.initialRound ?? '')
const showConfigPanel = ref(false)
const selectedConfigIds = ref<Array<string | number>>([])
const candidateError = ref('')
const configFormError = ref('')

const eligibility = ref<{ node: string; configRef: string; result: Record<string, any> | null }>({
  node: '',
  configRef: '',
  result: null,
})

const report = ref<{ node: string; configRef: string; autoAccept: boolean }>({
  node: '',
  configRef: '',
  autoAccept: false,
})
const reportMessage = ref('')
const reportError = ref(false)
const submitting = ref(false)

const rounds = computed<any[]>(() => board.value?.rounds ?? [])
const candidates = computed<any[]>(() => board.value?.candidates ?? [])
const selections = computed<any[]>(() => board.value?.selections ?? [])
const reports = computed<any[]>(() => board.value?.reports ?? [])
const previousRound = computed<any | null>(() => board.value?.previous_round ?? null)
const history = computed<any[]>(() => board.value?.history ?? [])

const selectionCount = computed(() => Number(board.value?.selection_count ?? selections.value.length))
const acceptedCount = computed(() => Number(board.value?.accepted_count ?? 0))
const rejectedCount = computed(() => Number(board.value?.rejected_count ?? 0))
const pendingCount = computed(() => Number(board.value?.pending_count ?? 0))

const nodeOptions = computed<string[]>(() => {
  const raw = String(board.value?.task?.参与节点 ?? '')
  const fromField = raw.split(/[,，、\s/]+/).map((s) => s.trim()).filter(Boolean)
  const fromReports = reports.value.map((r) => String(r.node ?? '')).filter(Boolean)
  return Array.from(new Set([...fromField, ...fromReports]))
})

function flash(message: string, isError = false) {
  actionMessage.value = message
  actionError.value = isError
}

async function load(roundNo?: string | number) {
  loading.value = true
  try {
    const ref = roundNo ?? activeRoundNo.value ?? props.initialRound ?? ''
    const data = await fetchBoard(props.taskRef, ref === '' ? undefined : ref)
    if (data.ok === false) {
      flash(data.message || '训练轮次读取失败', true)
      board.value = null
    } else {
      board.value = data
      if (data.round) activeRoundNo.value = data.round.round_no
      flash('')
    }
  } catch (error) {
    flash(error instanceof Error ? error.message : '训练详情读取失败', true)
  } finally {
    loading.value = false
  }
}

async function switchRound(roundNo: string | number) {
  activeRoundNo.value = roundNo
  eligibility.value.result = null
  await load(roundNo)
}

function openConfigPanel() {
  configFormError.value = ''
  candidateError.value = ''
  selectedConfigIds.value = selections.value.map((s) => (s.config_id ?? s.id) as number)
  showConfigPanel.value = true
}

function closeConfigPanel() {
  showConfigPanel.value = false
}

async function saveConfigSelection() {
  configFormError.value = ''
  if (!selectedConfigIds.value.length) {
    configFormError.value = '请至少勾选一份已启用的配置'
    return
  }
  const replace = board.value?.status === '待确认'
  const data = await postSelection(props.taskRef, activeRoundNo.value, selectedConfigIds.value, replace)
  if (data.ok === false) {
    configFormError.value = data.message || '保存失败'
    return
  }
  showConfigPanel.value = false
  flash(data.message || '配置选择已保存')
  await load()
}

async function doConfirm() {
  const data = await postConfirmRound(props.taskRef, activeRoundNo.value, selectedConfigIds.value)
  flash(data.message || (data.ok ? '轮次已确认' : '确认失败'), data.ok === false)
  if (data.ok !== false) await load()
}

async function doClose() {
  const data = await postCloseRound(props.taskRef, activeRoundNo.value)
  flash(data.message || (data.ok ? '轮次已关闭' : '关闭失败'), data.ok === false)
  if (data.ok !== false) await load()
}

async function createNextRound() {
  const data = await postCreateRound(props.taskRef)
  if (data.ok === false) {
    flash(data.message || '创建轮次失败', true)
    return
  }
  flash(data.message || '新轮次已创建')
  const nextNo = data.round?.round_no ?? data.data?.round?.round_no
  await load(nextNo)
}

async function checkEligibility() {
  if (!eligibility.value.node.trim()) {
    flash('请先填写要核对的节点名称', true)
    return
  }
  const data = await fetchEligibility({
    taskRef: props.taskRef,
    roundNo: activeRoundNo.value,
    node: eligibility.value.node.trim(),
    configRef: eligibility.value.configRef || null,
  })
  if (data.ok === false) {
    eligibility.value.result = { eligible: false, reason: data.message, remediation: '' }
  } else {
    eligibility.value.result = data
  }
}

async function submitReport() {
  reportError.value = false
  reportMessage.value = ''
  if (!report.value.node.trim()) {
    reportError.value = true
    reportMessage.value = '请填写节点名称'
    return
  }
  submitting.value = true
  try {
    const data = await postReport({
      taskRef: props.taskRef,
      roundNo: activeRoundNo.value,
      node: report.value.node.trim(),
      configRef: report.value.configRef || null,
      autoAccept: report.value.autoAccept,
    })
    reportError.value = data.ok === false
    reportMessage.value = data.message || (data.ok ? '回报已提交' : '回报不符合资格')
    if (data.ok !== false) report.value.node = ''
    await load()
  } catch (error) {
    reportError.value = true
    reportMessage.value = error instanceof Error ? error.message : '回报提交失败'
  } finally {
    submitting.value = false
  }
}

async function acceptReport(reportId: number | string) {
  const data = await apiAcceptReport(reportId)
  flash(data.message || (data.ok ? '已接受' : '接受失败'), data.ok === false)
  await load()
}

function statusClass(status: string): string {
  if (status === '已启用' || status === '已接受') return 'chip-ok'
  if (status === '已停用' || status === '已拒绝') return 'chip-bad'
  if (status === '待验证' || status === '待接受' || status === '待确认') return 'chip-warn'
  if (status === '接收中') return 'chip-info'
  if (status === '已关闭') return 'chip-muted'
  return ''
}

function reportStatusClass(status: string): string {
  return statusClass(status)
}

watch(() => props.taskRef, async () => {
  board.value = null
  await load(props.initialRound)
})

onMounted(async () => {
  await load(props.initialRound)
  if (props.autoOpenConfig) openConfigPanel()
})
</script>

<style scoped>
.train-panel { display: flex; flex-direction: column; gap: 12px; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.detail-title { margin: 0; font-size: 18px; }
.head-tools { display: flex; gap: 8px; }
.code-badge { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px;
  background: #eef2ff; color: #3730a3; font-size: 12px; font-weight: 400; }
.action-message { margin: 0; padding: 8px 12px; border-radius: 6px; background: #ecfdf3;
  border: 1px solid #abefc6; color: #067647; font-size: 13px; }
.action-message.error-text { background: #fef3f2; border-color: #fecdca; color: #b42318; }
.round-tabs { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.round-tab { border: 1px solid var(--border); background: #fff; border-radius: 999px;
  padding: 6px 14px; cursor: pointer; font-size: 13px; }
.round-tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.new-round-btn { margin-left: 4px; }
.detail-stats { flex-wrap: wrap; }
.detail-stats .stat-card { min-width: 150px; }
.count-line { display: block; font-size: 18px; margin-bottom: 4px; }
.action-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.closed-hint { color: var(--muted); font-size: 13px; }
.panel-block { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.block-title { margin: 0 0 8px; font-size: 15px; }
.block-hint { margin: 0 0 10px; color: var(--muted); font-size: 12.5px; line-height: 1.7; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 1100px) { .two-col { grid-template-columns: 1fr; } }
.mini-form { display: flex; flex-direction: column; gap: 10px; }
.mini-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: #334155; }
.mini-form input[type='text'], .mini-form select { padding: 7px 10px; border: 1px solid var(--border);
  border-radius: 6px; font-size: 13px; }
.mini-form .check-line { flex-direction: row; align-items: center; gap: 8px; }
.form-actions { display: flex; gap: 8px; }
.form-message { margin: 0; font-size: 13px; }
.ok-text { color: #067647; }
.reject-reason { color: #b42318; font-size: 12.5px; max-width: 280px; line-height: 1.6; }
.basis-cell { color: var(--muted); font-size: 12px; max-width: 260px; line-height: 1.6; }
.status-chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px;
  background: #f1f5f9; color: #475569; white-space: nowrap; }
.chip-ok { background: #dcfae6; color: #067647; }
.chip-bad { background: #fee4e2; color: #b42318; }
.chip-warn { background: #fef0c7; color: #b54708; }
.chip-info { background: #dbeafe; color: #1d4ed8; }
.chip-muted { background: #e5e7eb; color: #4b5563; }
.eligibility-result { margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: #f8fafc;
  border: 1px solid var(--border); }
.eligibility-verdict { margin: 0 0 6px; font-weight: 600; font-size: 13.5px; }
.eligibility-verdict.is-ok { color: #067647; }
.eligibility-verdict.is-bad { color: #b42318; }
.remediation { margin: 6px 0 0; font-size: 12.5px; line-height: 1.7; color: #334155; }
.history-block .prev-round { border-left: 3px solid var(--brand); padding-left: 12px; margin-bottom: 10px; }
.history-list { margin: 6px 0 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.history-other { padding: 8px 0; border-top: 1px dashed var(--border); }
.history-other h5, .prev-round h5 { margin: 0 0 4px; font-size: 13.5px; }
.candidate-list { display: flex; flex-direction: column; gap: 8px; margin: 10px 0; }
.candidate-item { display: flex; gap: 10px; align-items: flex-start; padding: 10px;
  border: 1px solid var(--border); border-radius: 8px; cursor: pointer; }
.candidate-body { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.config-modal { width: min(680px, 100%); }
.modal-actions { justify-content: flex-end; margin-top: 8px; }
.panel-loading { padding: 40px; text-align: center; color: var(--muted); }
.muted { color: var(--muted); }
</style>
