# Hermes集成管理设计

## 目标

为知流补齐可由前端管理、由后端安全执行的Hermes连接配置与连通性验证，同时移除应用自身的登录体系，将访问控制完全交给部署层的Nginx或Caddy IP白名单。

## 安全边界

- 知流不再提供登录页、JWT Cookie、用户密码或API登录校验。
- 任何能够通过反向代理IP白名单访问知流的人都拥有完整管理权限。
- 部署文档必须明确要求先配置IP白名单，再开放知流。
- Hermes API密钥可以由前端提交，但后端永不向前端返回完整密钥。
- Hermes API密钥使用服务器环境变量`INTEGRATION_SECRET_KEY`加密后存入SQLite。
- `INTEGRATION_SECRET_KEY`只用于静态加密，不通过API暴露；生产环境缺少或不合法时，后端拒绝启动。
- Hermes仍应只监听同机回环地址或受保护的私有网络，不允许将8642端口直接暴露到公网。

## 后端架构

### 持久化模型

新增单例Hermes集成配置，包含：

- `base_url`：Hermes API Server地址；
- `encrypted_api_key`：加密后的API密钥；
- `api_key_hint`：仅用于展示的末四位；
- `last_status`：最近一次检测状态；
- `last_message`：面向用户的检测结果；
- `last_checked_at`：最近检测时间；
- `hermes_version`：检测成功时返回的Hermes版本；
- 创建及更新时间。

配置密钥时使用Fernet对称加密。更新请求中的密钥为空或缺省时保留原密钥，避免浏览器先读取完整密钥。更换`INTEGRATION_SECRET_KEY`前必须先重新加密已有数据，否则旧配置无法解密。

### 服务边界

新增独立的Hermes集成服务，负责：

1. 加密和解密API密钥；
2. 读取及保存当前配置；
3. 规范化并验证`base_url`；
4. 执行连接检测；
5. 将网络和HTTP错误归类为稳定的前端状态；
6. 为调度器提供当前有效的Hermes客户端配置。

现有`HermesClient.execute()`继续只负责创建和轮询真实任务。连接检测使用单独方法，避免为了验证密钥而创建无意义任务。

### 连接检测

检测严格按以下顺序执行：

1. 配置缺失：返回`unconfigured`；
2. 请求`GET /health`：验证服务可达，读取`platform`与`version`；
3. 请求`GET /v1/capabilities`并携带`Authorization: Bearer <key>`：验证密钥；
4. 两步均成功：返回`connected`。

稳定状态及含义：

- `unconfigured`：地址或密钥尚未配置；
- `unreachable`：DNS、连接、TLS或超时失败；
- `unauthorized`：Hermes返回401或403；
- `connected`：健康检查和受保护能力端点均成功；
- `error`：Hermes返回其他异常响应或不符合协议。

检测不得返回请求头、完整密钥或Hermes内部异常堆栈。超时使用短连接检测超时，不沿用最长180秒的任务执行超时。

### API

#### `GET /api/integrations/hermes`

返回：

```json
{
  "baseUrl": "http://127.0.0.1:8642",
  "apiKeyConfigured": true,
  "apiKeyHint": "••••a9f2",
  "status": "connected",
  "message": "Hermes已连接并通过鉴权",
  "checkedAt": "2026-08-02T10:30:00+08:00",
  "version": "1.2.3"
}
```

没有持久化配置时，返回默认`HERMES_BASE_URL`以及`unconfigured`，不返回环境变量密钥提示。

#### `PUT /api/integrations/hermes`

请求：

```json
{
  "baseUrl": "http://127.0.0.1:8642",
  "apiKey": "new-secret-or-empty"
}
```

保存配置后立即执行检测，并返回与GET相同的状态结构。`apiKey`为空时保留原值；首次配置时密钥不能为空。

#### `POST /api/integrations/hermes/test`

使用已保存配置执行检测、持久化检测结果，并返回状态结构。该接口不创建Hermes Run。

### 调度器集成

- 调度任务执行前读取数据库中的当前Hermes配置，而不是只读取进程启动时的环境变量。
- 已保存配置优先于旧的`HERMES_BASE_URL`和`HERMES_API_KEY`环境变量。
- 在迁移期间，如果数据库没有配置且环境变量包含真实密钥，可以继续使用环境变量执行任务，但前端状态仍提示用户迁移到受管配置。
- `DEMO_MODE=true`且没有任何真实密钥时继续使用DemoHermes；`DEMO_MODE=false`且配置缺失时任务明确失败为“尚未配置Hermes连接”。
- 真实任务成功后继续保存`hermes_run_id`，供任务记录证明端到端执行来源。

