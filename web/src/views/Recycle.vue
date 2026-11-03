<script setup>
// 回收站：M2 接入恢复/彻底删除
</script>

<template>
  <div>
    <div class="page-head">
      <h2>回收站</h2>
      <div class="actions"><button class="btn btn-ghost">清空回收站</button></div>
    </div>
    <div class="card table-card">
      <div class="empty">
        <div class="icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M3 6h18m-8 4v6m-4-6v6M6 6l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13M10 6V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"/></svg>
        </div>
        <p>回收站 — 删除的文件在这里，支持恢复（M2 开放）</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { font-size: 18px; }
.table-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
</style>
