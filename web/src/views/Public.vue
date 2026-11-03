<script setup>
// 公开广场：免登录浏览/搜索/下载；登录后可上传公开资源（须简介+分类）
import { ref, onMounted } from 'vue'
import { api, getToken } from '../api'

const logged = ref(!!getToken())
const files = ref([])
const categories = ref([])
const keyword = ref('')
const cat = ref('')
const sort = ref('new')
const loading = ref(false)
const showUpload = ref(false)
const up = ref({ name: '', desc: '', category_id: null })
const uploading = ref(false)

function fmt(n) {
  if (n >= 1<<30) return (n/(1<<30)).toFixed(2)+' GB'
  if (n >= 1<<20) return (n/(1<<20)).toFixed(1)+' MB'
  if (n >= 1024) return (n/1024).toFixed(1)+' KB'
  return n+' B'
}

async function load() {
  loading.value = true
  try {
    const qs = new URLSearchParams()
    if (keyword.value) qs.set('keyword', keyword.value)
    if (cat.value) qs.set('category_id', cat.value)
    if (sort.value) qs.set('sort', sort.value)
    const r = await api.get(`/public/files?${qs}`)
    files.value = r.files
    categories.value = r.categories
  } catch (e) { alert(e.message) } finally { loading.value = false }
}

function download(f) {
  const a = document.createElement('a')
  a.href = `/api/public/files/${f.id}/download`
  document.body.appendChild(a); a.click(); a.remove()
}

async function uploadPub(e) {
  const file = e.target.files[0]; e.target.value = ''
  if (!file) return
  if (!up.value.desc.trim()) { alert('公开上传必须填写简介'); return }
  if (!up.value.category_id) { alert('公开上传必须选择分类'); return }
  uploading.value = true
  try {
    const buf = new Uint8Array(await file.arrayBuffer())
    const hash = await crypto.subtle.digest('SHA-256', buf).then(h => [...new Uint8Array(h)].map(b=>b.toString(16).padStart(2,'0')).join(''))
    const init = await api.post('/upload/init', { name: file.name, size: buf.length, sha256: hash, is_public: true, category_id: up.value.category_id, desc_text: up.value.desc.trim() })
    if (!init.instant) {
      const form = new FormData()
      form.append('file', new Blob([buf]))
      await fetch(`/api/upload/${init.upload_id}/chunk/0`, { method: 'POST', headers: { Authorization: `Bearer ${getToken()}` }, body: form })
      await api.post(`/upload/${init.upload_id}/complete`, { sha256: hash })
    }
    up.value = { name: '', desc: '', category_id: null }
    showUpload.value = false
    await load()
  } catch (err) { alert(err.message) } finally { uploading.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2>公开广场</h2>
      <div class="toolbar">
        <input v-model="keyword" class="ipt" placeholder="搜索名称或简介…" @keyup.enter="load" />
        <select v-model="cat" class="ipt sel" @change="load">
          <option value="">全部分类</option>
          <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <select v-model="sort" class="ipt sel" @change="load">
          <option value="new">最新上传</option>
          <option value="hot">下载最多</option>
        </select>
        <button class="btn" @click="load">搜索</button>
        <button v-if="logged && !showUpload" class="btn btn-primary" @click="showUpload = true">上传公开资源</button>
      </div>
    </div>

    <div v-if="showUpload" class="card pub-upload">
      <h3>上传公开资源 <small>需填写简介与分类</small></h3>
      <input v-model="up.desc" class="ipt" placeholder="简介：这个文件是什么、适合谁用…" />
      <div class="row">
        <select v-model="up.category_id" class="ipt sel">
          <option :value="null" disabled>选择分类</option>
          <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <label class="btn btn-primary">
          {{ uploading ? '上传中…' : '选择文件上传' }}
          <input type="file" hidden @change="uploadPub" />
        </label>
      </div>
    </div>

    <div class="pub-grid">
      <div v-for="f in files" :key="f.id" class="card pub-item">
        <div class="pub-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path d="M14 2v6h6"/>
          </svg>
        </div>
        <div class="pub-body">
          <div class="pub-name" :title="f.name">{{ f.name }}</div>
          <div class="pub-desc">{{ f.desc_text || '（无简介）' }}</div>
          <div class="pub-meta">
            <span>{{ fmt(f.size) }}</span><span>·</span><span>{{ f.owner }}</span>
            <span>·</span><span>{{ f.download_count }} 下载</span>
            <span class="cat" v-if="f.category_id">{{ (categories.find(c=>c.id===f.category_id)||{}).name }}</span>
          </div>
        </div>
        <button class="btn btn-primary sm" @click="download(f)">下载</button>
      </div>
    </div>
    <div v-if="!files.length && !loading" class="empty">
      <p>暂无公开资源 — 点击「上传公开资源」分享你的文件</p>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.page-head h2 { font-size: 18px; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
.ipt { padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text); font-size: 13.5px; min-width: 120px; }
.ipt:focus { outline: none; border-color: var(--accent); }
.sel { min-width: 110px; }
.pub-upload { padding: 16px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 10px; }
.pub-upload h3 { font-size: 15px; } .pub-upload h3 small { color: var(--text-3); font-weight: 400; }
.pub-upload .row { display: flex; gap: 10px; }
.pub-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.pub-item { padding: 14px; display: flex; align-items: center; gap: 12px; }
.pub-icon { width: 40px; height: 40px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.pub-icon svg { width: 22px; height: 22px; }
.pub-body { flex: 1; min-width: 0; }
.pub-name { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pub-desc { font-size: 12.5px; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 3px 0; }
.pub-meta { font-size: 11.5px; color: var(--text-3); display: flex; gap: 5px; align-items: center; flex-wrap: wrap; }
.cat { background: var(--bg-hover); padding: 1px 8px; border-radius: 99px; }
.btn.sm { padding: 6px 12px; font-size: 12.5px; flex-shrink: 0; }
</style>
