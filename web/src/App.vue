<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LogoCloud from './components/LogoCloud.vue'
import { api, getToken, setToken } from './api'

const route = useRoute()
const router = useRouter()
const user = ref(null)
const showUserMenu = ref(false)

const nav = [
  { to: '/', label: '公开广场', icon: 'M2 20h20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v14m16-6h.01M4 14l4-4 4 4m8-2h.01M8 8h.01' },
  { to: '/files', label: '我的文件', icon: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z' },
  { to: '/shares', label: '我的分享', icon: 'M13 7l5 5-5 5M7 7l-5 5 5 5' },
  { to: '/recycle', label: '回收站', icon: 'M3 6h18m-8 4v6m-4-6v6M6 6l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13M10 6V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2' },
  { to: '/settings', label: '设置', icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.5 7.5 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.06-.4.1-.8.1-1.2z' },
]

async function loadMe() {
  try {
    user.value = (await api.get('/auth/me')).user
  } catch { user.value = null }
}

function logout() {
  setToken(null)
  user.value = null
  router.push('/')
}

onMounted(() => {
  if (getToken()) loadMe()
})
</script>

<template>
  <div class="shell">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="brand" @click="router.push('/')">
        <LogoCloud :size="28" />
        <span class="brand-name">Darling Cloud</span>
      </div>

      <nav class="topnav" v-if="route.name === 'public'">
        <router-link to="/" class="nav-link" active-class="on">公开广场</router-link>
        <router-link to="/files" class="nav-link">我的文件</router-link>
        <router-link to="/shares" class="nav-link">我的分享</router-link>
        <router-link to="/offline" class="nav-link">离线下载</router-link>
      </nav>

      <div class="top-right">
        <template v-if="user">
          <span class="user-chip" @click="showUserMenu = !showUserMenu">
            <span class="avatar">{{ (user.nickname || user.username).charAt(0).toUpperCase() }}</span>
            <span>{{ user.nickname || user.username }}</span>
            <span v-if="user.is_admin" class="admin-badge">管理员</span>
          </span>
          <div v-if="showUserMenu" class="user-menu card">
            <div class="um-item" @click="router.push('/help'); showUserMenu=false">帮助与部署</div>
            <div class="um-item" @click="router.push('/settings'); showUserMenu=false">设置</div>
            <div class="um-item" @click="router.push('/settings'); showUserMenu=false">清缓存</div>
            <div class="um-item danger" @click="logout">退出登录</div>
          </div>
        </template>
        <template v-else>
          <button class="btn btn-ghost" @click="router.push('/login')">登录</button>
          <button class="btn btn-primary" @click="router.push('/register')">注册</button>
          <button class="btn btn-ghost" @click="router.push('/help')">帮助</button>
        </template>
      </div>
    </header>

    <!-- 主体 -->
    <main class="main">
      <router-view :key="route.fullPath" />
    </main>
  </div>
</template>

<style scoped>
.shell { min-height: 100%; display: flex; flex-direction: column; }
.topbar {
  position: sticky; top: 0; z-index: 20;
  height: 56px; display: flex; align-items: center; gap: 20px;
  padding: 0 20px;
  background: color-mix(in srgb, var(--bg-card) 88%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 600; font-size: 16px; }
.brand-name { letter-spacing: .2px; }
.topnav { display: flex; gap: 4px; }
.nav-link { padding: 6px 12px; border-radius: 8px; color: var(--text-2); font-weight: 500; }
.nav-link:hover { background: var(--bg-hover); color: var(--text); }
.nav-link.on { color: var(--accent); background: var(--accent-soft); }
.top-right { margin-left: auto; display: flex; align-items: center; gap: 8px; position: relative; }
.user-chip { display: flex; align-items: center; gap: 8px; padding: 4px 10px 4px 4px; border-radius: 999px; cursor: pointer; }
.user-chip:hover { background: var(--bg-hover); }
.avatar {
  width: 32px; height: 32px; border-radius: 50%; background: var(--accent);
  color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 600;
}
.admin-badge { font-size: 11px; background: var(--accent-soft); color: var(--accent); padding: 2px 6px; border-radius: 4px; }
.user-menu { position: absolute; top: 44px; right: 0; min-width: 160px; padding: 6px; z-index: 30; }
.um-item { padding: 8px 12px; border-radius: 8px; cursor: pointer; }
.um-item:hover { background: var(--bg-hover); }
.um-item.danger { color: var(--danger); }
.main { flex: 1; width: 100%; max-width: 1200px; margin: 0 auto; padding: 24px 20px 48px; }
</style>