## 前端设计

### 位置与信息层级

在“订阅与任务”页面顶部、任务记录和新建订阅工具栏之前增加“Hermes连接”区域。该区域保持现有Operate模式，不使用营销式大标题或冗长说明。

默认状态直接展示：

- 连接状态及文字；
- 服务地址；
- 脱敏密钥提示；
- Hermes版本；
- 最近检测时间；
- “测试连接”和“配置连接”操作。

状态不能只依赖颜色，同时使用图标和明确文字。

### 配置交互

“配置连接”打开受保护焦点的对话框，包含：

- Hermes服务地址；
- Hermes API密钥密码输入框；
- 密钥留空时显示“保留当前密钥”；
- 主操作“保存并测试”；
- 取消和Esc关闭。

保存期间禁用重复提交。成功后关闭对话框并更新状态；失败时保留输入内容，显示准确原因和再次测试入口。

### 状态文案

- 未配置：`尚未配置Hermes连接`；
- 不可达：`无法连接Hermes服务，请检查地址和服务状态`；
- 鉴权失败：`Hermes拒绝了当前密钥，请重新配置`；
- 已连接：`Hermes已连接并通过鉴权`；
- 服务异常：`Hermes响应异常，请查看服务日志`。

最近检测时间使用本地化日期时间。进行中的测试通过禁用按钮和`aria-live`状态向辅助技术播报。

## 移除登录体系

后端删除或停用：

- `/api/auth/login`、`/api/auth/logout`、`/api/auth/me`；
- JWT Cookie和当前用户依赖；
- 生产环境对`JWT_SECRET`、`ADMIN_USERNAME`、`ADMIN_PASSWORD`的要求；
- 不再需要的用户初始化逻辑。

前端删除：

- `/login`路由和登录页；
- AppShell的当前用户查询、401跳转、用户名展示和退出按钮；
- 登录相关类型、测试和E2E步骤。

数据库已有`users`表可以在本次迁移中保留，避免对现有SQLite执行破坏性迁移；代码不再读写该表。后续可在单独的数据迁移版本中清理。

## 错误处理

- 配置格式错误返回400和可操作说明；
- 加密主密钥缺失属于启动配置错误，不降级为明文保存；
- 已保存密文无法解密时状态为`error`，要求重新输入密钥；
- Hermes健康检查成功但鉴权失败时必须返回`unauthorized`，不能笼统显示不可达；
- 测试失败不覆盖地址和密钥配置，只更新最近检测结果；
- 保存新密钥后检测失败仍保留新配置，便于修复Hermes服务后直接重试；
- API响应和日志不得包含完整密钥。

## 测试策略

### 后端

- 加密密钥可往返解密，API响应仅包含脱敏提示；
- 无配置返回`unconfigured`；
- `/health`连接失败返回`unreachable`；
- `/v1/capabilities`返回401/403时返回`unauthorized`；
- 两个端点成功时返回`connected`和版本；
- PUT保存后自动检测，空密钥更新保留原密钥；
- 调度器优先读取数据库配置；
- 所有业务API在无Cookie情况下可访问；
- 原认证端点不可用。

### 前端

- 正确渲染五种连接状态；
- 配置表单不会回显完整密钥；
- “保存并测试”和“测试连接”调用正确接口并显示结果；
- 请求期间按钮不可重复提交；
- 鉴权失败和不可达使用不同文案；
- App直接进入首页，无登录跳转。

### 端到端

- 无登录步骤访问首页；
- 打开Hermes配置、保存模拟配置并看到检测结果；
- 桌面和移动端无横向溢出；
- 真实部署验收时以`/health`、`/v1/capabilities`及一次产生`hermes_run_id`的订阅任务作为三级连接证据。

## 部署变更

- `.env.example`新增`INTEGRATION_SECRET_KEY`，删除不再使用的JWT和管理员登录配置。
- README增加IP白名单示例和“未配置白名单不得公网部署”的醒目约束。
- README说明Hermes端`API_SERVER_ENABLED=true`及`API_SERVER_KEY`配置，并要求知流前端录入同一密钥。
- 现有`.env`中的Hermes配置可作为迁移来源，但不在日志或前端中输出完整值。
