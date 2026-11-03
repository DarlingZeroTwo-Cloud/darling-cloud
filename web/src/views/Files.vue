<script setup>
// 我的文件（私有空间）：上传/列表/下载/打包/星标/回收站
import { ref, onMounted, computed } from 'vue'
import { api, getToken } from '../api'

const files = ref([])
const path = ref([])          // 路径栈 [{id,name}]
const loading = ref(false)
const selected = ref(new Set())
const uploading = ref([])     // 上传队列 {name, pct, status}
const curDir = computed(() => path.value.length ? path.value[path.value.length-1].id : 0)
const quota = ref(null)

function fmt(n) {
  if (n == null) return '-'
  if (n >= 1<<30) return (n/(1<<30)).toFixed(2)+' GB'
  if (n >= 1<<20) return (n/(1<<20)).toFixed(1)+' MB'
  if (n >= 1024) return (n/1024).toFixed(1)+' KB'
  return n+' B'
}

async function load() {
  loading.value = true
  try {
    files.value = await api.get(`/files?parent_id=${curDir.value}`)
    quota.value = await api.get('/user/quota')
  } catch (e) { alert(e.message) } finally { loading.value = false }
}

async function openDir(f) {
  if (!f.is_dir) return
  path.value.push({ id: f.id, name: f.name })
  selected.value.clear()
  await load()
}

async function up() {
  path.value.pop()
  selected.value.clear()
  await load()
}

async function newDir() {
  const name = prompt('新建文件夹名称')
  if (!name) return
  try { await api.post(`/files/dir?name=${encodeURIComponent(name)}&parent_id=${curDir.value}`); await load() }
  catch (e) { alert(e.message) }
}

async function toggleStar(f) {
  try { await api.patch(`/files/${f.id}?star=${!f.star}`); await load() }
  catch (e) { alert(e.message) }
}

async function rename(f) {
  const name = prompt('重命名', f.name)
  if (!name || name === f.name) return
  try { await api.patch(`/files/${f.id}?name=${encodeURIComponent(name)}`); await load() }
  catch (e) { alert(e.message) }
}

async function trash(f) {
  if (!confirm(`删除「${f.name}」？将移入回收站`)) return
  try { await api.del(`/files/${f.id}`); await load() }
  catch (e) { alert(e.message) }
}

function download(f) {
  if (f.is_dir) { alert('文件夹请用打包下载'); return }
  const a = document.createElement('a')
  a.href = `/api/files/${f.id}/download`
  a.href += (a.href.includes('?') ? '&' : '?') + 't=' + getToken()
  document.body.appendChild(a); a.click(); a.remove()
}

async function downloadSel() {
  const ids = [...selected.value]
  if (!ids.length) { alert('请先勾选文件'); return }
  const a = document.createElement('a')
  a.href = `/api/zip?ids=${ids.join(',')}&t=${getToken()}`
  document.body.appendChild(a); a.click(); a.remove()
}

// 分片上传（8MB chunk + 进度 + 断点续传）
async function uploadFiles(e) {
  const input = e.target
  const list = [...input.files]
  input.value = ''
  for (const file of list) {
    const item = { name: file.name, pct: 0, status: '上传中' }
    uploading.value.push(item)
    try {
      await uploadOne(file, item)
      item.status = '完成'
    } catch (err) {
      item.status = '失败: ' + err.message
    }
  }
  await load()
}

async function uploadOne(file, item) {
  const data = new Uint8Array(await file.arrayBuffer())
  const sha = await sha256(data)
  const size = data.length
  // init（服务端检测秒传）
  const init = await api.post('/upload/init', {
    name: file.name, size, sha256: sha, parent_id: curDir.value
  })
  if (init.instant) { item.pct = 100; item.status = '秒传'; return }
  // 断点：跳过已上传分片
  const done = new Set(init.received || [])
  const CH = init.chunk_size
  const total = init.chunks
  let sent = done.size
  for (let i = 0; i < total; i++) {
    if (done.has(i)) continue
    const slice = data.slice(i*CH, Math.min((i+1)*CH, size))
    const form = new FormData()
    form.append('file', new Blob([slice]))
    await fetch(`/api/upload/${init.upload_id}/chunk/${i}`, {
      method: 'POST', headers: { Authorization: `Bearer ${getToken()}` }, body: form
    })
    sent++
    item.pct = Math.round(sent/total*100)
  }
  await api.post(`/upload/${init.upload_id}/complete`, { sha256: sha })
  item.pct = 100
}

