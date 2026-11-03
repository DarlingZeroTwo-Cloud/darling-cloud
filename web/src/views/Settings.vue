<script setup>
// 设置：个人设置 + WebDAV + 管理面板（管理员）
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
const selUser = ref(null)
const userFiles = ref([])

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

async function patchUser(u, body) {
  try {
    await api.patch(`/admin/users/${u.id}`, body)
    await load()
  } catch (e) { alert(e.message) }
}

async function resetPw(u) {
  const pw = prompt(`重置 ${u.username} 的密码（至少 6 位）`)
  if (pw && pw.length >= 6) await patchUser(u, { new_password: pw })
}

async function viewFiles(u) {
  selUser.value = u
  try { userFiles.value = await api.get(`/admin/users/${u.id}/files`) }
  catch (e) { alert(e.message) }
}

async function forceDelete(f) {
  if (!confirm(`强制删除「${f.name}」？（入回收站可恢复）`)) return
  try {
    await api.del(`/admin/users/${selUser.value.id}/files/${f.id}`)
    await viewFiles(selUser.value)
  } catch (e) { alert(e.message) }
}

async function setBackend(v) {
  if (v === 'remote') {
    alert('远程存储需在启动前设置环境变量 DARLING_REMOTE=远程挂载目录（如 /mnt/nas）\nNFS/SFTP 挂载另一台机器的目录后，新上传文件将写入扩容盘。')
  }
  try {
    await api.put('/admin/settings', { storage_backend: v })
    await load()
  } catch (e) { alert(e.message) }
}

function fmt(n) {
  if (n == null) return '-'
  if (n >= 1 << 30) return (n / (1 << 30)).toFixed(2) + ' GB'
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + ' MB'
  return n + ' B'
}

const davUrl = ref('')
function davPath() { return location.origin + '/dav/' }

onMounted(() => { if (getToken()) { load(); davUrl.value = davPath() } })
</script>

