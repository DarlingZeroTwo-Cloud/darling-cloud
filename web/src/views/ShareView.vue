<script setup>
// 分享落地页（免登录）：查看信息 + 输入提取码 + 下载
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const info = ref(null)
const password = ref('')
const err = ref('')
const loading = ref(true)

async function load() {
  loading.value = true; err.value = ''
  try {
    const r = await fetch(`/api/s/${route.params.token}`)
    const j = await r.json()
    if (!r.ok) { err.value = j.detail || '分享不存在'; return }
    info.value = j
  } catch (e) { err.value = '网络错误' } finally { loading.value = false }
}

async function download() {
  err.value = ''
  let dl = ''
  if (info.value.has_password) {
    try {
      const r = await fetch(`/api/s/${route.params.token}/verify`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: password.value })
      })
      const j = await r.json()
      if (!r.ok) { err.value = j.detail || '验证失败'; return }
      dl = '&t=' + j.download_token
    } catch (e) { err.value = '网络错误'; return }
  }
  const a = document.createElement('a')
  a.href = `/api/s/${route.params.token}/download?x=1${dl}`
  document.body.appendChild(a); a.click(); a.remove()
}

function fmt(n) {
  if (n >= 1<<30) return (n/(1<<30)).toFixed(2)+' GB'
  if (n >= 1<<20) return (n/(1<<20)).toFixed(1)+' MB'
  if (n >= 1024) return (n/1024).toFixed(1)+' KB'
  return n+' B'
}

onMounted(load)
</script>

<template>
  <div class="landing">
    <div class="card box" v-if="info && !err">
      <div class="logo-big">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path d="M14 2v6h6"/>
        </svg>
      </div>
      <h1>{{ info.name }}</h1>
      <div class="meta">
        <span>{{ fmt(info.size) }}</span>
        <span v-if="info.owner">· {{ info.owner }} 分享</span>
        <span v-if="info.expire_at">· {{ info.expire_at.slice(0,16).replace('T',' ') }} 过期</span>
        <span v-if="info.max_downloads">· 剩余 {{ info.max_downloads - info.downloads }} 次下载</span>
      </div>
      <div v-if="info.has_password" class="pw-row">
        <input v-model="password" class="ipt" placeholder="输入提取码" @keyup.enter="download" />
      </div>
      <button class="btn btn-primary big" @click="download">下载文件</button>
      <div v-if="err" class="err">{{ err }}</div>
    </div>
    <div v-if="err && !info" class="card box">
      <h1>分享不可用</h1>
      <p class="err">{{ err }}</p>
    </div>
    <div v-if="loading" class="card box"><p>加载中…</p></div>
  </div>
</template>

<style scoped>
.landing { min-height: 60vh; display: flex; align-items: center; justify-content: center; padding: 24px; }
.box { width: 100%; max-width: 420px; padding: 32px 28px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 14px; }
.logo-big { width: 56px; height: 56px; border-radius: 16px; background: var(--accent-soft); color: var(--accent); display: flex; align-items: center; justify-content: center; }
.logo-big svg { width: 30px; height: 30px; }
.box h1 { font-size: 18px; word-break: break-all; }
.meta { font-size: 12.5px; color: var(--text-3); display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
.pw-row { width: 100%; }
.ipt { width: 100%; padding: 10px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-card); color: var(--text); font-size: 14px; text-align: center; }
.ipt:focus { outline: none; border-color: var(--accent); }
.big { width: 100%; padding: 12px; font-size: 15px; }
.err { color: var(--danger); font-size: 13px; }
</style>
