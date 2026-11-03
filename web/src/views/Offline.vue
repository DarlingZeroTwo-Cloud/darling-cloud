<script setup>
// 离线下载：Aria2 任务管理（添加/进度/转存/取消）
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'

const url = ref('')
const tasks = ref([])
let timer = null

async function load() {
  try { tasks.value = await api.get('/offline') } catch (e) { alert(e.message) }
}

async function add() {
  if (!url.value.trim()) { alert('请输入 HTTP/磁力链接'); return }
  try {
    await api.post('/offline', { url: url.value.trim() })
    url.value = ''
    await load()
  } catch (e) { alert(e.message) }
}

async function transfer(t) {
  const name = prompt('转存文件名（默认保持原名）', t.url.split('/').pop() || t.url)
  try { await api.post(`/offline/${t.id}/transfer`, { name: name || null }); await load() }
  catch (e) { alert(e.message) }
}

async function cancel(t) {
  try { await api.del(`/offline/${t.id}`); await load() } catch (e) { alert(e.message) }
}

function fmt(n) {
  if (n >= 1<<30) return (n/(1<<30)).toFixed(2)+' GB'
  if (n >= 1<<20) return (n/(1<<20)).toFixed(1)+' MB'
  if (n >= 1024) return (n/1024).toFixed(1)+' KB'
  return n+' B'
}

const stMap = { queued: '排队中', active: '下载中', complete: '已完成', error: '失败', canceled: '已取消', transferred: '已转存' }

onMounted(() => { load(); timer = setInterval(load, 3000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div>
    <div class="page-head">
      <h2>离线下载</h2>
      <div class="add-row">
        <input v-model="url" class="ipt" placeholder="粘贴 HTTP/HTTPS/磁力链接，服务器后台下载…" @keyup.enter="add" />
        <button class="btn btn-primary" @click="add">添加任务</button>
      </div>
    </div>
    <div class="card table-card">
      <table class="otable" v-if="tasks.length">
        <thead><tr><th>链接</th><th>状态</th><th>进度</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.id">
            <td class="url" :title="t.url">{{ t.url }}</td>
            <td><span class="st" :class="t.status">{{ stMap[t.status] || t.status }}</span></td>
            <td class="prog">
              <div class="bar" v-if="t.status==='active'||t.status==='queued'||t.status==='complete'">
                <div class="fill" :style="{width: (t.progress||0)+'%'}"></div>
              </div>
              <span class="pct" v-if="t.progress != null">{{ t.progress }}%</span>
              <span class="pct muted" v-else>—</span>
            </td>
            <td class="ops">
              <button v-if="t.status==='complete'" class="op" @click="transfer(t)">转存到网盘</button>
              <button v-if="t.status==='active'||t.status==='queued'||t.status==='paused'" class="op danger" @click="cancel(t)">取消</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!tasks.length" class="empty"><p>没有离线任务 — 粘贴链接添加，服务器将自动下载</p></div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.page-head h2 { font-size: 18px; }
.add-row { display: flex; gap: 8px; flex: 1; max-width: 560px; }
.ipt { flex: 1; padding: 9px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text); font-size: 13.5px; }
.ipt:focus { outline: none; border-color: var(--accent); }
.otable { width: 100%; border-collapse: collapse; }
.otable th { text-align: left; padding: 10px 12px; font-size: 12px; color: var(--text-2); font-weight: 500; border-bottom: 1px solid var(--border); }
.otable td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
.otable tr:last-child td { border-bottom: none; }
.url { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st { font-size: 12px; padding: 2px 10px; border-radius: 99px; background: var(--bg-hover); color: var(--text-2); }
.st.active { background: var(--accent-soft); color: var(--accent); }
.st.complete, .st.transferred { background: rgba(22,163,74,.12); color: #16a34a; }
.st.error { background: rgba(220,38,38,.1); color: var(--danger); }
.prog { display: flex; align-items: center; gap: 8px; min-width: 130px; }
.bar { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.fill { height: 100%; background: var(--accent); }
.pct { font-size: 12px; color: var(--text-2); width: 44px; }
.muted { color: var(--text-3); }
.ops { display: flex; gap: 4px; }
.op { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; color: var(--text-2); }
.op:hover { background: var(--bg-hover); color: var(--accent); }
.op.danger:hover { color: var(--danger); }
</style>
