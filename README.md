# Darling Cloud v2

开源私有云盘 —— 全功能网盘（公开资源广场 + 私有空间 + 多用户 + 分享 + WebDAV + 离线下载 + 远程/云盘存储），底层全 Python。

> 对标 Cloud Drive / OpenList：公开资源广场免登录浏览下载、私有空间、分享链接（过期/提取码/次数）、多用户多组配额、WebDAV、Aria2 离线下载、多存储后端。

## 快速启动

```bash
# 1. 安装后端依赖（Python 3.10+）
cd server
pip install -r requirements.txt

# 2. 启动服务（默认 18081 端口，可加 --port 自定义）
python -m uvicorn main:app --port 18081

# 3. 浏览器打开
#    http://127.0.0.1:18081
```

> **注意**：第一个注册的账号自动成为**管理员**。

## 前端开发

```bash
cd web
npm install
npm run dev        # 开发模式（代理到 18081）
npm run build      # 构建到 web/dist（后端自动挂载）
```

## 冒烟测试

```bash
bash scripts/smoke.sh 18081
```

## 里程碑

| 阶段 | 内容 | 状态 |
|------|------|------|
| M1 | 用户系统（注册/登录/验证码/三组/首号管理员/管理端） | ✅ 完成 |
| M2 | 核心文件（上传/秒传/断点/下载/打包/预览/回收站） | 进行中 |
| M3 | 公开区 + 分享 + 离线下载 | 待开始 |
| M4 | 管理 + WebDAV + 多存储 | 待开始 |
| M5 | 打包发布（Windows CMD / Linux 单二进制） | 待开始 |

## 目录结构

```
server/            # Python 后端（FastAPI + SQLite）
  core/            # 配置 / 数据库 / 安全
  api/             # 路由（auth / user / files / admin）
web/               # Vue3 前端
scripts/           # 测试与部署脚本
```

## 许可

木兰宽松许可证 v2（Mulan Permissive Software License v2）
