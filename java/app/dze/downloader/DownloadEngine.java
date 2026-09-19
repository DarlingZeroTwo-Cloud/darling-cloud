package app.dze.downloader;

import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.SystemClock;
import android.provider.DocumentsContract;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 下载引擎：任务队列 + aria2c（libaria2c.so，从 nativeLibraryDir 执行）。
 * 逻辑与桌面/Linux 版一致：HEAD/Range 取大小 → IDM 式分档 → dry-run 验证降档
 * → 多线程下载（流式解析摘要 + 磁盘大小兜底进度）。
 */
public class DownloadEngine {
    private static final String UA = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36";
    private static final Pattern P_FRAC = Pattern.compile(
            "(\\d+(?:\\.\\d+)?[KMG]iB)\\s*/\\s*(\\d+(?:\\.\\d+)?[KMG]iB)\\s*\\((\\d+(?:\\.\\d+)?)%\\)");
    private static final Pattern P_DL = Pattern.compile("DL:\\s*(\\d+(?:\\.\\d+)?)([KMG])iB");
    private static final Pattern P_ETA = Pattern.compile("ETA:\\s*(\\S+)");
    private static final Pattern P_ANSI = Pattern.compile("\\x1b\\[[0-9;]*[A-Za-z]");

    private final Context ctx;
    private final String aria2c;
    private final File stagingDir;   // aria2c 实际写入的真实路径（应用专属目录）
    private Uri saveTree;            // SAF 用户所选目录（可空）
    private String saveTreeName;     // 所选目录的显示名
    private final List<Map<String, Object>> tasks = new ArrayList<>();
    private final List<String[]> logs = new ArrayList<>();
    private final LinkedBlockingQueue<Map<String, Object>> queue = new LinkedBlockingQueue<>();
    private volatile Process proc;
    private volatile boolean stopFlag;
    private int seq = 0;

    public DownloadEngine(Context ctx) {
        this.ctx = ctx;
        aria2c = new File(ctx.getApplicationInfo().nativeLibraryDir, "libaria2c.so").getAbsolutePath();
        File base = ctx.getExternalFilesDir(null);
        if (base == null) base = ctx.getFilesDir();
        File dzeDir = new File(base, "下载");
        if (!dzeDir.exists()) dzeDir.mkdirs();
        stagingDir = dzeDir;
        SharedPreferences sp = ctx.getSharedPreferences("dze", Context.MODE_PRIVATE);
        applyTree(sp.getString("save_tree", null));
        log("info", new File(aria2c).exists()
                ? "✓ aria2c 已就绪（内置）"
                : "⚠ 未找到内置 aria2c，仅单线程模式可用");
        log("info", "保存目录：" + saveDirDisplay() + "（可在界面更改）");
        Thread w = new Thread(new Runnable() {
            @Override
            public void run() {
                worker();
            }
        }, "dze-worker");
        w.setDaemon(true);
        w.start();
    }

    /** 读取/应用 SAF 保存目录（MainActivity 选择后调用）。 */
    public void reloadSaveDir() {
        SharedPreferences sp = ctx.getSharedPreferences("dze", Context.MODE_PRIVATE);
        synchronized (this) {
            applyTree(sp.getString("save_tree", null));
        }
        log("ok", "保存目录已更改为：" + saveDirDisplay());
    }

    private void applyTree(String tree) {
        if (tree == null || tree.isEmpty()) {
            saveTree = null;
            saveTreeName = stagingDir.getAbsolutePath();
        } else {
            try {
                saveTree = Uri.parse(tree);
                saveTreeName = treeDisplayName(saveTree);
            } catch (Exception e) {
                saveTree = null;
                saveTreeName = stagingDir.getAbsolutePath();
            }
        }
    }

