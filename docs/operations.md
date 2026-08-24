# 知流运维手册

本文适用于Linux服务器上的Docker Compose部署。知流没有应用登录，访问控制、TLS和公网入口由宿主机现有反向代理负责；Hermes和MCP均不得直接暴露公网。

## 不可破坏的边界

- 数据库位于命名卷`zhiliu-data`的`/data/zhiliu.db`。
- 服务器本机的`.env`、Compose覆盖文件、Nginx配置和Hermes网关配置不是仓库代码，不得提交或被拉取覆盖。
- 禁止执行`docker compose down -v`，也不要删除或重建`zhiliu-data`卷。
- 后端启动会自动执行`alembic upgrade head`。回滚旧代码时必须同时恢复该版本升级前的SQLite备份。
- 命令输出、日志、工单和聊天中不得出现密钥或`.env`内容。

## 运行状态

两个接口承担不同职责：

- `GET /api/health`：存活检查，只验证进程和数据库基础查询，数据库不可用时返回503。
- `GET /api/diagnostics`：非敏感运行摘要，包含数据库延迟和迁移版本、调度器状态、任务积压、最近成败时间、Hermes网络/授权状态及MCP最近写入；不会返回Hermes地址、密钥提示或任务错误正文。

每个HTTP响应都带`X-Request-ID`。应用日志只记录请求ID、方法、路径、状态码和耗时，不记录查询串、请求正文、Authorization或其他headers；排障时用请求ID关联反向代理与应用日志。

诊断状态为`degraded`时，先检查调度器是否运行、最近失败是否晚于最近成功，以及任务收件箱中的失败详情：

```bash
curl --fail --silent http://127.0.0.1:8080/api/health
curl --silent http://127.0.0.1:8080/api/diagnostics
docker compose ps
docker compose logs --tail=100 backend web
```

## 一致性备份

正式脚本使用SQLite Backup API创建在线一致性快照，再执行`PRAGMA integrity_check`并生成SHA-256校验文件。备份目录权限设为700，备份及校验文件权限设为600，容器内临时文件会被清理。

```bash
cd /opt/zhiliu
./deploy/scripts/sqlite-backup.sh /opt/backups/zhiliu
```

输出的`.db`和同名`.sha256`必须一起保存，并纳入服务器现有restic/rclone任务。建议每日备份、保留至少30个日备份和12个周备份；每月至少在隔离环境完成一次恢复演练。

## 内容迁移

跨环境迁移内容时，在源站“设置→数据迁移”下载JSON，在目标站上传同一文件并先查看差异预览。确认导入使用短时、文件绑定的预览凭证；文件变化或凭证过期都必须重新预览。导入只写入内容及公开来源关系，不恢复密钥、内部地址、微信原文、任务历史或Hermes原始发布记录。

目标站会记录迁移批次。撤销只允许删除该批次新增且此后未变化、未被其他内容引用的数据；任一记录不满足条件时整批拒绝，不会部分撤销。内容迁移不能替代SQLite灾备，部署升级前仍须先执行一致性备份。

## 安全发布

1. 记录当前版本并确认工作树。本机部署改动不得提交：

   ```bash
   cd /opt/zhiliu
   git rev-parse HEAD
   git status --short
   docker compose ps
   ```

2. 创建并异地保存一致性备份：

   ```bash
   ./deploy/scripts/sqlite-backup.sh /opt/backups/zhiliu
   ```

3. 对已跟踪的服务器本机修改使用带说明的stash保护；未跟踪的Compose/Nginx覆盖文件原地保留。只允许快进同步，并在同步后重新应用本机修改：

   ```bash
   LOCAL_STASH=""
   if ! git diff --quiet -- docker-compose.yml; then
     git stash push -m "zhiliu-pre-release-local-tracked" -- docker-compose.yml
     LOCAL_STASH="$(git stash list -1 --format='%gd')"
   fi
   git pull --ff-only origin main
   if [ -n "$LOCAL_STASH" ]; then
     git stash apply "$LOCAL_STASH"
   fi
   ```

   若重新应用时发生冲突，立即停止；只保留经过核验的服务器端口、网络和网关差异，不要继续构建。

4. 执行发布门禁：

   ```bash
   cd backend
   uv sync --dev
   uv run pytest -q
   cd ../frontend
   npm ci
   npm test -- --run
   npm run build
   npm audit --audit-level=high
   cd ..
   docker compose config --quiet
   ```

5. 只重建应用服务：

   ```bash
   docker compose up -d --build backend web
   ./deploy/scripts/acceptance.sh
   ```

6. 用域名验收公网MCP确实被宿主机Nginx隐藏：

   ```bash
   PUBLIC_BASE_URL=https://zhiliu.example.com ./deploy/scripts/acceptance.sh
   ```

`deploy/nginx-host.conf.example`是宿主机代理的最小参考，MCP拒绝规则必须位于通用`location /`之前。它不替代现有TLS或访问控制配置。

## 回滚与恢复

先确定要恢复的应用commit及其升级前备份。不要只切换代码继续使用已被新版本迁移的数据库。

恢复脚本会先校验SHA-256和SQLite完整性，再自动创建一份恢复前安全备份；只有提供固定确认词才会停止backend并原子替换数据库。它不会删除卷。

```bash
cd /opt/zhiliu
./deploy/scripts/sqlite-restore.sh \
  /opt/backups/zhiliu/zhiliu-YYYYMMDDTHHMMSSZ.db \
  RESTORE_ZHILIU_SQLITE
```

如需同时回退代码，顺序是：停止backend、切换到明确的旧commit、恢复与该commit匹配的升级前备份、重建backend/web、执行验收。生产回滚前先在副本上演练；不得在运行中的生产库上做“试恢复”。

## 验收矩阵

自动脚本会检查Compose渲染、容器运行、本机健康与诊断接口、本机未认证MCP返回401、公网MCP可选返回404，以及活跃SQLite完整性。随后还要人工确认：

- 首页、情报、报告、质量、任务收件箱和设置页均可打开；详情链路可追溯。
- Hermes容器网关可达，测试连接成功；微信真实任务返回非空`taskUrl`、`briefingUrl`和`traceUrl`。
- 重启后既有情报、报告和任务仍存在。
- 宿主机8010、8642不对公网监听；Web仍只绑定`127.0.0.1:8080`。
- backend/web最近100行日志无Traceback、500、数据库异常和前端资源404。

## 备份恢复演练

每月在隔离目录或临时服务器执行：校验备份与`.sha256`、恢复到独立卷、启动相同commit、运行`acceptance.sh`、抽查关键情报/报告/任务，再销毁临时环境。演练记录至少包含备份时间、commit、迁移版本、校验结果、恢复耗时和验收结果，不记录任何密钥。
