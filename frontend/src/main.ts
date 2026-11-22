import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: (_to, _from, savedPosition) => savedPosition ?? { top: 0 },
  routes: [
    { path: '/', name: 'overview', component: () => import('./views/Overview.vue'), meta: { title: '战绩总览', description: '查看对局表现、盟约趋势与常用阵容。' } },
    { path: '/matches', name: 'matches', component: () => import('./views/History.vue'), meta: { title: '对局记录', description: '查阅每局结算、盟约、阵容与装备。' } },
    { path: '/operators', name: 'operators', component: () => import('./views/Operators.vue'), meta: { title: '干员统计', description: '比较各干员的出场率与出场胜率。' } },
    { path: '/achievements', name: 'achievements', component: () => import('./views/Achievements.vue'), meta: { title: '成就档案', description: '六维成就、称号、获赞与分队特殊标识，数据直连鹰角成就接口。' } },
    { path: '/import', name: 'data-import', component: () => import('./views/Import.vue'), meta: { title: '数据导入', description: '上传战绩快照，查看导入进度。' } },
    { path: '/icons', name: 'mode-icons', component: () => import('./views/ModeIcons.vue'), meta: { title: '难度图标', description: '从 PC 端资源包拆出的模拟难度图标试装页。', public: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.afterEach(route => { document.title = String(route.meta.title) + ' | 卫戍协议' })
createApp(App).use(router).mount('#app')
