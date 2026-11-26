<template>
  <section class="page train-detail-page" data-module="federated_train"
           data-testid="federated-train-detail-page">
    <header class="page-head">
      <div>
        <div class="breadcrumb">
          <RouterLink to="/federated_train" class="back-link" data-testid="back-to-list">
            ← 返回联邦训练列表
          </RouterLink>
        </div>
        <h2>联邦训练 · 训练详情与轮次资格</h2>
        <p class="page-desc">
          为指定轮次选择加密配置、生成轮次入选单，并核对节点回报资格；同一节点同一轮只计一次合格回报。
        </p>
      </div>
    </header>

    <div data-testid="federated-train-detail">
      <div data-testid="training-detail">
        <TrainRoundPanel
          :task-ref="taskId"
          :initial-round="roundQuery"
          :auto-open-config="panelQuery === 'config'"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import TrainRoundPanel from '@/components/TrainRoundPanel.vue'

const route = useRoute()
const taskId = computed<string>(() => String(route.params.id ?? route.query.detail ?? ''))
const roundQuery = computed<string | undefined>(() => {
  const value = route.query.round ?? route.query.round_no
  return value === undefined ? undefined : String(value)
})
const panelQuery = computed<string | undefined>(() => {
  const value = route.query.panel
  return value === undefined ? undefined : String(value)
})
</script>

<style scoped>
.breadcrumb { margin-bottom: 6px; }
.back-link { color: var(--brand); text-decoration: none; font-size: 13px; }
.back-link:hover { text-decoration: underline; }
</style>
