# Darling Cloud v2 部署指南（官方文档）

开源私有云盘 —— 公开资源广场（免登录）+ 私有空间 + 多用户多组 + 分享链接 + WebDAV + Aria2 离线下载 + 远程/云盘多存储。

- 版本：v0.1.0（M5）
- 许可证：木兰宽松许可证 v2
- 仓库：Gitee `darling-cloud/darling-cloud` / GitHub `DarlingZeroTwo-Cloud/darling-cloud`（v2 分支）

---

## 一、Linux（含 Arch Linux）—— 压缩包 + 单二进制一条命令

### 方式 A：发布压缩包（推荐）

```bash
# 1. 下载并解压
wget -O darling-cloud.tar.gz <Release 下载地址>   # 或浏览器下载
tar -xzf darling-cloud.tar.gz
cd darling-cloud-v0.1.0-linux-x86_64

# 2. 一条命令启动（默认端口 8080；可加端口参数 ./start.sh 9000）
./start.sh
```

启动后浏览器访问 `http://127.0.0.1:8080`：

- 公开广场无需登录即可浏览 / 下载
- **首个注册的账号自动成为管理员**（可授予/撤销管理员、清理违规内容）
- WebDAV 地址：`http://127.0.0.1:8080/dav/`（用户名 + 登录密码）

### 方式 B：直接运行单二进制

```bash
./darling-cloud start                       # 默认 0.0.0.0:8080，数据目录 ./data
./darling-cloud start --port 9000           # 改端口
./darling-cloud start --data /srv/dc-data   # 改数据目录（库/文件/临时区）
./darling-cloud version
```

### 方式 C：源码运行（开发）

```bash
git clone -b v2 https://gitee.com/darling-cloud/darling-cloud.git
cd darling-cloud
./scripts/start.sh        # 自动装依赖（华为云镜像）并启动
# 或手动：
#   cd server && python3 -m pip install -r requirements.txt -i https://mirrors.huaweicloud.com/repository/pypi/simple
#   python3 server/cli.py start
```

> Arch Linux 说明：纯 Python + 标准依赖，不依赖发行版专属包；`pacman -S python python-pip nodejs npm` 即可运行。前端已构建进单二进制，运行期不需要 Node。

---

## 二、Windows —— CMD 一条命令启动

```bat
:: 方式 A：双击 start.bat（推荐）
:: 方式 B：命令行
start.bat 9000
```

- 首次运行自动安装依赖（华为云镜像）
- 自动打开浏览器；`Ctrl+C` 停止
- 前置：安装 Python 3.10+（安装时勾选 Add to PATH）

---

## 三、环境变量

| 变量 | 说明 | 默认 |
|---|---|---|
| `DARLING_PORT` | 端口 | `8080` |
| `DARLING_HOST` | 监听地址 | `0.0.0.0` |
| `DARLING_DATA` | 数据目录（库/文件/临时） | `./data` |
| `DARLING_MAX_FILE` | 单文件上限（字节） | 10GB |
| `DARLING_SECRET` | JWT 密钥（生产必改） | dev 值 |
| `DARLING_REMOTE` | 远程挂载扩容目录（NFS/SFTP 挂载另一台机器后指向它） | 空（本地） |

远程扩容示例（把另一台机器挂到本机）：

```bash
# 另一台机器共享 /srv/nas（NFS）后：
mkdir -p /mnt/nas
mount -t nfs 192.168.1.10:/srv/nas /mnt/nas
DARLING_REMOTE=/mnt/nas ./darling-cloud start
# 管理面板将存储后端切为「远程挂载扩容」后，新文件写入扩容盘
```

---

## 四、WebDAV 挂载

| 客户端 | 用法 |
|---|---|
| Windows 文件管理器 | 地址栏输入 `http://<主机>:8080/dav/` 回车，填账号密码，右键"映射网络驱动器" |
| RaiDrive / Mountain Duck | WebDAV → 地址同上，账号=用户名，密码=登录密码 |
| rclone | `rclone config` → WebDAV → vendor=other → url=`http://<主机>:8080/dav/` |

支持：PROPFIND / MKCOL / PUT / GET / COPY / MOVE / LOCK / UNLOCK、目录递归复制、配额属性。

---

## 五、离线下载（可选）

需要服务器安装 aria2：

```bash
# Debian/Ubuntu
sudo apt-get install aria2
# Arch
sudo pacman -S aria2
# 启动 RPC（默认 6800）
aria2c --enable-rpc --rpc-listen-port=6800 --dir=/tmp/aria --daemon=true
```

网盘「离线下载」页添加 HTTP/HTTPS/磁力链接，完成后一键转存到私有空间。

---

## 六、默认数据与账号

- 默认用户组：游客（禁上传）、普通（私有 5GB / 公开 10GB）、管理员（私有 10GB / 公开 20GB）
- 首次注册账号 → 自动管理员
- 验证码默认「轻量」：图形算术题（如 `6 - 3`），不刁难

## 七、问题排查

| 现象 | 处理 |
|---|---|
| 端口被占用 | 换端口：`./start.sh 9000` / `start.bat 9000` |
| 公开广场打不开子路由 | 确认是 v2 分支（含 SPA fallback） |
| WebDAV 中文名失败 | 客户端需 UTF-8 编码路径（现代客户端默认支持） |
| 忘记管理员密码 | 停服后删除 `data/darling.db` 重建（会清空数据），或联系管理员重置 |