    private static String treeDisplayName(Uri tree) {
        String id = DocumentsContract.getTreeDocumentId(tree);
        if (id.contains(":")) {
            String[] parts = id.split(":", 2);
            String vol = parts[0], path = parts[1];
            if (path.isEmpty()) return vol.equals("primary") ? "内部存储根目录" : vol;
            return "/" + path;
        }
        return id;
    }

    private String saveDirDisplay() {
        return saveTree != null ? saveTreeName : stagingDir.getAbsolutePath();
    }

    // ---------- 对 JS 桥的接口 ----------
    public String addTask(String url) {
        if (url == null) url = "";
        url = url.trim();
        if (!(url.startsWith("http://") || url.startsWith("https://")))
            return "请输入 http(s):// 开头的下载链接";
        Map<String, Object> t = new LinkedHashMap<>();
        t.put("id", ++seq);
        t.put("link", url);
        t.put("name", sanitize(url.substring(url.lastIndexOf('/') + 1)));
        t.put("state", "排队");
        t.put("pct", 0.0);
        t.put("size", "—");
        t.put("speed", "—");
        t.put("eta", "—");
        t.put("note", "");
        synchronized (this) {
            tasks.add(0, t);
        }
        stopFlag = false;
        queue.add(t);
        log("info", "已加入任务：" + url);
        return "ok";
    }

    public void stopAll() {
        stopFlag = true;
        Process p = proc;
        if (p != null) p.destroy();
        Map<String, Object> t;
        while ((t = queue.poll()) != null) {
            synchronized (this) {
                t.put("state", "已取消");
            }
        }
        log("warn", "正在停止…");
    }

    public void shutdown() {
        stopAll();
        Process p = proc;
        if (p != null) p.destroy();
    }

    public String statusJson() {
        try {
            JSONObject o = new JSONObject();
            o.put("has_aria2", new File(aria2c).exists());
            o.put("save_dir", saveDirDisplay());
            JSONArray arr = new JSONArray();
            synchronized (this) {
                for (Map<String, Object> t : tasks) arr.put(new JSONObject(t));
            }
            o.put("tasks", arr);
            JSONArray lg = new JSONArray();
            synchronized (logs) {
                int from = Math.max(0, logs.size() - 60);
                for (int i = from; i < logs.size(); i++) {
                    String[] l = logs.get(i);
                    JSONObject j = new JSONObject();
                    j.put("t", l[0]);
                    j.put("tag", l[1]);
                    j.put("text", l[2]);
                    lg.put(j);
                }
            }
            o.put("logs", lg);
            return o.toString();
        } catch (Exception e) {
            return "{\"tasks\":[],\"logs\":[]}";
        }
    }

    // ---------- worker ----------
    private void worker() {
        while (true) {
            Map<String, Object> t;
            try {
                t = queue.take();
            } catch (InterruptedException e) {
                return;
            }
            if (stopFlag) {
                setTask(t, "state", "已取消");
                continue;
            }
            try {
                runTask(t);
            } catch (Exception e) {
                log("error", "任务异常终止：" + e);
                setTask(t, "state", "失败");
            }
        }
    }

