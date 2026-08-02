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

访问`http://127.0.0.1:5173`。知流没有应用登录；请仅在受部署层保护的网络中访问。

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

在知流UI进入“订阅与任务→Hermes连接”，填写Hermes地址和API密钥后保存并测试。测试先以无认证GET `/health`证明网络可达，再以Bearer认证GET `/v1/capabilities`证明授权有效；只有提交任务并看到非空`hermesRunId`及新增情报，才算端到端验证成功。`HERMES_API_KEY`仅用于旧部署迁移fallback；UI会显示其掩码，首次测试后将其加密迁移到SQLite。新部署应直接从UI配置。

## VPS部署

```bash
sudo mkdir -p /opt/zhiliu
sudo chown "$USER":"$USER" /opt/zhiliu
cd /opt/zhiliu
# 将仓库同步到此目录
cp .env.example .env
```

生成集成密钥：

```bash
openssl rand -hex 32
```

编辑`.env`，必须将`INTEGRATION_SECRET_KEY`替换为刚生成的随机值；后端会拒绝示例占位值。然后启动：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

默认只在宿主机`127.0.0.1:8080`提供Web服务。当前Compose按Linux VPS设计，后端使用宿主机网络访问仅监听`127.0.0.1:8642`的Hermes；后端仍会在宿主机监听8010，因此防火墙必须拒绝公网访问8010，并将8080的本机绑定作为纵深保护。使用宿主机现有Nginx或Caddy将域名HTTPS流量反向代理到`http://127.0.0.1:8080`。

Windows或macOS的Docker Desktop只有在显式启用host networking且验证可达性后才能沿用此配置；否则应改为桥接网络，并将`HERMES_BASE_URL`设为`http://host.docker.internal:8642`，同时让Hermes只接受受控的本机/容器网段访问。不要在未验证隔离边界时把8642暴露到公网。

知流没有应用登录，公网暴露前必须启用部署层IP白名单。例如Nginx：

```nginx
location / {
    allow 203.0.113.10;
    deny all;
    proxy_pass http://127.0.0.1:8080;
}
```

请替换示例IP，并按现有Nginx配置正确设置`Host`、`X-Real-IP`、`X-Forwarded-For`等代理headers。若Nginx前还有CDN或其他反向代理，只能信任明确列出的代理地址，并用`set_real_ip_from`与`real_ip_header`恢复客户端IP；不要直接信任任意请求提供的`X-Forwarded-For`做白名单判断。Compose后端使用宿主机网络时，`127.0.0.1:8642`指向宿主机Hermes。

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
