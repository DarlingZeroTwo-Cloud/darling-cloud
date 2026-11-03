<script setup>
// 内置帮助页：部署命令 / 使用说明
const cmds = [
  { os: 'Linux / Arch', title: '一条命令启动（压缩包）', code: 'wget -O dc.tgz <下载链接> && tar -xzf dc.tgz && cd darling-cloud-* && ./start.sh' },
  { os: 'Linux / Arch', title: '单二进制启动', code: './darling-cloud start --port 8080' },
  { os: 'Windows CMD', title: '一键启动', code: 'start.bat   （或：start.bat 9000 指定端口）' },
  { os: '源码开发', title: '自动装依赖并启动', code: 'git clone -b v2 <仓库> && cd darling-cloud && ./scripts/start.sh' },
  { os: '远程扩容', title: '挂载另一台机器后指向扩容盘', code: 'mount -t nfs <另一台>:/srv/nas /mnt/nas && DARLING_REMOTE=/mnt/nas ./darling-cloud start' },
]
const tips = [
  ['公开广场', '无需登录即可浏览/下载；登录后可上传公开资源（须填写简介+分类）'],
  ['首个账号自动管理员', '可查看所有用户资源、授予/撤销管理员、强制清理违规内容'],
  ['WebDAV', '地址 http://<主机>:8080/dav/，账号=用户名、密码=登录密码；支持 Windows 映射/RaiDrive/rclone'],
  ['离线下载', '服务器安装 aria2 后，粘贴 HTTP/磁力链接，完成后一键转存'],
  ['验证码', '图形算术题（如 6-3），轻量不刁难'],
]
</script>

<template>
  <div>
    <div class="page-head"><h2>帮助与部署</h2></div>

    <div class="card panel">
      <h3>部署命令</h3>
      <div v-for="(c, i) in cmds" :key="i" class="cmd-block">
        <div class="cmd-title"><span class="os">{{ c.os }}</span>{{ c.title }}</div>
        <pre class="code">{{ c.code }}</pre>
      </div>
    </div>

    <div class="card panel">
      <h3>使用说明</h3>
      <div v-for="(t, i) in tips" :key="i" class="tip-row">
        <b>{{ t[0] }}</b><span>{{ t[1] }}</span>
      </div>
    </div>

    <div class="card panel">
      <h3>环境变量</h3>
      <table class="tbl">
        <tr><th>变量</th><th>说明</th><th>默认</th></tr>
        <tr><td class="mono">DARLING_PORT</td><td>端口</td><td>8080</td></tr>
        <tr><td class="mono">DARLING_HOST</td><td>监听地址</td><td>0.0.0.0</td></tr>
        <tr><td class="mono">DARLING_DATA</td><td>数据目录</td><td>./data</td></tr>
        <tr><td class="mono">DARLING_MAX_FILE</td><td>单文件上限</td><td>10GB</td></tr>
        <tr><td class="mono">DARLING_SECRET</td><td>JWT 密钥（生产必改）</td><td>dev</td></tr>
        <tr><td class="mono">DARLING_REMOTE</td><td>远程挂载扩容目录</td><td>空</td></tr>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page-head { margin-bottom: 16px; }
.page-head h2 { font-size: 18px; }
.panel { padding: 24px; margin-bottom: 14px; }
.panel h3 { font-size: 15px; margin-bottom: 14px; }
.cmd-block { margin-bottom: 16px; }
.cmd-title { font-size: 13.5px; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.os { font-size: 11px; background: var(--accent-soft); color: var(--accent); padding: 2px 8px; border-radius: 99px; }
.code {
  background: var(--bg-hover); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 14px; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 12.5px; overflow-x: auto; white-space: pre-wrap; word-break: break-all;
}
.tip-row { display: flex; gap: 12px; padding: 9px 0; border-bottom: 1px dashed var(--border); font-size: 13.5px; }
.tip-row:last-child { border-bottom: none; }
.tip-row b { flex-shrink: 0; color: var(--accent); min-width: 130px; }
.tip-row span { color: var(--text-2); }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.tbl th { color: var(--text-2); font-weight: 500; }
.mono { font-family: ui-monospace, monospace; font-size: 12.5px; }
</style>
