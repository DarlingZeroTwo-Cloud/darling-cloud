<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LogoCloud from '../components/LogoCloud.vue'
import { api, setToken } from '../api'

const router = useRouter()
const form = ref({ username: '', password: '', email: '', captcha_id: '', captcha_answer: '' })
const capUrl = ref('')
const err = ref('')
const loading = ref(false)

async function freshCaptcha() {
  const { blob, id } = await api.captcha()
  capUrl.value = URL.createObjectURL(blob)
  form.value.captcha_id = id
}

async function submit() {
  err.value = ''
  const f = form.value
  if (!f.username || !f.password || !f.email || !f.captcha_answer) { err.value = '请填写完整信息'; return }
  if (f.username.length < 2) { err.value = '用户名至少 2 个字符'; return }
  if (f.password.length < 6) { err.value = '密码至少 6 位'; return }
  loading.value = true
  try {
    const d = await api.post('/auth/register', f)
    setToken(d.token)
    router.push(d.user.is_admin ? '/settings' : '/files')
  } catch (e) {
    err.value = e.message
    freshCaptcha()  // 验证码单次消费，失败自动换新
    form.value.captcha_answer = ''
  } finally { loading.value = false }
}

onMounted(() => { freshCaptcha(); document.getElementById('u').focus() })
</script>

<template>
  <div class="auth-page">
    <div class="auth-card card">
      <div class="auth-head">
        <LogoCloud :size="44" />
        <h1>创建账号</h1>
        <p>第一个注册的账号将成为管理员</p>
      </div>
      <form @submit.prevent="submit">
        <div class="form-item">
          <label>用户名（唯一）</label>
          <input id="u" v-model="form.username" placeholder="2-32 个字符" autocomplete="username" />
        </div>
        <div class="form-item">
          <label>邮箱</label>
          <input v-model="form.email" type="email" placeholder="仅用于记录，不验证" autocomplete="email" />
        </div>
        <div class="form-item">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="至少 6 位" autocomplete="new-password" />
        </div>
        <div class="form-item">
          <label>人机验证</label>
          <div class="cap-row">
            <img v-if="capUrl" :src="capUrl" alt="验证码" class="cap-img" @click="freshCaptcha" title="看不清？点我换一张" />
            <input v-model="form.captcha_answer" placeholder="计算结果" class="cap-input" />
          </div>
          <div class="cap-hint">算出结果填入，看不清点图片换一张</div>
        </div>
        <p v-if="err" class="err-tip">{{ err }}</p>
        <button class="btn btn-primary submit" type="submit" :disabled="loading">
          {{ loading ? '注册中…' : '注册并登录' }}
        </button>
      </form>
      <div class="auth-foot">
        已有账号？<router-link to="/login">去登录</router-link>
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
.cap-row { display: flex; gap: 10px; }
.cap-img { height: 42px; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; background: #fff; }
.cap-input { flex: 1; }
.cap-hint { font-size: 12px; color: var(--text-3); margin-top: 5px; }
.submit { width: 100%; padding: 11px; font-size: 15px; }
.auth-foot { text-align: center; margin-top: 20px; color: var(--text-2); font-size: 13px; }
</style>
