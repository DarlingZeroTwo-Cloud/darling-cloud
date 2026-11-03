// API 封装：统一请求 + token 管理
const BASE = '/api'

export function getToken() {
  return localStorage.getItem('dc_token') || ''
}

export function setToken(t) {
  if (t) localStorage.setItem('dc_token', t)
  else localStorage.removeItem('dc_token')
}

async function req(method, path, body, opts = {}) {
  const headers = { ...(opts.headers || {}) }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body instanceof FormData ? body : (body !== undefined ? JSON.stringify(body) : undefined),
    ...opts.fetch
  })
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const d = await res.json()
      if (d.detail) msg = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail)
    } catch (e) { /* ignore */ }
    throw new Error(msg)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),
  patch: (p, b) => req('PATCH', p, b),
  put: (p, b) => req('PUT', p, b),
  del: (p) => req('DELETE', p),
  // 验证码：返回 blob 图片 + 从响应头取 captcha id
  async captcha() {
    const res = await fetch(BASE + '/auth/captcha')
    const blob = await res.blob()
    return { blob, id: res.headers.get('x-captcha-id') }
  },
  // 带进度上传
  upload(url, formData, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', BASE + url)
      const token = getToken()
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
      }
      xhr.onload = () => {
        try { resolve(JSON.parse(xhr.responseText)) }
        catch { reject(new Error('响应解析失败')) }
      }
      xhr.onerror = () => reject(new Error('网络错误'))
      xhr.send(formData)
    })
  }
}