<template>
  <div>
    <div class="page-head"><h2>设置</h2></div>

    <div class="tabs" v-if="me">
      <button :class="['tab', tab==='profile' && 'on']" @click="tab='profile'">个人设置</button>
      <button :class="['tab', tab==='dav' && 'on']" @click="tab='dav'">WebDAV</button>
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

    <!-- WebDAV -->
    <div v-if="tab === 'dav'" class="card panel">
      <h3>WebDAV 访问</h3>
      <p class="tip">用系统文件管理器 / RaiDrive / rclone 等客户端挂载网盘，像本地文件夹一样读写。</p>
      <div class="row"><span>服务器地址</span><code class="url">{{ davUrl }}</code></div>
      <div class="row"><span>账号</span><b>{{ me?.username }}（用户名）</b></div>
      <div class="row"><span>密码</span><b>你的登录密码</b></div>
      <div class="row"><span>Windows 映射</span><b class="mono">文件管理器地址栏输入 {{ davUrl }} 后回车，填入账号密码</b></div>
      <div class="row"><span>rclone</span><b class="mono">rclone config → WebDAV → vendor: other → url: {{ davUrl }}</b></div>
    </div>

    <!-- 管理面板 -->
    <div v-if="tab === 'admin'">
      <div class="card panel">
        <h3>全站设置</h3>
        <div class="row"><span>允许自由注册</span>
          <select :value="settings.allow_register" @change="api.put('/admin/settings',{allow_register: $event.target.value==='1'})">
            <option value="1">开启</option><option value="0">关闭</option>
          </select>
        </div>
        <div class="row"><span>存储后端</span>
          <select :value="settings.storage_backend" @change="setBackend($event.target.value)">
            <option value="local">本地存储</option>
            <option value="remote">远程挂载扩容（DARLING_REMOTE）</option>
          </select>
        </div>
        <div class="row"><span>验证码强度</span>
          <select :value="settings.captcha_level" @change="api.put('/admin/settings',{captcha_level: $event.target.value})">
            <option value="easy">轻量（不刁难）</option><option value="medium">中等</option><option value="hard">严格</option>
          </select>
        </div>
      </div>

      <div class="card panel">
        <h3>用户组配额</h3>
        <table class="tbl">
          <tr><th>用户组</th><th>可上传</th><th>私有空间</th><th>公开空间</th></tr>
          <tr v-for="g in groups" :key="g.id">
            <td>{{ g.name }}</td><td>{{ g.can_upload ? '是' : '否' }}</td>
            <td>{{ fmt(g.priv_quota) }}</td><td>{{ fmt(g.pub_quota) }}</td>
          </tr>
        </table>
      </div>

      <div class="card panel">
        <h3>用户管理 <small class="hint">首个注册账号自动为管理员</small></h3>
        <table class="tbl">
          <tr><th>ID</th><th>用户名</th><th>邮箱</th><th>用户组</th><th>状态</th><th>操作</th></tr>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.id }}</td><td>{{ u.username }}</td><td>{{ u.email }}</td>
            <td>{{ u.group_name }}</td>
            <td><span :class="['st', u.is_active ? 'ok' : 'off']">{{ u.is_active ? '正常' : '停用' }}</span></td>
            <td class="ops">
              <button class="op" @click="patchUser(u,{is_active: !u.is_active})">{{ u.is_active ? '停用' : '启用' }}</button>
              <button class="op" @click="patchUser(u,{is_admin: !u.is_admin})">{{ u.is_admin ? '撤销管理员' : '设为管理员' }}</button>
              <button class="op" @click="resetPw(u)">重置密码</button>
              <button class="op" @click="viewFiles(u)">查看文件</button>
            </td>
          </tr>
        </table>
      </div>

      <!-- 用户文件（违规清理） -->
      <div v-if="selUser" class="card panel">
        <h3>{{ selUser.username }} 的文件 <small class="hint">管理员可强制清理违规内容</small></h3>
        <table class="tbl" v-if="userFiles.length">
          <tr><th>ID</th><th>名称</th><th>类型</th><th>大小</th><th>公开</th><th>上传时间</th><th>操作</th></tr>
          <tr v-for="f in userFiles" :key="f.id">
            <td>{{ f.id }}</td>
            <td>{{ f.name }}</td>
            <td>{{ f.is_dir ? '目录' : '文件' }}</td>
            <td>{{ f.is_dir ? '-' : fmt(f.size) }}</td>
            <td>{{ f.is_public ? '公开' : '私有' }}</td>
            <td class="muted">{{ (f.created_at||'').slice(0,16).replace('T',' ') }}</td>
            <td><button class="op danger" v-if="!f.is_dir" @click="forceDelete(f)">强制删除</button></td>
          </tr>
        </table>
        <div v-else class="empty"><p>该用户暂无文件</p></div>
      </div>

      <div class="card panel">
        <h3>分类管理</h3>
        <div class="cats">
          <span v-for="c in categories" :key="c.id" class="chip">{{ c.name }}</span>
        </div>
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
.panel { padding: 24px; margin-bottom: 14px; }
.panel h3 { font-size: 15px; margin: 24px 0 12px; }
.panel h3:first-child { margin-top: 0; }
.hint { color: var(--text-3); font-weight: 400; font-size: 12px; }
.tip { color: var(--text-2); font-size: 13px; margin-bottom: 12px; }
.row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px dashed var(--border); gap: 16px; }
.row:last-child { border-bottom: none; }
.row span { color: var(--text-2); flex-shrink: 0; }
.row select { padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text); }
.badge { background: var(--accent-soft); color: var(--accent); font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 6px; }
.url { font-size: 12.5px; color: var(--accent); word-break: break-all; }
.mono { font-size: 12px; font-family: ui-monospace, monospace; color: var(--text-2); text-align: right; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.tbl th { color: var(--text-2); font-weight: 500; }
.st { font-size: 11.5px; padding: 2px 8px; border-radius: 99px; }
.st.ok { background: rgba(22,163,74,.12); color: #16a34a; }
.st.off { background: rgba(220,38,38,.1); color: var(--danger); }
.ops { display: flex; gap: 4px; flex-wrap: wrap; }
.op { font-size: 12px; padding: 3px 8px; border-radius: 6px; color: var(--text-2); }
.op:hover { background: var(--bg-hover); color: var(--accent); }
.op.danger:hover { color: var(--danger); }
.muted { color: var(--text-3); font-size: 12px; }
.cats { display: flex; gap: 8px; flex-wrap: wrap; }
.chip { padding: 5px 12px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 13px; }
</style>