function sha256(buf) {
  return crypto.subtle.digest('SHA-256', buf).then(h => [...new Uint8Array(h)].map(b=>b.toString(16).padStart(2,'0')).join(''))
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div class="crumbs">
        <h2>
          <button class="crumb" @click="path=[]; load()">我的文件</button>
          <template v-for="(p,i) in path" :key="p.id">
            <span class="sep">/</span>
            <button class="crumb" @click="path.splice(i+1); load()">{{ p.name }}</button>
          </template>
        </h2>
        <div class="quota" v-if="quota">
          私有空间 {{ fmt(quota.priv_used) }} / {{ fmt(quota.priv_quota) }}
        </div>
      </div>
      <div class="actions">
        <label class="btn btn-primary up-btn">
          上传文件
          <input type="file" multiple hidden @change="uploadFiles" />
        </label>
        <button class="btn btn-ghost" @click="newDir">新建文件夹</button>
        <button class="btn btn-ghost" @click="downloadSel" :disabled="!selected.size">打包下载 ({{ selected.size }})</button>
      </div>
    </div>

    <!-- 上传队列 -->
    <div v-if="uploading.length" class="card up-queue">
      <div v-for="(u,i) in uploading" :key="i" class="up-item">
        <span class="up-name">{{ u.name }}</span>
        <div class="up-bar"><div class="up-fill" :style="{width: u.pct+'%'}"></div></div>
        <span class="up-pct">{{ u.pct }}%</span>
        <span class="up-status" :class="{done: u.status==='完成'||u.status==='秒传', fail: u.status.startsWith('失败')}">{{ u.status }}</span>
      </div>
    </div>

    <div class="card table-card">
      <table class="ftable">
        <thead>
          <tr>
            <th style="width:32px"><input type="checkbox" :checked="selected.size===files.length && files.length>0" @change="selected = $event.target.checked ? new Set(files.map(f=>f.id)) : new Set()" /></th>
            <th>名称</th>
            <th style="width:100px">大小</th>
            <th style="width:160px">修改时间</th>
            <th style="width:150px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in files" :key="f.id" :class="{sel: selected.has(f.id)}" @dblclick="openDir(f)">
            <td @click.stop><input type="checkbox" :checked="selected.has(f.id)" @change="selected.has(f.id) ? selected.delete(f.id) : selected.add(f.id)" /></td>
            <td class="fname" @click="openDir(f)">
              <svg v-if="f.is_dir" class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>
              <svg v-else class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path d="M14 2v6h6"/></svg>
              <span>{{ f.name }}</span>
              <svg v-if="f.star" class="star" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.8 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8L12 2z"/></svg>
            </td>
            <td>{{ f.is_dir ? '—' : fmt(f.size) }}</td>
            <td class="muted">{{ f.updated_at?.slice(0,16).replace('T',' ') }}</td>
            <td class="ops">
              <button class="op" title="下载" v-if="!f.is_dir" @click="download(f)">下载</button>
              <button class="op" title="重命名" @click="rename(f)">重命名</button>
              <button class="op" :title="f.star?'取消星标':'星标'" @click="toggleStar(f)">{{ f.star ? '取消星标' : '星标' }}</button>
              <button class="op danger" title="删除" @click="trash(f)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!files.length && !loading" class="empty">
        <div class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M18 10h-1.3A7 7 0 1 0 9 3a7 7 0 0 0-6.2 7H2a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2z" transform="translate(4 2)"/></svg></div>
        <p>空目录 — 点「上传文件」开始</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.crumbs h2 { font-size: 18px; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.crumb { font-size: 17px; font-weight: 600; color: var(--text); padding: 2px 4px; border-radius: 6px; }
.crumb:hover { color: var(--accent); }
.sep { color: var(--text-3); }
.quota { font-size: 12px; color: var(--text-3); margin-top: 6px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.up-btn { position: relative; overflow: hidden; }
.table-card { overflow: hidden; }
.ftable { width: 100%; border-collapse: collapse; }
.ftable th { text-align: left; padding: 10px 12px; font-size: 12px; color: var(--text-2); font-weight: 500; border-bottom: 1px solid var(--border); }
.ftable td { padding: 9px 12px; border-bottom: 1px solid var(--border); font-size: 13.5px; }
.ftable tr:last-child td { border-bottom: none; }
.ftable tr:hover td { background: var(--bg-hover); }
.ftable tr.sel td { background: var(--accent-soft); }
.fname { cursor: pointer; display: flex; align-items: center; gap: 8px; }
.fic { width: 18px; height: 18px; color: var(--accent); flex-shrink: 0; }
.star { width: 14px; height: 14px; color: #f5b50a; flex-shrink: 0; }
.muted { color: var(--text-3); font-size: 12.5px; }
.ops { display: flex; gap: 4px; }
.op { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; color: var(--text-2); }
.op:hover { background: var(--bg-hover); color: var(--accent); }
.op.danger:hover { color: var(--danger); }
.up-queue { padding: 12px 16px; margin-bottom: 14px; }
.up-item { display: flex; align-items: center; gap: 10px; padding: 5px 0; }
.up-name { width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.up-bar { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.up-fill { height: 100%; background: var(--accent); transition: width .2s; }
.up-pct { width: 44px; text-align: right; font-size: 12px; color: var(--text-2); }
.up-status { width: 110px; font-size: 12px; color: var(--text-2); }
.up-status.done { color: var(--ok); }
.up-status.fail { color: var(--danger); }
</style>