    private void runTask(Map<String, Object> t) {
        String link = (String) t.get("link");
        long t0 = SystemClock.elapsedRealtime();
        setTask(t, "state", "解析", "note", "正在获取文件大小…");
        long size = resolveSize(link);
        t.put("total", size);
        setTask(t, "size", fmtSize(size));
        log("info", "文件大小：" + fmtSize(size));

        int n;
        String desc;
        if (size < 0) {
            n = 32;
            desc = "32 连接（未知大小按大文件）";
        } else if (size < 2L * 1024 * 1024) {
            n = 1;
            desc = "1 连接（< 2MB 小文件）";
        } else if (size < 10L * 1024 * 1024) {
            n = 4;
            desc = "4 连接（< 10MB）";
        } else if (size < 30L * 1024 * 1024) {
            n = 8;
            desc = "8 连接（< 30MB）";
        } else if (size < 100L * 1024 * 1024) {
            n = 16;
            desc = "16 连接（< 100MB）";
        } else {
            n = 32;
            desc = "32 连接（≥ 100MB 大文件）";
        }

        if (n > 1) {
            setTask(t, "state", "测速", "note", "验证 " + desc + "…");
            int m = validate(link, n);
            if (m < n) {
                log("warn", n + " 连接不可用，降到 " + m + " 连接");
                desc = m + " 连接（自动降档）";
            } else {
                log("ok", "测速通过：" + desc);
            }
            n = m;
        }
        setTask(t, "note", "策略：" + desc, "state", "下载");
        int code = download(t, n);

        if (stopFlag) {
            setTask(t, "state", "已取消");
            log("warn", "任务已取消：" + t.get("name"));
            return;
        }
        long used = (SystemClock.elapsedRealtime() - t0) / 1000;
        if (code == 0) {
            if (saveTree != null) {
                setTask(t, "state", "移动", "note", "正在移动到所选目录…");
                String err = moveToTree(link);
                if (err == null) {
                    log("ok", "已保存到所选目录：" + saveTreeName);
                } else {
                    log("error", "移动失败：" + err + "（文件保留在 " + stagingDir + "）");
                }
            }
            setTask(t, "state", "完成", "pct", 100.0);
            log("ok", "✅ 下载完成：" + t.get("name") + "（用时 " + fmtTime(used) + "）→ " + saveDirDisplay());
        } else {
            setTask(t, "state", "失败");
            log("error", "❌ 下载失败（退出码 " + code + "）：" + t.get("name"));
        }
    }

    /** 把暂存目录里的成品移动到用户所选的 SAF 目录。返回 null 表示成功。 */
    private String moveToTree(String link) {
        try {
            String name = sanitize(link.substring(link.lastIndexOf('/') + 1));
            android.content.ContentResolver res = ctx.getContentResolver();
            Uri treeDoc = DocumentsContract.buildDocumentUriUsingTree(saveTree,
                    DocumentsContract.getTreeDocumentId(saveTree));
            Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(saveTree,
                    DocumentsContract.getTreeDocumentId(saveTree));
            Cursor cur = res.query(children, new String[]{
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME}, null, null, null);
            if (cur != null) {
                while (cur.moveToNext()) {
                    String dn = cur.getString(1);
                    if (name.equals(dn) || (name + ".aria2").equals(dn)) {
                        try {
                            DocumentsContract.deleteDocument(res,
                                    DocumentsContract.buildDocumentUriUsingTree(saveTree, cur.getString(0)));
                        } catch (Exception ignored) {
                        }
                    }
                }
                cur.close();
            }
            Uri newDoc = DocumentsContract.createDocument(res, treeDoc,
                    "application/octet-stream", name);
            if (newDoc == null) return "目标目录创建文件失败";
            java.io.InputStream in = new java.io.FileInputStream(new File(stagingDir, name));
            java.io.OutputStream out = res.openOutputStream(newDoc);
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
            out.close();
            in.close();
            new File(stagingDir, name).delete();
            return null;
        } catch (Exception e) {
            return String.valueOf(e);
        }
    }

