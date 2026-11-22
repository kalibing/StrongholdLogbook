import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('./views/Overview.vue'), meta: { title: '战绩总览', description: '查看对局表现、盟约趋势与常用阵容。' } },
    { path: '/matches', name: 'matches', component: () => import('./views/History.vue'), meta: { title: '对局记录', description: '查阅每局结算、盟约、阵容与装备。' } },
    { path: '/operators', name: 'operators', component: () => import('./views/Operators.vue'), meta: { title: '干员统计', description: '比较各干员的出场率与出场胜率。' } },
    { path: '/import', name: 'data-import', component: () => import('./views/Import.vue'), meta: { title: '数据导入', description: '上传战绩快照，查看导入进度。' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.afterEach(route => { document.title = String(route.meta.title) + ' | 卫戍协议' })
createApp(App).use(router).mount('#app')
