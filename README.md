# 知流

知流是一个由Hermes Agent驱动的个人信息监测与智能简报系统。它通过移动端优先的Web界面管理关注主题，将Hermes生成的热点、论文和招聘情报保存为可筛选、可收藏的历史记录。

## 功能

- 今日情报概览和优先级排序
- 按热点、论文、招聘分类浏览
- 已读、收藏和忽略状态
- 订阅规则、Cron周期和Hermes提示词管理
- 手动触发与后台定时执行
- 日报、周报和任务失败记录
- 未配置Hermes时的完整演示模式

## 本地运行

后端：

```powershell
cd backend
uv sync --dev
$env:DEMO_MODE="true"
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

访问`http://127.0.0.1:5173`，演示账号为`admin / demo-password`。

## 配置Hermes

在Hermes所在服务器的`~/.hermes/.env`中开启API Server：

```dotenv
API_SERVER_ENABLED=true
API_SERVER_KEY=使用独立的高强度随机密钥
```

重启并检查Hermes：

```bash
hermes gateway restart
curl http://127.0.0.1:8642/health
```

Hermes必须只监听`127.0.0.1:8642`，不要把8642端口开放到公网。知流后端在Linux VPS上使用宿主机网络，因此可以安全访问这个本地端口。

## VPS部署

```bash
sudo mkdir -p /opt/zhiliu
sudo chown "$USER":"$USER" /opt/zhiliu
cd /opt/zhiliu
# 将仓库同步到此目录
cp .env.example .env
```

生成JWT密钥：

```bash
openssl rand -hex 32
```

编辑`.env`，至少替换`JWT_SECRET`、`ADMIN_PASSWORD`和`HERMES_API_KEY`，然后启动：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

默认在宿主机`8080`端口提供服务。建议使用宿主机现有Nginx或Caddy将域名HTTPS流量反向代理到`http://127.0.0.1:8080`，防火墙不对公网放行8080。

## 数据备份

SQLite数据保存在Docker卷`zhiliu-data`。备份前请创建一致性快照：

```bash
docker compose exec backend python -c "import sqlite3; src=sqlite3.connect('/data/zhiliu.db'); dst=sqlite3.connect('/data/zhiliu-backup.db'); src.backup(dst); dst.close(); src.close()"
docker cp "$(docker compose ps -q backend):/data/zhiliu-backup.db" ./zhiliu-backup.db
```

将`zhiliu-backup.db`纳入服务器现有的restic/rclone备份任务。

## 验证

```powershell
cd backend
uv run pytest -v

cd ../frontend
npm test -- --run
npm run build
npm audit --omit=dev
```