    // ---------- 组件 ----------
    private long resolveSize(String link) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(link).openConnection();
            c.setRequestMethod("HEAD");
            c.setConnectTimeout(10000);
            c.setReadTimeout(10000);
            c.setRequestProperty("User-Agent", UA);
            String cl = c.getHeaderField("Content-Length");
            c.disconnect();
            if (cl != null && cl.matches("\\d+")) return Long.parseLong(cl);
        } catch (Exception ignored) {
        }
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(link).openConnection();
            c.setRequestProperty("Range", "bytes=0-0");
            c.setRequestProperty("User-Agent", UA);
            c.setConnectTimeout(10000);
            c.setReadTimeout(10000);
            String cr = c.getHeaderField("Content-Range");
            c.disconnect();
            if (cr != null && cr.contains("/")) {
                String total = cr.substring(cr.lastIndexOf('/') + 1).trim();
                if (total.matches("\\d+")) return Long.parseLong(total);
            }
        } catch (Exception ignored) {
        }
        return -1;
    }

    private int validate(String link, int n) {
        while (n > 1) {
            if (probe(link, n)) return n;
            n /= 2;
        }
        return 1;
    }

    private boolean probe(String link, int n) {
        if (stopFlag) return false;
        try {
            List<String> cmd = new ArrayList<>();
            cmd.add(aria2c);
            cmd.add("-x" + n);
            cmd.add("-s" + n);
            cmd.add("-k1M");
            cmd.add("--timeout=1");
            cmd.add("--max-tries=1");
            cmd.add("--dry-run");
            cmd.add("--dir");
            cmd.add(stagingDir.getAbsolutePath());
            cmd.add("--console-log-level=error");
            cmd.add("--");
            cmd.add(link);
            Process p = new ProcessBuilder(cmd).redirectErrorStream(true).start();
            InputStream in = p.getInputStream();
            byte[] buf = new byte[4096];
            while (in.read(buf) != -1) {
            }
            in.close();
            boolean done = p.waitFor(20, TimeUnit.SECONDS);
            if (!done) {
                p.destroyForcibly();
                return false;
            }
            boolean ok = p.exitValue() == 0;
            log(ok ? "dim" : "warn", "测速探测：" + n + " 连接 " + (ok ? "✓" : "✗"));
            return ok;
        } catch (Exception e) {
            return false;
        }
    }

    private int download(Map<String, Object> t, int n) {
        try {
            List<String> cmd = new ArrayList<>();
            cmd.add(aria2c);
            cmd.add("-x" + n);
            cmd.add("-s" + n);
            cmd.add("-k1M");
            cmd.add("--timeout=8");
            cmd.add("--summary-interval=1");
            cmd.add("--dir");
            cmd.add(stagingDir.getAbsolutePath());
            cmd.add("--");
            cmd.add((String) t.get("link"));
            Process p = new ProcessBuilder(cmd).redirectErrorStream(true).start();
            proc = p;
            int code = pump(t, p);
            proc = null;
            return code;
        } catch (Exception e) {
            log("error", "aria2c 启动失败：" + e);
            return 1;
        }
    }

    private int pump(Map<String, Object> t, Process p) {
        String link = (String) t.get("link");
        File target = new File(stagingDir, sanitize(link.substring(link.lastIndexOf('/') + 1)));
        StringBuilder pending = new StringBuilder();
        InputStream in = p.getInputStream();
        byte[] buf = new byte[65536];
        long lastDisk = 0;
        long lastAny = SystemClock.elapsedRealtime();
        boolean stall = false;
        try {
            int n;
            while ((n = in.read(buf)) != -1) {
                pending.append(new String(buf, 0, n, "UTF-8"));
                int start = 0;
                for (int i = 0; i < pending.length(); i++) {
                    char c = pending.charAt(i);
                    if (c == '\n' || c == '\r') {
                        String line = pending.substring(start, i).trim();
                        start = i + 1;
                        if (!line.isEmpty() && parseLine(t, line)) {
                            lastAny = SystemClock.elapsedRealtime();
                            stall = false;
                        }
                    }
                }
                if (start > 0) pending.delete(0, start);
                long now = SystemClock.elapsedRealtime();
                if (now - lastDisk >= 500) {
                    lastDisk = now;
                    diskProbe(t, target);
                }
                if (now - lastAny > 20000 && !stall) {
                    stall = true;
                    log("warn", "⚠ 已 20 秒无下载数据，可能被限速或拒绝连接…");
                }
            }
            if (pending.toString().trim().length() > 0) parseLine(t, pending.toString().trim());
            diskProbe(t, target);
            return p.waitFor();
        } catch (Exception e) {
            log("error", "读取输出异常：" + e);
            p.destroy();
            return 1;
        }
    }

    private boolean parseLine(Map<String, Object> t, String line) {
        line = P_ANSI.matcher(line).replaceAll("");
        Matcher m = P_FRAC.matcher(line);
        if (!m.find()) {
            String low = line.toLowerCase();
            if (low.contains("errorcode=") || low.contains("aborted") || low.contains("exception")
                    || low.contains("(err") || low.contains("result: err") || low.contains("failed")) {
                log("error", line);
            }
            return false;
        }
        double pct = Double.parseDouble(m.group(3));
        setTask(t, "state", "下载", "pct", Math.min(pct, 100),
                "size", m.group(1) + " / " + m.group(2));
        Matcher dl = P_DL.matcher(line);
        if (dl.find()) {
            double bps = Double.parseDouble(dl.group(1)) * unit(dl.group(2));
            setTask(t, "speed", fmtSize(bps) + "/s");
        }
        Matcher eta = P_ETA.matcher(line);
        if (eta.find()) {
            String e = eta.group(1);
            if (e.endsWith("]")) e = e.substring(0, e.length() - 1);
            if (!e.equals("-") && !e.equals("--") && !e.equals("unknown")) setTask(t, "eta", e);
        }
        return true;
    }

    private void diskProbe(Map<String, Object> t, File target) {
        Object totalObj = t.get("total");
        if (!(totalObj instanceof Long) || ((Long) totalObj) <= 0) return;
        long total = (Long) totalObj;
        long done = target.exists() ? target.length() : 0;
        double pct = Math.min(done * 100.0 / total, 100);
        setTask(t, "state", "下载", "pct", pct,
                "size", fmtSize(done) + " / " + fmtSize(total));
        Object ltObj = t.get("_lt");
        long now = SystemClock.elapsedRealtime();
        if (ltObj instanceof Long) {
            long lt = (Long) ltObj;
            Object ldObj = t.get("_ld");
            long ld = ldObj instanceof Long ? (Long) ldObj : 0;
            if (now > lt) {
                double bps = (done - ld) * 1000.0 / (now - lt);
                if (bps > 0) {
                    setTask(t, "speed", fmtSize(bps) + "/s");
                    long remain = total - done;
                    if (remain > 0) setTask(t, "eta", fmtTime(remain / (long) bps));
                }
            }
        }
        t.put("_lt", now);
        t.put("_ld", done);
    }

    private int unit(String k) {
        switch (k.charAt(0)) {
            case 'K': return 1024;
            case 'G': return 1024 * 1024 * 1024;
            default:  return 1024 * 1024;
        }
    }

    private static String fmtSize(double n) {
        if (n >= 1073741824) return String.format("%.2f GiB", n / 1073741824);
        if (n >= 1048576) return String.format("%.2f MiB", n / 1048576);
        return String.format("%.2f KiB", n / 1024);
    }

    private static String fmtTime(long sec) {
        if (sec < 0) sec = 0;
        if (sec < 60) return sec + "s";
        if (sec < 3600) return String.format("%dm%02ds", sec / 60, sec % 60);
        return String.format("%dh%02dm", sec / 3600, sec % 3600 / 60);
    }

    private static String sanitize(String name) {
        String s = name == null ? "" : name.replaceAll("[<>:\"/\\\\|?*]", "_");
        return s.isEmpty() ? "downloaded_file" : s;
    }

    private void setTask(Map<String, Object> t, Object... kv) {
        synchronized (this) {
            for (int i = 0; i + 1 < kv.length; i += 2) t.put((String) kv[i], kv[i + 1]);
        }
    }

    private void log(String tag, String text) {
        String time = android.text.format.DateFormat.format("HH:mm:ss", new java.util.Date()).toString();
        synchronized (logs) {
            logs.add(new String[]{time, tag, text});
            if (logs.size() > 300) logs.remove(0);
        }
    }
}
