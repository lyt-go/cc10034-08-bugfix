import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import TrainDetailView from '@/views/TrainDetailView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    {
      path: '/federated_train/:id',
      name: 'federated-train-detail',
      component: TrainDetailView,
      props: true,
    },
    {
      path: '/federated_train/detail/:id',
      name: 'federated-train-detail-alias',
      component: TrainDetailView,
      props: true,
    },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
