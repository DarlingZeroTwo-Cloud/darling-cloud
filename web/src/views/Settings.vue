<script setup>
// 设置：个人设置 + 管理面板（管理员）
import { ref, onMounted } from 'vue'
import { api, getToken } from '../api'

const me = ref(null)
const quota = ref(null)
const settings = ref({})
const groups = ref([])
const users = ref([])
const categories = ref([])
const isAdmin = ref(false)
const tab = ref('profile')

async function load() {
  try {
    const d = await api.get('/auth/me')
    me.value = d.user
    isAdmin.value = d.user.is_admin
    quota.value = await api.get('/user/quota')
    if (isAdmin.value) {
      settings.value = await api.get('/admin/settings')
      groups.value = await api.get('/admin/groups')
      users.value = await api.get('/admin/users')
      categories.value = await api.get('/admin/categories')
    }
  } catch (e) { /* 未登录 */ }
}

async function clearCache() {
  await api.post('/user/clear-cache')
  alert('缓存已清理')
}

function fmt(n) {
  if (n == null) return '-'
  if (n >= 1 << 30) return (n / (1 << 30)).toFixed(2) + ' GB'
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + ' MB'
  return n + ' B'
}

onMounted(() => { if (getToken()) load() })
</script>

<template>
  <div>
    <div class="page-head"><h2>设置</h2></div>

    <div class="tabs" v-if="me">
      <button :class="['tab', tab==='profile' && 'on']" @click="tab='profile'">个人设置</button>
      <button v-if="isAdmin" :class="['tab', tab==='admin' && 'on']" @click="tab='admin'">管理面板</button>
    </div>

    <!-- 个人设置 -->
    <div v-if="tab === 'profile'" class="card panel">
      <div class="row"><span>用户名</span><b>{{ me?.username }}</b></div>
      <div class="row"><span>邮箱</span><b>{{ me?.email }}</b></div>
      <div class="row"><span>用户组</span><b>{{ me?.group }}<span v-if="isAdmin" class="badge">管理员</span></b></div>
      <div class="row"><span>私有空间</span><b>{{ fmt(quota?.priv_used) }} / {{ fmt(quota?.priv_quota) }}</b></div>
      <div class="row"><span>公开空间</span><b>{{ fmt(quota?.pub_used) }} / {{ fmt(quota?.pub_quota) }}</b></div>
      <div class="row">
        <span>一键清缓存</span>
        <button class="btn btn-ghost" @click="clearCache">立即清理</button>
      </div>
    </div>

    <!-- 管理面板 -->
    <div v-if="tab === 'admin'" class="card panel">
      <h3>全站设置</h3>
      <div class="row"><span>允许自由注册</span>
        <select :value="settings.allow_register" @change="api.put('/admin/settings',{allow_register: $event.target.value==='1'})">
          <option value="1">开启</option><option value="0">关闭</option>
        </select>
      </div>
      <div class="row"><span>存储后端</span><b>{{ settings.storage_backend }}</b></div>
      <div class="row"><span>验证码强度</span>
        <select :value="settings.captcha_level" @change="api.put('/admin/settings',{captcha_level: $event.target.value})">
          <option value="easy">轻量（不刁难）</option><option value="medium">中等</option><option value="hard">严格</option>
        </select>
      </div>

      <h3>用户组配额</h3>
      <table class="tbl">
        <tr><th>用户组</th><th>可上传</th><th>私有空间</th><th>公开空间</th></tr>
        <tr v-for="g in groups" :key="g.id">
          <td>{{ g.name }}</td><td>{{ g.can_upload ? '是' : '否' }}</td>
          <td>{{ fmt(g.priv_quota) }}</td><td>{{ fmt(g.pub_quota) }}</td>
        </tr>
      </table>

      <h3>用户管理</h3>
      <table class="tbl">
        <tr><th>ID</th><th>用户名</th><th>邮箱</th><th>用户组</th><th>状态</th></tr>
        <tr v-for="u in users" :key="u.id">
          <td>{{ u.id }}</td><td>{{ u.username }}</td><td>{{ u.email }}</td>
          <td>{{ u.group_name }}</td><td>{{ u.is_active ? '正常' : '停用' }}</td>
        </tr>
      </table>

      <h3>分类管理</h3>
      <div class="cats">
        <span v-for="c in categories" :key="c.id" class="chip">{{ c.name }}</span>
      </div>
    </div>

    <div v-if="!me" class="card panel empty"><p>请先登录</p></div>
  </div>
</template>

<style scoped>
.page-head { margin-bottom: 16px; }
.page-head h2 { font-size: 18px; }
.tabs { display: flex; gap: 6px; margin-bottom: 16px; }
.tab { padding: 7px 16px; border-radius: 8px; color: var(--text-2); font-weight: 500; }
.tab.on { background: var(--accent-soft); color: var(--accent); }
.panel { padding: 24px; }
.panel h3 { font-size: 15px; margin: 24px 0 12px; }
.panel h3:first-child { margin-top: 0; }
.row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px dashed var(--border); }
.row:last-child { border-bottom: none; }
.row span { color: var(--text-2); }
.badge { background: var(--accent-soft); color: var(--accent); font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 6px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.tbl th { color: var(--text-2); font-weight: 500; }
.cats { display: flex; gap: 8px; flex-wrap: wrap; }
.chip { padding: 5px 12px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 13px; }
</style>
