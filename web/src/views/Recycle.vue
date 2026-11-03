<script setup>
// 回收站：恢复 / 彻底删除 / 清空
import { ref, onMounted } from 'vue'
import { api } from '../api'

const items = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try { items.value = await api.get('/recycle') }
  catch (e) { alert(e.message) } finally { loading.value = false }
}

function fmt(n) {
  if (n == null) return '-'
  if (n >= 1<<30) return (n/(1<<30)).toFixed(2)+' GB'
  if (n >= 1<<20) return (n/(1<<20)).toFixed(1)+' MB'
  return n+' B'
}

async function restore(f) {
  try { await api.post(`/recycle/${f.id}/restore`); await load() }
  catch (e) { alert(e.message) }
}

async function remove(f) {
  if (!confirm(`彻底删除「${f.name}」？不可恢复`)) return
  try { await api.del(`/recycle/${f.id}`); await load() }
  catch (e) { alert(e.message) }
}

async function clearAll() {
  if (!confirm('清空回收站？其中所有文件将被彻底删除')) return
  try { await api.post('/recycle/clear'); await load() }
  catch (e) { alert(e.message) }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2>回收站</h2>
      <button class="btn btn-ghost" @click="clearAll" :disabled="!items.length">清空回收站</button>
    </div>
    <div class="card table-card">
      <table class="rtable" v-if="items.length">
        <thead><tr><th>名称</th><th>大小</th><th>删除时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="f in items" :key="f.id">
            <td class="fname">
              <svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                <path v-if="f.is_dir" d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>
                <path v-else d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path v-if="!f.is_dir" d="M14 2v6h6"/>
              </svg>
              {{ f.name }}
            </td>
            <td class="muted">{{ f.is_dir ? '—' : fmt(f.size) }}</td>
            <td class="muted">{{ f.deleted_at?.slice(0,16).replace('T',' ') }}</td>
            <td class="ops">
              <button class="op" @click="restore(f)">恢复</button>
              <button class="op danger" @click="remove(f)">彻底删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!items.length && !loading" class="empty">
        <div class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M3 6h18m-8 4v6m-4-6v6M6 6l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13M10 6V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"/></svg></div>
        <p>回收站是空的</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.page-head h2 { font-size: 18px; }
.rtable { width: 100%; border-collapse: collapse; }
.rtable th { text-align: left; padding: 10px 12px; font-size: 12px; color: var(--text-2); font-weight: 500; border-bottom: 1px solid var(--border); }
.rtable td { padding: 9px 12px; border-bottom: 1px solid var(--border); font-size: 13.5px; }
.rtable tr:last-child td { border-bottom: none; }
.rtable tr:hover td { background: var(--bg-hover); }
.fname { display: flex; align-items: center; gap: 8px; }
.fic { width: 18px; height: 18px; color: var(--accent); flex-shrink: 0; }
.muted { color: var(--text-3); font-size: 12.5px; }
.ops { display: flex; gap: 4px; }
.op { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; color: var(--text-2); }
.op:hover { background: var(--bg-hover); color: var(--accent); }
.op.danger:hover { color: var(--danger); }
</style>
