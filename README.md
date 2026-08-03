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

若`API_SERVER_KEY`尚未配置，可用下面的命令安全生成；已有值时不要执行，以免让知流UI中保存的旧密钥失效：

```bash
mkdir -p ~/.hermes
touch ~/.hermes/.env
chmod 600 ~/.hermes/.env
if ! grep -Eq '^API_SERVER_KEY=.+$' ~/.hermes/.env; then
  HERMES_API_TOKEN="$(openssl rand -hex 32)"
  sed -i '/^API_SERVER_KEY=/d' ~/.hermes/.env
  printf '\nAPI_SERVER_KEY=%s\n' "$HERMES_API_TOKEN" >> ~/.hermes/.env
  unset HERMES_API_TOKEN
fi
```

重启并检查Hermes：

```bash
hermes gateway restart
curl http://127.0.0.1:8642/health
```

Hermes必须只监听`127.0.0.1:8642`，不要把8642端口开放到公网。知流后端在Linux VPS上使用宿主机网络，因此可以安全访问这个本地端口。

在知流UI进入“订阅与任务→Hermes连接”，填写Hermes地址和API密钥后保存并测试。测试先以无认证GET `/health`证明网络可达，再以Bearer认证GET `/v1/capabilities`证明授权有效；只有提交任务并看到非空`hermesRunId`及新增情报，才算端到端验证成功。`HERMES_API_KEY`仅用于旧部署迁移fallback；UI会显示其掩码，首次测试后将其加密迁移到SQLite。新部署应直接从UI配置。

## 微信Hermes写入知流

这条链路由Hermes理解微信消息，先向知流登记处理任务，再完成检索与整理，最后通过知流MCP写入情报、简报或长期监测。无需固定命令前缀。

先生成独立Token，并分别保存到知流和Hermes环境文件。若已经配置，除非要轮换Token，否则不要重复执行：

```bash
cd /opt/zhiliu
ZHILIU_TOKEN="$(openssl rand -hex 32)"
sed -i '/^ZHILIU_MCP_TOKEN=/d' .env
printf '\nZHILIU_MCP_TOKEN=%s\n' "$ZHILIU_TOKEN" >> .env
mkdir -p ~/.hermes
touch ~/.hermes/.env
chmod 600 ~/.hermes/.env
sed -i '/^ZHILIU_MCP_TOKEN=/d' ~/.hermes/.env
printf '\nZHILIU_MCP_TOKEN=%s\n' "$ZHILIU_TOKEN" >> ~/.hermes/.env
unset ZHILIU_TOKEN
```

`ZHILIU_MCP_TOKEN`用于Hermes调用知流；`API_SERVER_KEY`用于知流调用Hermes，方向相反且必须不同。不要在终端、日志或聊天中输出真实密钥。

在知流`.env`中配置`PUBLIC_BASE_URL=https://zhiliu.academicedu.me`，MCP成功回执才会包含可从微信直接打开的完整处理链路地址。该值不是密钥。

把`deploy/hermes/mcp-zhiliu.yaml.example`中的`mcp_servers.zhiliu`合并到现有`~/.hermes/config.yaml`，不要覆盖原文件。然后安装自然触发skill并重启：

```bash
mkdir -p ~/.hermes/skills/productivity/zhiliu-publisher
cp /opt/zhiliu/deploy/hermes/skills/zhiliu-publisher/SKILL.md ~/.hermes/skills/productivity/zhiliu-publisher/SKILL.md
cd /opt/zhiliu
docker compose up -d --build backend web
hermes gateway restart
hermes mcp test zhiliu
hermes mcp list
hermes skills list
```

配置中的`http://127.0.0.1:8080/api/mcp`适用于Hermes和知流部署在同一台服务器、Web仅绑定本机8080端口的情况。验收时可直接在微信发送：“请检索今天最重要的三条Agent动态，整理好以后放进知流。”Hermes先调用`zhiliu_begin_task`登记处理中状态，完成后调用`zhiliu_publish`；任一步失败则调用`zhiliu_report_failure`。只有发布工具返回成功后才应确认写入，并把回执中的结果摘要和`traceUrl`回复给用户。

三个任务工具必须复用同一个8至160字符的稳定`traceId`，同一次重试也必须复用；能取得真实任务ID时另传`hermesRunId`，不能取得时省略，不得伪造。知流只保存脱敏后的`requestSummary`，不接收微信用户ID、群ID、昵称或完整聊天记录。首页“最近处理动态”和任务详情会实时展示受理、处理、写入、完成或失败状态。

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

Hermes通过服务器回环地址直连MCP；公网域名不需要暴露该入口。在宿主机站点配置中把下面两条规则放在通用代理之前：

```nginx
location = /api/mcp { return 404; }
location ^~ /api/mcp/ { return 404; }
```

这不会影响Hermes访问`http://127.0.0.1:8080/api/mcp`，但会阻止公网请求经域名进入MCP。

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

数据库结构由Alembic管理，后端容器每次启动会先执行`alembic upgrade head`。升级前必须完成上述一致性备份；若要回滚到旧版应用，必须同时恢复升级前数据库备份，禁止只回滚容器并继续使用已升级的SQLite，也不要执行`docker compose down -v`。

## 验证

```powershell
cd backend
uv run pytest -v

cd ../frontend
npm test -- --run
npm run build
npm audit --omit=dev
```
