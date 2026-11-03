<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LogoCloud from '../components/LogoCloud.vue'
import { api, setToken } from '../api'

const route = useRoute()
const router = useRouter()
const form = ref({ username: '', password: '', remember: false })
const err = ref('')
const loading = ref(false)

async function submit() {
  err.value = ''
  if (!form.value.username || !form.value.password) { err.value = '请输入用户名和密码'; return }
  loading.value = true
  try {
    const d = await api.post('/auth/login', form.value)
    setToken(d.token)
    router.push(route.query.redirect || '/files')
  } catch (e) { err.value = e.message } finally { loading.value = false }
}

onMounted(() => { document.getElementById('u').focus() })
</script>

<template>
  <div class="auth-page">
    <div class="auth-card card">
      <div class="auth-head">
        <LogoCloud :size="44" />
        <h1>欢迎回来</h1>
        <p>登录 Darling Cloud 云盘</p>
      </div>
      <form @submit.prevent="submit">
        <div class="form-item">
          <label>用户名</label>
          <input id="u" v-model="form.username" placeholder="输入用户名" autocomplete="username" />
        </div>
        <div class="form-item">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="输入密码" autocomplete="current-password" />
        </div>
        <label class="remember">
          <input type="checkbox" v-model="form.remember" /> 记住我（30 天）
        </label>
        <p v-if="err" class="err-tip">{{ err }}</p>
        <button class="btn btn-primary submit" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登 录' }}
        </button>
      </form>
      <div class="auth-foot">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page { min-height: calc(100vh - 56px); display: flex; align-items: center; justify-content: center; padding: 24px; }
.auth-card { width: 380px; max-width: 100%; padding: 36px 32px; }
.auth-head { text-align: center; margin-bottom: 26px; }
.auth-head h1 { font-size: 22px; margin: 10px 0 4px; }
.auth-head p { color: var(--text-2); font-size: 13px; }
.remember { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-2); margin-bottom: 16px; cursor: pointer; }
.submit { width: 100%; padding: 11px; font-size: 15px; }
.auth-foot { text-align: center; margin-top: 20px; color: var(--text-2); font-size: 13px; }
</style>
