<script setup>
// 我的分享：创建/列表/复制链接/取消
import { ref, onMounted } from 'vue'
import { api } from '../api'

const shares = ref([])
const files = ref([])
const showNew = ref(false)
const form = ref({ file_id: null, password: '', expire_hours: 24, max_downloads: '' })

async function load() {
  try { shares.value = await api.get('/shares') } catch (e) { alert(e.message) }
  try { files.value = (await api.get('/files?parent_id=0')).filter(f => !f.is_dir) } catch (e) {}
}

async function create() {
  if (!form.value.file_id) { alert('请选择要分享的文件'); return }
  try {
    await api.post('/shares', {
      file_id: +form.value.file_id,
      password: form.value.password || null,
      expire_hours: form.value.expire_hours ? +form.value.expire_hours : null,
      max_downloads: form.value.max_downloads ? +form.value.max_downloads : null,
    })
    form.value = { file_id: null, password: '', expire_hours: 24, max_downloads: '' }
    showNew.value = false
    await load()
  } catch (e) { alert(e.message) }
}

function link(s) { return location.origin + '/s/' + s.token }

async function copy(s) {
  try { await navigator.clipboard.writeText(link(s)); alert('链接已复制') }
  catch { prompt('复制链接', link(s)) }
}

async function remove(s) {
  if (!confirm('取消该分享？链接将失效')) return
  try { await api.del(`/shares/${s.id}`); await load() } catch (e) { alert(e.message) }
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
  <div>
    <div class="page-head">
      <h2>我的分享</h2>
      <button class="btn btn-primary" @click="showNew = !showNew">{{ showNew ? '收起' : '新建分享' }}</button>
    </div>

    <div v-if="showNew" class="card new-share">
      <h3>创建分享链接</h3>
      <div class="row">
        <select v-model="form.file_id" class="ipt">
          <option :value="null" disabled>选择私有文件</option>
          <option v-for="f in files" :key="f.id" :value="f.id">{{ f.name }} ({{ fmt(f.size) }})</option>
        </select>
        <input v-model="form.password" class="ipt" placeholder="提取码（留空则无需密码）" />
        <input v-model="form.expire_hours" class="ipt num" type="number" min="0" placeholder="有效小时（留空永久）" />
        <input v-model="form.max_downloads" class="ipt num" type="number" min="0" placeholder="下载次数上限（留空不限）" />
      </div>
      <button class="btn btn-primary" @click="create">生成链接</button>
    </div>

    <div class="card table-card">
      <table class="stable" v-if="shares.length">
        <thead><tr><th>文件</th><th>链接</th><th>提取码</th><th>次数</th><th>过期</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="s in shares" :key="s.id">
            <td>{{ s.file_name }}</td>
            <td class="link">{{ link(s) }}</td>
            <td>{{ s.password || '无' }}</td>
            <td>{{ s.downloads }}{{ s.max_downloads ? ' / ' + s.max_downloads : '' }}</td>
            <td class="muted">{{ s.expire_at ? s.expire_at.slice(0,16).replace('T',' ') : '永久' }}</td>
            <td class="ops">
              <button class="op" @click="copy(s)">复制</button>
              <button class="op danger" @click="remove(s)">取消分享</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!shares.length" class="empty"><p>还没有分享 — 点击「新建分享」生成链接</p></div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.page-head h2 { font-size: 18px; }
.new-share { padding: 16px; margin-bottom: 14px; display: flex; flex-direction: column; gap: 10px; }
.new-share h3 { font-size: 15px; }
.new-share .row { display: flex; gap: 8px; flex-wrap: wrap; }
.ipt { padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text); font-size: 13.5px; }
.ipt:focus { outline: none; border-color: var(--accent); }
.num { width: 130px; }
.stable { width: 100%; border-collapse: collapse; }
.stable th { text-align: left; padding: 10px 12px; font-size: 12px; color: var(--text-2); font-weight: 500; border-bottom: 1px solid var(--border); }
.stable td { padding: 9px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
.stable tr:last-child td { border-bottom: none; }
.stable tr:hover td { background: var(--bg-hover); }
.link { color: var(--accent); font-size: 12.5px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.muted { color: var(--text-3); font-size: 12px; }
.ops { display: flex; gap: 4px; }
.op { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; color: var(--text-2); }
.op:hover { background: var(--bg-hover); color: var(--accent); }
.op.danger:hover { color: var(--danger); }
</style>
