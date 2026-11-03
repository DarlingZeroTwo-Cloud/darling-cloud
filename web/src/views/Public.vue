<script setup>
// 公开广场：未登录可直接浏览下载（M3 接入公开区 API）
import { ref, onMounted } from 'vue'
import { api } from '../api'

const files = ref([])
const cats = ref([])
const loading = ref(true)
const keyword = ref('')
const catId = ref('')

onMounted(async () => {
  try {
    const d = await api.get('/public/files')
    files.value = d.files || []
    cats.value = d.categories || []
  } catch { /* M3 未接入时静默 */ }
  loading.value = false
})
</script>

<template>
  <div class="public-page">
    <div class="hero card">
      <h1>公开资源广场</h1>
      <p>来自社区用户上传的公开资源，无需登录即可浏览与下载</p>
      <div class="search-row">
        <input v-model="keyword" placeholder="搜索公开资源…" />
        <select v-model="catId">
          <option value="">全部分类</option>
          <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <button class="btn btn-primary">搜索</button>
      </div>
    </div>

    <div class="cat-chips">
      <span class="chip on">全部</span>
      <span class="chip" v-for="c in cats" :key="c.id">{{ c.name }}</span>
    </div>

    <div class="grid">
      <div v-for="f in files" :key="f.id" class="file-card card">
        <div class="fc-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/><path d="M14 2v6h6"/></svg>
        </div>
        <div class="fc-name" :title="f.name">{{ f.name }}</div>
        <div class="fc-desc">{{ f.desc_text || '暂无简介' }}</div>
        <div class="fc-meta">{{ f.size }} · {{ f.download_count }} 次下载</div>
      </div>
    </div>
    <div v-if="!files.length && !loading" class="empty">
      <div class="icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M18 10h-1.3A7 7 0 1 0 9 3a7 7 0 0 0-6.2 7H2a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2z" transform="translate(4 2)"/></svg>
      </div>
      <p>公开资源区正在建设中，敬请期待</p>
    </div>
  </div>
</template>

<style scoped>
.hero { padding: 32px; text-align: center; margin-bottom: 20px; }
.hero h1 { font-size: 24px; margin-bottom: 6px; }
.hero p { color: var(--text-2); margin-bottom: 20px; }
.search-row { display: flex; gap: 10px; max-width: 520px; margin: 0 auto; }
.search-row input { flex: 1; }
.cat-chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
.chip { padding: 6px 14px; border-radius: 999px; background: var(--bg-card); border: 1px solid var(--border); cursor: pointer; font-size: 13px; color: var(--text-2); }
.chip.on { background: var(--accent-soft); color: var(--accent); border-color: transparent; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; }
.file-card { padding: 16px; cursor: pointer; transition: transform .12s, box-shadow .12s; }
.file-card:hover { transform: translateY(-2px); }
.fc-icon { font-size: 30px; margin-bottom: 8px; }
.fc-icon svg { width: 30px; height: 30px; color: var(--accent); }
.fc-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fc-desc { color: var(--text-2); font-size: 12px; margin: 4px 0; height: 32px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.fc-meta { color: var(--text-3); font-size: 12px; }
</style>
