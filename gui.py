#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Darling Zero Two 极速下载器 —— 迅雷风格 GUI
纯 Python 标准库（tkinter），无第三方依赖；支持 PyInstaller 打包。

特性：
  · 迅雷风格界面：深蓝顶栏 / 任务卡大进度条 / 任务列表 / 底部状态栏
  · 进度条可靠：aria2c 摘要解析 + 磁盘文件大小双保险，任何情况都动
  · 无黑色弹窗：所有 aria2c 子进程带 CREATE_NO_WINDOW
  · IDM 式测速：按文件大小分档连接数（1/4/8/16/32），只做少量探测验证，
    失败自动降档，不再 1~256 暴力扫描
  · 保存目录可自选（默认 exe 旁「下载」文件夹）
"""

import ctypes
import os
import re
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------- 运行环境 ----------
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = APP_DIR

DEFAULT_DOWNLOAD_DIR = os.path.join(APP_DIR, "下载")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
ICON_PATH = os.path.join(RES_DIR, "icon.ico")

# ---------- 主题色（迅雷风） ----------
COLOR_DEEP   = "#0b1220"
COLOR_BG     = "#eef2f7"
COLOR_CARD   = "#ffffff"
COLOR_BLUE   = "#0a84e8"
COLOR_BLUE_D = "#086fbf"
COLOR_GREEN  = "#22c55e"
COLOR_ORANGE = "#f59e0b"
COLOR_RED    = "#ef4444"
COLOR_GRAY   = "#94a3b8"
COLOR_SLATE  = "#64748b"
COLOR_TEXT   = "#1e293b"

UNIT_BYTE = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
UA = "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


# aria2c 摘要行（非 TTY 模式）解析
RE_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
RE_FRAC = re.compile(r"(\d+(?:\.\d+)?[KMG]iB)\s*/\s*(\d+(?:\.\d+)?[KMG]iB)\s*\((\d+(?:\.\d+)?)%\)")
RE_DL = re.compile(r"DL:\s*(\d+(?:\.\d+)?)([KMG])iB")
RE_ETA = re.compile(r"ETA:\s*(\S+)")


def _find_aria2c():
    """优先内置资源 / 脚本目录，其次搜系统 PATH。"""
    for c in (os.path.join(RES_DIR, "aria2c.exe"), os.path.join(APP_DIR, "aria2c.exe")):
        if os.path.isfile(c):
            return c
    return shutil.which("aria2c")


def idm_connects(size):
    """IDM 式分档：按文件大小决定连接数。未知大小按最大档再验证降档。"""
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


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Darling Zero Two 极速下载器")
        self.geometry("880x700")
        self.minsize(800, 620)
        self.configure(bg=COLOR_BG)

        self.q = queue.Queue()
        self.task_q = queue.Queue()
        self.stop_event = threading.Event()
        self.proc = None
        self.busy = False
        self.aria2c = _find_aria2c()
        self.has_aria2 = self.aria2c is not None
        self.save_dir = DEFAULT_DOWNLOAD_DIR
        os.makedirs(self.save_dir, exist_ok=True)
        self._task_seq = 0
        self._cur = None

        self._build_ui()
        if os.path.isfile(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except Exception:
                pass
        self.after(60, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.has_aria2:
            self.aria_badge.config(text="● aria2c 已就绪", fg=COLOR_GREEN)
            self._log("ok", f"✓ 检测到 aria2c：{self.aria2c}")
        else:
            self.aria_badge.config(text="● 未检测到 aria2c（单线程）", fg=COLOR_ORANGE)
            self._log("warn", "⚠ 未检测到 aria2c，将使用系统单线程下载（速度较慢）")

    # ---------- 界面 ----------
    def _build_ui(self):
        F = ("Microsoft YaHei UI", 10)
        FB = ("Microsoft YaHei UI", 10, "bold")
        F9 = ("Microsoft YaHei UI", 9)

        # 顶部深蓝标题栏
        header = tk.Frame(self, bg=COLOR_DEEP, height=62)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Darling Zero Two 极速下载器", bg=COLOR_DEEP,
                 fg="white", font=("Microsoft YaHei UI", 15, "bold")).pack(side="left", padx=16, pady=(10, 0))
        tk.Label(header, text="IDM 式分档测速 · 全速下载", bg=COLOR_DEEP,
                 fg="#9fb3c8", font=F9).pack(side="left", padx=(10, 0), pady=(15, 0))
        self.aria_badge = tk.Label(header, text="aria2c 检测中…", bg=COLOR_DEEP,
                                   fg="white", font=("Microsoft YaHei UI", 9, "bold"))
        self.aria_badge.pack(side="right", padx=16, pady=(13, 0))

        body = tk.Frame(self, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=12, pady=(10, 0))

        # 链接 + 按钮
        row1 = tk.Frame(body, bg=COLOR_BG)
        row1.pack(fill="x")
        row1.columnconfigure(0, weight=1)
        self.link_var = tk.StringVar()
        entry = tk.Entry(row1, textvariable=self.link_var, font=F, relief="solid",
                         borderwidth=1, highlightthickness=1, highlightbackground="#cbd5e1")
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda e: self._start())
        self.start_btn = tk.Button(row1, text="立即下载", command=self._start, font=FB,
                                   bg=COLOR_BLUE, fg="white", activebackground=COLOR_BLUE_D,
                                   activeforeground="white", relief="flat", padx=22, pady=5)
        self.start_btn.grid(row=0, column=1, padx=(8, 0))
        self.stop_btn = tk.Button(row1, text="停止", command=self._stop, font=F,
                                  state=tk.DISABLED, relief="flat", padx=18, pady=5)
        self.stop_btn.grid(row=0, column=2, padx=(8, 0))

        # 保存目录
        row2 = tk.Frame(body, bg=COLOR_BG)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="保存到：", bg=COLOR_BG, font=F, fg=COLOR_SLATE).pack(side="left")
        self.dir_var = tk.StringVar(value=self.save_dir)
        d_entry = tk.Entry(row2, textvariable=self.dir_var, font=F, relief="solid",
                           borderwidth=1, state="readonly", readonlybackground="white")
        d_entry.pack(side="left", fill="x", expand=True)
        tk.Button(row2, text="浏览…", command=self._choose_dir, font=F,
                  relief="flat", padx=14).pack(side="left", padx=(8, 0))

        # 当前任务卡
        card = tk.Frame(body, bg=COLOR_CARD, highlightbackground="#e2e8f0", highlightthickness=1)
        card.pack(fill="x", pady=(12, 8))
        self.fname_lbl = tk.Label(card, text="暂无任务", bg=COLOR_CARD, fg=COLOR_TEXT, font=FB,
                                  anchor="w")
        self.fname_lbl.pack(fill="x", padx=14, pady=(10, 2))
        self.fstate_badge = tk.Label(card, text="就绪", bg="#eef2f7", fg=COLOR_SLATE,
                                     font=("Microsoft YaHei UI", 9, "bold"), padx=10, pady=1)
        self.fstate_badge.pack(anchor="w", padx=14)

        # 原生 ttk 进度条（clam 主题下可自定义蓝色）
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Darling.Horizontal.TProgressbar",
                        troughcolor="#e2e8f0", background=COLOR_BLUE,
                        bordercolor="#e2e8f0", lightcolor=COLOR_BLUE,
                        darkcolor=COLOR_BLUE, thickness=18)
        self.bar = ttk.Progressbar(card, style="Darling.Horizontal.TProgressbar",
                                   maximum=100, value=0)
        self.bar.pack(fill="x", padx=14, pady=(10, 4))

        meta = tk.Frame(card, bg=COLOR_CARD)
        meta.pack(fill="x", padx=14, pady=(0, 2))
        self.fsize_lbl = tk.Label(meta, text="大小：—", bg=COLOR_CARD, fg=COLOR_SLATE, font=F)
        self.fsize_lbl.pack(side="left")
        self.fspeed_lbl = tk.Label(meta, text="速度：—", bg=COLOR_CARD, fg=COLOR_BLUE, font=FB)
        self.fspeed_lbl.pack(side="left", padx=(16, 0))
        self.feta_lbl = tk.Label(meta, text="剩余：—", bg=COLOR_CARD, fg=COLOR_SLATE, font=F)
        self.feta_lbl.pack(side="right")
        self.fpct_lbl = tk.Label(meta, text="", bg=COLOR_CARD, fg=COLOR_BLUE,
                                 font=("Microsoft YaHei UI", 12, "bold"))
        self.fpct_lbl.pack(side="right", padx=(16, 0))
        self.fnote_lbl = tk.Label(card, text="", bg=COLOR_CARD, fg=COLOR_SLATE, font=F9)
        self.fnote_lbl.pack(anchor="w", padx=14, pady=(0, 10))

        # 任务列表
        list_hdr = tk.Frame(body, bg=COLOR_BG)
        list_hdr.pack(fill="x")
        tk.Label(list_hdr, text="任务列表", bg=COLOR_BG, font=FB, fg=COLOR_TEXT).pack(side="left")
        tk.Button(list_hdr, text="清空列表", command=self._clear_rows, font=F9,
                  relief="flat").pack(side="right")
        self.tree = ttk.Treeview(body, columns=("id", "name", "size", "state", "used"),
                                 show="headings", height=4)
        for cid, txt, w in (("id", "#", 40), ("name", "文件名", 320), ("size", "大小", 130),
                            ("state", "状态", 90), ("used", "用时", 90)):
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, anchor="e" if cid in ("size", "used") else "w",
                             stretch=(cid == "name"))
        self.tree.pack(fill="x", pady=(4, 0))

        # 事件日志
        self.log_txt = scrolledtext.ScrolledText(body, height=6, wrap="word", state=tk.DISABLED,
                                                 font=("Consolas", 9), relief="solid", borderwidth=1)
        self.log_txt.pack(fill="both", expand=True, pady=(8, 0))
        for tag, color in (("info", "#0a66c2"), ("warn", "#b45309"), ("error", "#dc2626"),
                           ("ok", "#15803d"), ("dim", "#6b7280")):
            self.log_txt.tag_config(tag, foreground=color)

        # 底部状态栏
        statusbar = tk.Frame(self, bg=COLOR_DEEP, height=32)
        statusbar.pack(fill="x", side="bottom")
        statusbar.pack_propagate(False)
        self.status_dir_lbl = tk.Label(statusbar, text=f"保存目录：{self.save_dir}",
                                       bg=COLOR_DEEP, fg="#cbd5e1", font=F9)
        self.status_dir_lbl.pack(side="left", padx=12, pady=6)
        self.status_speed_lbl = tk.Label(statusbar, text="速度 0 B/s", bg=COLOR_DEEP, fg="#cbd5e1",
                                         font=F9)
        self.status_speed_lbl.pack(side="right", padx=12, pady=6)

    # ---------- 消息（worker → 主线程） ----------
    def _post(self, msg):
        self.q.put(msg)

    def _log(self, tag, text):
        self.q.put(("log", tag, text))

    def _poll(self):
        try:
            while True:
                self._handle(self.q.get_nowait())
        except queue.Empty:
            pass
        except tk.TclError:
            return
        except Exception as e:
            try:
                self._write_log("error", f"界面事件异常：{e}")
            except Exception:
                pass
        self.after(60, self._poll)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "log":
            self._write_log(msg[1], msg[2])
        elif kind == "sync":
            self._handle_sync(msg[1])
        elif kind == "busy":
            self._handle_busy(msg[1])

    def _write_log(self, tag, text):
        self.log_txt.config(state=tk.NORMAL)
        self.log_txt.insert(tk.END, text + "\n", tag)
        self.log_txt.see(tk.END)
        self.log_txt.config(state=tk.DISABLED)

    def _handle_sync(self, task):
        self._cur = task
        self.fname_lbl.config(text=task["name"])
        self.fsize_lbl.config(text=task["size_text"])
        self.fspeed_lbl.config(text=task["speed_text"])
        self.feta_lbl.config(text=task["eta_text"])
        self.fnote_lbl.config(text=task["note"])
        self.fstate_badge.config(text=task["state"], bg=task["state_color"], fg="white")
        pct = 100.0 if task["state"] == "完成" else task["pct"]
        if task["total"]:
            self.fpct_lbl.config(text=f"{pct:.1f}%")
        else:
            self.fpct_lbl.config(text="—" if task["state"] in ("完成", "失败", "已取消") else "计算中…")
        if task["indet"]:
            if str(self.bar["mode"]) != "indeterminate":
                self.bar.stop()
                self.bar.config(mode="indeterminate")
                self.bar.start(30)
        else:
            if str(self.bar["mode"]) != "determinate":
                self.bar.stop()
                self.bar.config(mode="determinate")
            self.bar.config(value=pct)
        used = ""
        if task.get("t1") and task.get("t0"):
            used = fmt_time(task["t1"] - task["t0"])
        try:
            self.tree.set(task["row"], "size", task["size_text"].replace("大小：", ""))
            self.tree.set(task["row"], "state", task["state"])
            self.tree.set(task["row"], "used", used)
        except tk.TclError:
            pass
        self.status_speed_lbl.config(text=task["speed_text"])

    def _handle_busy(self, busy):
        self.busy = busy
        if not busy:
            self.stop_btn.config(state=tk.DISABLED)
            self.bar.stop()
            self.bar.config(mode="determinate", value=0)

    # ---------- 按钮动作 ----------
    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_dir, title="选择保存目录", parent=self)
        if d:
            self.save_dir = d
            os.makedirs(d, exist_ok=True)
            self.dir_var.set(d)
            self.status_dir_lbl.config(text=f"保存目录：{d}")

    def _start(self):
        link = self.link_var.get().strip()
        if not link.lower().startswith(("http://", "https://")):
            messagebox.showwarning("提示", "请粘贴以 http:// 或 https:// 开头的下载链接", parent=self)
            return
        os.makedirs(self.save_dir, exist_ok=True)
        self._task_seq += 1
        name = sanitize_name(os.path.basename(urllib.parse.urlparse(link).path))
        iid = self.tree.insert("", "end", values=(self._task_seq, name, "—", "排队", ""))
        task = {"tid": self._task_seq, "link": link, "row": iid, "name": name,
                "size": None, "size_text": "大小：—", "pct": 0.0, "speed_text": "速度：—",
                "eta_text": "剩余：—", "state": "排队", "state_color": COLOR_SLATE,
                "note": "", "indet": False, "total": None, "speed_bps": 0.0,
                "_last_done": 0.0, "_last_t": 0.0, "t0": None, "t1": None}
        self.task_q.put(task)
        self.stop_event.clear()
        self.stop_btn.config(state=tk.NORMAL)
        self._log("info", f"已加入任务：{link}")
        if not self.busy:
            self.busy = True
            threading.Thread(target=self._worker_main, daemon=True).start()

    def _stop(self):
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
                t["state_color"] = COLOR_GRAY
                self._post(("sync", t))
            except queue.Empty:
                break
        if not self.busy:
            self.stop_btn.config(state=tk.DISABLED)
        self._log("warn", "正在停止…")

    def _clear_rows(self):
        self.tree.delete(*self.tree.get_children())

    def _on_close(self):
        if self.busy and not messagebox.askyesno("退出", "任务正在进行，确定要退出吗？", parent=self):
            return
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.destroy()

    # ---------- 下载流程 ----------
    def _worker_main(self):
        while True:
            try:
                task = self.task_q.get_nowait()
            except queue.Empty:
                break
            if self.stop_event.is_set():
                task["state"] = "已取消"
                task["state_color"] = COLOR_GRAY
                self._post(("sync", task))
                continue
            try:
                self._run_task(task)
            except Exception as exc:
                self._log("error", f"任务异常终止：{exc}")
                task["state"] = "失败"
                task["state_color"] = COLOR_RED
                task["t1"] = time.time()
                task["indet"] = False
                self._post(("sync", task))
        self._post(("busy", False))

    def _run_task(self, task):
        link = task["link"]
        task["t0"] = time.time()
        self._set_state(task, "解析", COLOR_ORANGE, "正在获取文件大小…")
        size = self._resolve_size(link)
        task["total"] = size
        task["size_text"] = f"大小：{fmt_size(size)}"
        self._post(("sync", task))

        if not self.has_aria2:
            self._log("warn", "aria2c 不可用，改用系统单线程下载…")
            task["note"] = "系统单线程（无 aria2c）"
            code = self._fallback_download(task)
        else:
            connects, desc = idm_connects(size)
            if connects > 1:
                self._set_state(task, "测速", COLOR_ORANGE, f"验证 {desc}…")
                n = self._validate_connects(link, connects)
                if n < connects:
                    desc = f"{n} 连接（自动降档）"
                    self._log("warn", f"{connects} 连接不可用，降到 {n} 连接")
                else:
                    self._log("ok", f"测速通过：{desc}")
                connects = n
            task["note"] = f"策略：{desc}"
            self._set_state(task, "下载", COLOR_BLUE)
            code = self._aria2_download(task, connects)

        if self.stop_event.is_set():
            self._finish_task(task, "已取消", COLOR_GRAY, code=-1)
            return
        if code == 0:
            self._finish_task(task, "完成", COLOR_GREEN)
        else:
            self._finish_task(task, "失败", COLOR_RED, code=code)

    def _set_state(self, task, state, color, note=""):
        task["state"] = state
        task["state_color"] = color
        if note:
            task["note"] = note
        self._post(("sync", task))

    def _finish_task(self, task, state, color, code=0):
        task["state"] = state
        task["state_color"] = color
        task["t1"] = time.time()
        task["indet"] = False
        self._post(("sync", task))
        used = fmt_time(task["t1"] - task["t0"]) if task["t0"] else ""
        if state == "完成":
            self._log("ok", f"✅ 下载完成：{task['name']}（用时 {used}）→ {self.save_dir}")
        elif state == "失败":
            self._log("error", f"❌ 下载失败（退出码 {code}）：{task['name']}")
        else:
            self._log("warn", f"任务已取消：{task['name']}")

    def _resolve_size(self, link):
        """HEAD 取大小，不支持再试 Range: bytes=0-0。"""
        try:
            req = urllib.request.Request(link, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as r:
                size = r.headers.get("Content-Length")
                if size and size.isdigit():
                    return int(size)
        except Exception:
            pass
        try:
            req = urllib.request.Request(link, headers={"Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                cr = r.headers.get("Content-Range", "")
                if "/" in cr:
                    total = cr.rsplit("/", 1)[1]
                    if total.isdigit():
                        return int(total)
                size = r.headers.get("Content-Length")
                if size and size.isdigit():
                    return int(size)
        except Exception:
            pass
        return None

    def _validate_connects(self, link, n):
        """推荐档 dry-run 验证一次，失败逐级减半，最多降到 1。"""
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
               "--console-log-level=error", "--", link]
        try:
            ret = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 timeout=15, creationflags=CREATE_NO_WINDOW).returncode
        except subprocess.TimeoutExpired:
            ret = 28
        self._log("dim" if ret == 0 else "warn", f"测速探测：{n} 连接 {'✓' if ret == 0 else '✗'}")
        return ret == 0

    def _aria2_download(self, task, n):
        os.makedirs(self.save_dir, exist_ok=True)
        cmd = [self.aria2c, f"-x{n}", f"-s{n}", "-k1M", "--timeout=8",
               "--summary-interval=1", "--dir", self.save_dir, UA, "--", task["link"]]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     creationflags=CREATE_NO_WINDOW)
        code = self._pump(task, self.proc)
        self.proc = None
        return code

    def _pump(self, task, proc):
        """读 aria2c 输出（摘要解析 + 错误日志），磁盘大小兜底进度。"""
        buf = b""
        last_disk = 0.0
        last_any = time.time()
        stall_warned = False
        path = self._target_path(task["link"])
        while True:
            # read1：管道里有多少就返回多少；read(n) 会阻塞攒满 n 字节导致进度全程冻结
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            buf += chunk
            start = 0
            for i, b in enumerate(buf):
                if b in (10, 13):
                    line = buf[start:i].decode("utf-8", "replace").strip("\r\n")
                    start = i + 1
                    if line.strip():
                        if self._parse_aria_line(task, line):
                            last_any = time.time()
                            stall_warned = False
            buf = buf[start:]
            now = time.time()
            if now - last_disk >= 0.5:
                last_disk = now
                self._disk_probe(task, path)
            if time.time() - last_any > 20 and not stall_warned:
                stall_warned = True
                self._log("warn", "⚠ 已 20 秒无任何下载数据，可能被服务器限速或拒绝连接，继续等待…")
        if buf.strip():
            self._parse_aria_line(task, buf.decode("utf-8", "replace").strip())
        self._disk_probe(task, path)
        return proc.wait()

    def _target_path(self, link):
        name = sanitize_name(os.path.basename(urllib.parse.urlparse(link).path))
        return os.path.join(self.save_dir, name)

    def _parse_aria_line(self, task, line):
        """返回 True 表示该行含进度数据；否则把该行写进日志（错误行标红）。"""
        line = RE_ANSI.sub("", line)
        m = RE_FRAC.search(line)
        if not m:
            low = line.lower()
            if any(k in low for k in ("errorcode=", "aborted", "exception", "(err)",
                                      "result: err", "failed", "下载失败", "错误")):
                self._log("error", line.strip())
            elif "download results" in low or ("|" in line and line.split("|")[0].strip().isdigit()):
                self._log("dim", line.strip())
            return False
        pct = float(m.group(3))
        task["pct"] = min(pct, 100)
        task["size_text"] = f"大小：{m.group(1)} / {m.group(2)}"
        dl = RE_DL.search(line)
        if dl:
            bps = float(dl.group(1)) * UNIT_BYTE[dl.group(2)]
            task["speed_bps"] = bps
            task["speed_text"] = f"速度：{fmt_size(bps)}/s"
        eta = RE_ETA.search(line)
        if eta:
            eta = eta.group(1).rstrip("]")
            if eta not in ("-", "--", "unknown"):
                task["eta_text"] = f"剩余：{eta}"
        task["state"] = "下载"
        task["state_color"] = COLOR_BLUE
        task["indet"] = False
        self._post(("sync", task))
        return True

    def _disk_probe(self, task, path):
        """兜底进度：按磁盘上目标文件实际大小算百分比和速度。"""
        if not task["total"]:
            task["indet"] = True
            self._post(("sync", task))
            return
        try:
            done = os.path.getsize(path) if os.path.exists(path) else 0
        except OSError:
            return
        now = time.time()
        bps = 0.0
        if task["_last_t"] and now > task["_last_t"]:
            bps = (done - task["_last_done"]) / (now - task["_last_t"])
        task["_last_done"], task["_last_t"] = done, now
        total = task["total"]
        task["pct"] = min(done * 100.0 / total, 100) if total else 0
        if bps > 0:
            task["speed_bps"] = bps
            task["speed_text"] = f"速度：{fmt_size(bps)}/s"
            remain = total - done
            if remain > 0:
                task["eta_text"] = f"剩余：{fmt_time(remain / bps)}"
        task["size_text"] = f"大小：{fmt_size(done)} / {fmt_size(total)}"
        task["state"] = "下载"
        task["state_color"] = COLOR_BLUE
        task["indet"] = False
        self._post(("sync", task))

    def _fallback_download(self, task):
        link = task["link"]
        path = self._target_path(link)
        os.makedirs(self.save_dir, exist_ok=True)
        try:
            req = urllib.request.urlopen(link, timeout=30)
        except Exception as e:
            self._log("error", f"连接失败：{e}")
            return 1
        total = int(req.headers.get("Content-Length") or 0) or None
        task["total"] = task["total"] or total
        done = last_done = 0
        last_t = time.time()
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
                    if now - last_t >= 0.3:
                        bps = (done - last_done) / (now - last_t)
                        last_done, last_t = done, now
                        task["speed_bps"] = bps
                        task["speed_text"] = f"速度：{fmt_size(bps)}/s"
                        task["state"] = "下载"
                        task["state_color"] = COLOR_BLUE
                        if total:
                            task["pct"] = min(done * 100.0 / total, 100)
                            task["size_text"] = f"大小：{fmt_size(done)} / {fmt_size(total)}"
                            task["eta_text"] = f"剩余：{fmt_time((total - done) / bps)}"
                            task["indet"] = False
                        else:
                            task["indet"] = True
                            task["size_text"] = f"已下载：{fmt_size(done)}"
                        self._post(("sync", task))
            if total:
                task["pct"] = 100.0
                self._post(("sync", task))
            return 0
        except Exception as e:
            self._log("error", f"下载失败：{e}")
            return 1


if __name__ == "__main__":
    DownloaderApp().mainloop()