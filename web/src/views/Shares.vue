<script setup>
// 我的分享：M3 接入分享管理
</script>

<template>
  <div>
    <div class="page-head">
      <h2>我的分享</h2>
      <button class="btn btn-primary">新建分享</button>
    </div>
    <div class="card table-card">
      <div class="empty">
        <div class="icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M13 7l5 5-5 5M7 7l-5 5 5 5"/></svg>
        </div>
        <p>分享链接管理将在 M3 开放（过期时间 / 提取码 / 下载次数）</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { font-size: 18px; }
.table-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
</style>
