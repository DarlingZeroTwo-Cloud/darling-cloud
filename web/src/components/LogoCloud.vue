<script setup>
defineProps({ size: { type: Number, default: 32 } })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" class="dc-logo">
    <defs>
      <linearGradient :id="`cg-${size}`" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#8ab6ff"/>
        <stop offset="1" stop-color="#5b8cff"/>
      </linearGradient>
    </defs>
    <path :fill="`url(#cg-${size})`" d="M18 46a10 10 0 0 1-2.2-19.8 14 14 0 0 1 27-2.5A11.5 11.5 0 0 1 44 46H18z"/>
    <path fill="#ffffff" fill-opacity="0.35" d="M22 27a8 8 0 0 1 7.5-5.5c2.6 0 4.9 1.3 6.3 3.3a9 9 0 0 0-11.7 5.6 6 6 0 0 0-2.1-.2A7.2 7.2 0 0 1 22 27z"/>
  </svg>
</template>

<style scoped>
.dc-logo { display: inline-block; vertical-align: middle; }
</style>
