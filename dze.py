#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DZE —— Darling Zero Two 极速下载器（Linux 版）
单文件二进制（PyInstaller --onefile），内置 aria2c（Linux 静态版）。

架构说明（适配 Linux 操作逻辑）：
  · 无 X11/GTK 依赖：启动一个本地 HTTP 服务（127.0.0.1 随机端口），
    自动尝试 xdg-open 打开浏览器；服务器/无桌面环境打印 URL 手动访问即可
  · 下载引擎与桌面版一致：HEAD/Range 取大小 → IDM 式分档连接数 →
    dry-run 验证降档 → aria2c 多线程下载（read1 流式解析 + 磁盘大小兜底）
文件保存到 ~/Downloads/DZE。
"""

import json
import os
import queue
import re
import shutil
import signal
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if getattr(sys, "frozen", False):
    RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(sys.executable)
else:
    RES_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = RES_DIR

UA = "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

UNIT_BYTE = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
RE_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
RE_FRAC = re.compile(r"(\d+(?:\.\d+)?[KMG]iB)\s*/\s*(\d+(?:\.\d+)?[KMG]iB)\s*\((\d+(?:\.\d+)?)%\)")
RE_DL = re.compile(r"DL:\s*(\d+(?:\.\d+)?)([KMG])iB")
RE_ETA = re.compile(r"ETA:\s*(\S+)")


def find_aria2c():
    for name in ("aria2c-linux", "aria2c"):
        p = os.path.join(RES_DIR, name)
        if os.path.isfile(p):
            try:
                os.chmod(p, 0o755)
            except OSError:
                pass
            return p
    return shutil.which("aria2c")


CA_PATH = os.path.join(RES_DIR, "cacert.pem")
# 逃生舱：代理/加速器做 TLS 中间人时，设 DZE_INSECURE_TLS=1 跳过证书校验
INSECURE_TLS = os.environ.get("DZE_INSECURE_TLS") == "1"


def ssl_ctx():
    if INSECURE_TLS:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if os.path.isfile(CA_PATH):
        return ssl.create_default_context(cafile=CA_PATH)
    return ssl.create_default_context()


def ca_args():
    if INSECURE_TLS:
        return ["--check-certificate=false"]
    if os.path.isfile(CA_PATH):
        return ["--ca-certificate=" + CA_PATH]
    return []


def idm_connects(size):
    MB = 1024 * 1024
    if size is None:
        return 32, "32 连接（未知大小按大文件）"
    if size < 2 * MB:
        return 1, "1 连接（< 2MB 小文件）"
    if size < 10 * MB:
        return 4, "4 连接（< 10MB）"
    if size < 30 * MB:
        return 8, "8 连接（< 30MB）"
    if size < 100 * MB:
        return 16, "16 连接（< 100MB）"
    return 32, "32 连接（≥ 100MB 大文件）"


def fmt_size(n):
    if n is None:
        return "—"
    for unit, div in (("GiB", 1024 ** 3), ("MiB", 1024 ** 2), ("KiB", 1024)):
        if n >= div or unit == "KiB":
            return f"{n / div:.2f} {unit}"


def fmt_time(sec):
    if sec is None:
        return "—"
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m{sec % 60:02d}s"
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m"


def sanitize_name(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name) or "downloaded_file"


class Engine:
    """下载引擎：任务队列 + aria2c 子进程管理，线程安全。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.tasks = []            # [{id,link,name,state,pct,size_text,speed_text,eta_text,note}]
        self.logs = []             # [{t,tag,text}] 环形
        self.task_q = queue.Queue()
        self.stop_event = threading.Event()
        self.proc = None
        self.busy = False
        self.aria2c = find_aria2c()
        home = os.path.expanduser("~") or APP_DIR
        self.save_dir = os.path.join(home, "Downloads", "DZE")
        os.makedirs(self.save_dir, exist_ok=True)
        self._seq = 0
        threading.Thread(target=self._worker_main, daemon=True).start()

    # ---- 状态快照（给 /api/status） ----
    def snapshot(self):
        with self.lock:
            return {
                "has_aria2": self.aria2c is not None,
                "save_dir": self.save_dir,
                "busy": self.busy,
                "tasks": [dict(t) for t in self.tasks],
                "logs": list(self.logs[-60:]),
            }

    def log(self, tag, text):
        with self.lock:
            self.logs.append({"t": time.strftime("%H:%M:%S"), "tag": tag, "text": text})
            del self.logs[:-300]

    def add_task(self, link):
        link = (link or "").strip()
        if not link.lower().startswith(("http://", "https://")):
            return False, "请输入 http(s):// 开头的下载链接"
        with self.lock:
            self._seq += 1
            name = sanitize_name(os.path.basename(urllib.parse.urlparse(link).path))
            task = {"id": self._seq, "link": link, "name": name, "state": "排队",
                    "pct": 0.0, "size_text": "—", "speed_text": "—", "eta_text": "—",
                    "note": ""}
            self.tasks.insert(0, task)
        self.stop_event.clear()
        self.task_q.put(task)
        self.log("info", f"已加入任务：{link}")
        return True, "ok"

    def stop(self):
        self.stop_event.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
        while True:
            try:
                t = self.task_q.get_nowait()
                t["state"] = "已取消"
            except queue.Empty:
                break
        self.log("warn", "正在停止…")

    # ---- worker ----
    def _worker_main(self):
        while True:
            task = self.task_q.get()
            if self.stop_event.is_set():
                task["state"] = "已取消"
                continue
            self.busy = True
            try:
                self._run_task(task)
            except Exception as exc:
                self.log("error", f"任务异常终止：{exc}")
                task["state"] = "失败"
            self.busy = False

    def _set(self, task, **kw):
        with self.lock:
            task.update(kw)

    def _run_task(self, task):
        link = task["link"]
        t0 = time.time()
        self._set(task, state="解析", note="正在获取文件大小…")
        size = self._resolve_size(link)
        task["total"] = size
        self._set(task, size_text=fmt_size(size))
        self.log("info", f"文件大小：{fmt_size(size)}")

        if not self.aria2c:
            self.log("warn", "未找到 aria2c，改用系统单线程下载…")
            self._set(task, note="系统单线程")
            code = self._fallback(task)
        else:
            n, desc = idm_connects(size)
            if n > 1:
                self._set(task, state="测速", note=f"验证 {desc}…")
                m = self._validate(link, n)
                if m < n:
                    self.log("warn", f"{n} 连接不可用，降到 {m} 连接")
                    desc = f"{m} 连接（自动降档）"
                else:
                    self.log("ok", f"测速通过：{desc}")
                n = m
            self._set(task, note=f"策略：{desc}", state="下载")
            code = self._aria2(task, n)

        if self.stop_event.is_set():
            self._set(task, state="已取消")
            self.log("warn", f"任务已取消:{task['name']}")
            return
        used = fmt_time(time.time() - t0)
        if code == 0:
            self._set(task, state="完成", pct=100.0)
            self.log("ok", f"✅ 下载完成：{task['name']}（用时 {used}）→ {self.save_dir}")
        else:
            self._set(task, state="失败")
            self.log("error", f"❌ 下载失败（退出码 {code}）：{task['name']}")

    # ---- 组件 ----
    def _resolve_size(self, link):
        ctx = ssl_ctx()
        try:
            req = urllib.request.Request(link, method="HEAD")
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                s = r.headers.get("Content-Length")
                if s and s.isdigit():
                    return int(s)
        except Exception:
            pass
        try:
            req = urllib.request.Request(link, headers={"Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                cr = r.headers.get("Content-Range", "")
                if "/" in cr:
                    total = cr.rsplit("/", 1)[1]
                    if total.isdigit():
                        return int(total)
        except Exception:
            pass
        return None

    def _validate(self, link, n):
        while n > 1:
            if self._probe(link, n):
                return n
            n //= 2
        return 1

    def _probe(self, link, n):
        if self.stop_event.is_set():
            return False
        cmd = [self.aria2c, f"-x{n}", f"-s{n}", "-k1M", "--timeout=1",
               "--max-tries=1", "--dry-run", "--dir", self.save_dir, UA,
               "--console-log-level=error"] + ca_args() + ["--", link]
        try:
            ret = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=15).returncode
        except subprocess.TimeoutExpired:
            ret = 28
        self.log("dim" if ret == 0 else "warn", f"测速探测：{n} 连接 {'✓' if ret == 0 else '✗'}")
        return ret == 0

    def _target_path(self, link):
        name = sanitize_name(os.path.basename(urllib.parse.urlparse(link).path))
        return os.path.join(self.save_dir, name)

    def _aria2(self, task, n):
        cmd = [self.aria2c, f"-x{n}", f"-s{n}", "-k1M", "--timeout=8",
               "--summary-interval=1", "--dir", self.save_dir, UA] + ca_args() + ["--", task["link"]]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        code = self._pump(task, self.proc)
        self.proc = None
        return code

    def _pump(self, task, proc):
        buf = b""
        last_disk = 0.0
        last_any = time.time()
        stall = False
        path = self._target_path(task["link"])
        while True:
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            buf += chunk
            start = 0
            for i, b in enumerate(buf):
                if b in (10, 13):
                    line = buf[start:i].decode("utf-8", "replace").strip("\r\n")
                    start = i + 1
                    if line.strip() and self._parse_line(task, line):
                        last_any = time.time()
                        stall = False
            buf = buf[start:]
            now = time.time()
            if now - last_disk >= 0.5:
                last_disk = now
                self._disk_probe(task, path)
            if time.time() - last_any > 20 and not stall:
                stall = True
                self.log("warn", "⚠ 已 20 秒无下载数据，可能被限速或拒绝连接…")
        if buf.strip():
            self._parse_line(task, buf.decode("utf-8", "replace").strip())
        self._disk_probe(task, path)
        return proc.wait()

    def _parse_line(self, task, line):
        line = RE_ANSI.sub("", line)
        m = RE_FRAC.search(line)
        if not m:
            low = line.lower()
            if any(k in low for k in ("errorcode=", "aborted", "exception",
                                      "(err)", "result: err", "failed")):
                self.log("error", line.strip())
            return False
        pct = float(m.group(3))
        kw = {"state": "下载", "pct": min(pct, 100),
              "size_text": f"{m.group(1)} / {m.group(2)}"}
        dl = RE_DL.search(line)
        if dl:
            bps = float(dl.group(1)) * UNIT_BYTE[dl.group(2)]
            kw["speed_text"] = f"{fmt_size(bps)}/s"
        eta = RE_ETA.search(line)
        if eta:
            e = eta.group(1).rstrip("]")
            if e not in ("-", "--", "unknown"):
                kw["eta_text"] = e
        self._set(task, **kw)
        return True

    def _disk_probe(self, task, path):
        total = task.get("total")
        if not total:
            return
        try:
            done = os.path.getsize(path) if os.path.exists(path) else 0
        except OSError:
            return
        now = time.time()
        kw = {"state": "下载", "pct": min(done * 100.0 / total, 100),
              "size_text": f"{fmt_size(done)} / {fmt_size(total)}"}
        if task.get("_lt") and now > task["_lt"]:
            bps = (done - task.get("_ld", 0)) / (now - task["_lt"])
            if bps > 0:
                kw["speed_text"] = f"{fmt_size(bps)}/s"
                remain = total - done
                if remain > 0:
                    kw["eta_text"] = fmt_time(remain / bps)
        task["_lt"], task["_ld"] = now, done
        self._set(task, **kw)

    def _fallback(self, task):
        path = self._target_path(task["link"])
        try:
            req = urllib.request.urlopen(task["link"], timeout=30, context=ssl_ctx())
        except Exception as e:
            self.log("error", f"连接失败：{e}")
            return 1
        total = int(req.headers.get("Content-Length") or 0) or None
        task["total"] = task.get("total") or total
        done = last = 0
        lt = time.time()
        try:
            with open(path, "wb") as f:
                while True:
                    if self.stop_event.is_set():
                        return -1
                    chunk = req.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - lt >= 0.3:
                        bps = (done - last) / (now - lt)
                        last, lt = done, now
                        kw = {"state": "下载", "speed_text": f"{fmt_size(bps)}/s"}
                        if total:
                            kw["pct"] = min(done * 100.0 / total, 100)
                            kw["size_text"] = f"{fmt_size(done)} / {fmt_size(total)}"
                            kw["eta_text"] = fmt_time((total - done) / bps)
                        self._set(task, **kw)
            return 0
        except Exception as e:
            self.log("error", f"下载失败：{e}")
            return 1


PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DZE 极速下载器</title>
<style>
  :root { --deep:#0b1220; --bg:#eef2f7; --card:#fff; --blue:#0a84e8; --green:#22c55e;
          --orange:#f59e0b; --red:#ef4444; --slate:#64748b; --text:#1e293b; }
  * { box-sizing:border-box; margin:0; }
  body { font-family:system-ui,"Noto Sans CJK SC","Microsoft YaHei",sans-serif;
         background:var(--bg); color:var(--text); }
  header { background:var(--deep); color:#fff; padding:14px 18px; display:flex;
           align-items:center; gap:12px; }
  header img { width:40px; height:40px; border-radius:8px; }
  header h1 { font-size:18px; } header p { font-size:12px; color:#9fb3c8; }
  main { max-width:860px; margin:0 auto; padding:16px; }
  .row { display:flex; gap:8px; }
  input[type=text] { flex:1; padding:12px; font-size:15px; border:1px solid #cbd5e1;
                     border-radius:8px; }
  button { border:0; border-radius:8px; padding:12px 20px; font-size:15px;
           cursor:pointer; font-weight:600; }
  .primary { background:var(--blue); color:#fff; }
  .ghost { background:#e2e8f0; color:var(--text); }
  .card { background:var(--card); border:1px solid #e2e8f0; border-radius:12px;
          padding:14px; margin-top:14px; }
  .badge { display:inline-block; padding:2px 10px; border-radius:99px; font-size:12px;
           font-weight:700; color:#fff; background:var(--slate); }
  .bar { height:14px; background:#e2e8f0; border-radius:99px; overflow:hidden;
         margin:10px 0; }
  .bar i { display:block; height:100%; width:0; background:var(--blue);
           border-radius:99px; transition:width .4s; }
  .meta { display:flex; justify-content:space-between; color:var(--slate);
          font-size:14px; flex-wrap:wrap; gap:6px; }
  .pct { color:var(--blue); font-size:22px; font-weight:800; }
  table { width:100%; border-collapse:collapse; font-size:14px; margin-top:8px; }
  th,td { text-align:left; padding:6px 8px; border-bottom:1px solid #eef2f7; }
  th { color:var(--slate); font-weight:600; }
  #log { background:#0b1220; color:#cbd5e1; font:12px/1.5 Consolas,monospace;
         border-radius:10px; padding:10px; height:150px; overflow-y:auto;
         white-space:pre-wrap; margin-top:14px; }
  .ok{color:#4ade80} .warn{color:#fbbf24} .error{color:#f87171} .info{color:#7dd3fc} .dim{color:#64748b}
</style></head>
<body>
<header>
  <img src="/icon.png" alt="">
  <div><h1>DZE 极速下载器</h1><p>IDM 式分档测速 · aria2c 全速下载 · Linux</p></div>
  <span id="aria" class="badge" style="margin-left:auto"></span>
</header>
<main>
  <div class="row">
    <input id="url" type="text" placeholder="粘贴 http(s):// 下载链接" />
    <button class="ghost" onclick="pasteClip()">粘贴</button>
    <button class="primary" onclick="start()">立即下载</button>
    <button class="ghost" onclick="stop()">停止</button>
  </div>
  <div class="card" id="card">
    <b id="name">暂无任务</b> <span id="state" class="badge">就绪</span>
    <div class="bar"><i id="fill"></i></div>
    <div class="meta">
      <span id="size">大小：—</span>
      <span id="speed" style="color:var(--blue);font-weight:700">速度：—</span>
      <span id="note"></span>
      <span>剩余：<span id="eta">—</span></span>
      <span class="pct" id="pct"></span>
    </div>
  </div>
  <div class="card">
    <b>任务列表</b>
    <table><thead><tr><th>#</th><th>文件名</th><th>大小</th><th>状态</th></tr></thead>
    <tbody id="rows"></tbody></table>
  </div>
  <div id="log"></div>
  <p style="color:var(--slate);font-size:12px;margin-top:10px" id="savedir"></p>
</main>
<script>
const st2c = {"下载":"var(--blue)","完成":"var(--green)","失败":"var(--red)",
              "测速":"var(--orange)","解析":"var(--orange)","排队":"var(--slate)","已取消":"#94a3b8"};
async function refresh(){
  const s = await (await fetch("/api/status")).json();
  document.getElementById("aria").textContent = s.has_aria2 ? "● aria2c 已就绪" : "● 无 aria2c（单线程）";
  document.getElementById("aria").style.background = s.has_aria2 ? "var(--green)" : "var(--orange)";
  document.getElementById("savedir").textContent = "保存目录：" + s.save_dir;
  const t = s.tasks[0];
  if (t) {
    document.getElementById("name").textContent = t.name;
    const st = document.getElementById("state");
    st.textContent = t.state; st.style.background = st2c[t.state] || "var(--slate)";
    const pct = t.state === "完成" ? 100 : t.pct;
    document.getElementById("fill").style.width = pct + "%";
    document.getElementById("pct").textContent = pct.toFixed(1) + "%";
    document.getElementById("size").textContent = "大小：" + t.size_text;
    document.getElementById("speed").textContent = "速度：" + t.speed_text;
    document.getElementById("eta").textContent = t.eta_text;
    document.getElementById("note").textContent = t.note || "";
  }
  document.getElementById("rows").innerHTML = s.tasks.map(t =>
    `<tr><td>${t.id}</td><td>${t.name}</td><td>${t.size_text}</td>
     <td style="color:${st2c[t.state]||'inherit'}">${t.state}</td></tr>`).join("");
  document.getElementById("log").innerHTML = s.logs.map(l =>
    `<div class="${l.tag}">[${l.t}] ${l.text}</div>`).join("");
  const lb = document.getElementById("log"); lb.scrollTop = lb.scrollHeight;
}
async function start(){
  const url = document.getElementById("url").value.trim();
  const r = await (await fetch("/api/start", {method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify({url})})).json();
  if (!r.ok) alert(r.msg);
}
async function pasteClip(){
  try { document.getElementById("url").value = await navigator.clipboard.readText(); } catch(e) { alert("请手动粘贴（浏览器剪贴板权限受限）"); }
}
async function stop(){ await fetch("/api/stop", {method:"POST"}); }
document.getElementById("url").addEventListener("keydown", e => { if (e.key === "Enter") start(); });
setInterval(refresh, 1000); refresh();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    engine = None  # type: Engine

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif self.path == "/api/status":
            body = json.dumps(self.engine.snapshot(), ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif self.path == "/icon.png":
            p = os.path.join(RES_DIR, "icon.png")
            if os.path.isfile(p):
                self._send(200, "image/png", open(p, "rb").read())
            else:
                self._send(404, "text/plain", b"no icon")
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if self.path == "/api/start":
            try:
                url = json.loads(raw.decode("utf-8")).get("url", "")
            except Exception:
                url = ""
            ok, msg = self.engine.add_task(url)
            body = json.dumps({"ok": ok, "msg": msg}, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif self.path == "/api/stop":
            self.engine.stop()
            self._send(200, "application/json", b'{"ok":true}')
        else:
            self._send(404, "text/plain", b"not found")

    def log_message(self, *a):
        pass


def main():
    engine = Engine()
    Handler.engine = engine

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}"

    print("=" * 52, flush=True)
    print("  DZE —— Darling Zero Two 极速下载器 (Linux)", flush=True)
    print(f"  aria2c : {'已就绪 ' + engine.aria2c if engine.aria2c else '未找到（单线程模式）'}", flush=True)
    print(f"  保存到 : {engine.save_dir}", flush=True)
    print(f"  界面   : {url}", flush=True)
    print("=" * 52, flush=True)

    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass

    def bye(*a):
        if engine.proc:
            try:
                engine.proc.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, bye)
    signal.signal(signal.SIGTERM, bye)
    srv.serve_forever()


if __name__ == "__main__":
    main()