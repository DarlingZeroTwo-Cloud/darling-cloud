import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from './api'

const routes = [
  { path: '/', name: 'public', component: () => import('./views/Public.vue') },
  { path: '/login', name: 'login', component: () => import('./views/Login.vue') },
  { path: '/register', name: 'register', component: () => import('./views/Register.vue') },
  { path: '/files', name: 'files', component: () => import('./views/Files.vue'), meta: { auth: true } },
  { path: '/shares', name: 'shares', component: () => import('./views/Shares.vue'), meta: { auth: true } },
  { path: '/recycle', name: 'recycle', component: () => import('./views/Recycle.vue'), meta: { auth: true } },
  { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue'), meta: { auth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  if (to.meta.auth && !getToken()) return { name: 'login', query: { redirect: to.fullPath } }
  if ((to.name === 'login' || to.name === 'register') && getToken()) return { name: 'public' }
})

export default router
