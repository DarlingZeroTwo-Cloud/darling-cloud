<script setup>
// 我的文件（私有空间）：M2 接入上传/下载/目录 API
</script>

<template>
  <div>
    <div class="page-head">
      <h2>我的文件</h2>
      <div class="actions">
        <button class="btn btn-ghost">上传</button>
        <button class="btn btn-ghost">新建文件夹</button>
        <button class="btn btn-primary">离线下载</button>
      </div>
    </div>
    <div class="card table-card">
      <div class="empty">
        <div class="icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M18 10h-1.3A7 7 0 1 0 9 3a7 7 0 0 0-6.2 7H2a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2z" transform="translate(4 2)"/></svg>
        </div>
        <p>私有空间 — 文件上传、秒传、断点续传将在 M2 开放</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { font-size: 18px; }
.actions { display: flex; gap: 8px; }
.table-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
</style>
