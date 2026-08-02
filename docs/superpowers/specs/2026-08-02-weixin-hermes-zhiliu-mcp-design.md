# 微信Hermes写入知流MCP设计

## 目标

让用户在微信中直接与Hermes对话。Hermes完成理解、检索和整理后，根据用户意图自主决定是否调用知流MCP工具，将情报或简报写入知流；只有明确的持续关注意图才创建长期监测规则。该链路不得让知流再次调用Hermes，避免重复消耗token。

## 不做的事情

- 不用固定命令前缀或关键词路由代替Hermes判断；
- 不同步所有微信聊天；
- 不修改Hermes核心源码；
- 不把Hermes已经完成的工作伪装成知流执行任务；
- 不为一次性整理创建长期定时任务；
- 不新增独立前端页面。

## 总体架构

采用Hermes原生支持的Streamable HTTP MCP。知流后端使用官方Python MCP SDK提供工具，Hermes微信gateway从`~/.hermes/config.yaml`发现这些工具。配套skill只描述调用边界和决策规则，工具发现、schema和执行由MCP完成。

```text
微信消息
  → Hermes理解、检索和整理
  → Hermes判断是否需要写入知流
  → 调用知流MCP工具
  → 知流鉴权、校验、去重并原子入库
  → 现有情报页或报告页展示
```

Hermes必须在形成可发布结果后才调用写入工具。普通聊天、解释“知流是什么”或用户没有保存/整理/跟踪意图时不调用工具。

## MCP传输与鉴权

- MCP地址：`http://127.0.0.1:8080/api/mcp`；
- 传输：Streamable HTTP；
- 鉴权：`Authorization: Bearer <ZHILIU_MCP_TOKEN>`；
- `ZHILIU_MCP_TOKEN`独立于Hermes的`API_SERVER_KEY`和知流的`INTEGRATION_SECRET_KEY`；
- 生产环境缺少token、使用示例占位值或长度小于32字符时，知流拒绝启动；
- token只放在知流`.env`和Hermes运行环境中，不写入Git、skill或日志；
- MCP只通过服务器回环地址访问，不为公网客户端提供入口。

在MCP ASGI入口处验证静态Bearer token，优先使用官方MCP SDK提供的认证扩展点；具体接口以实施时锁定的SDK版本为准。比较过程采用恒定时间比较。未携带token或token错误统一返回未授权，不透露token是否存在。

## 工具设计

### `zhiliu_publish`

用途：Hermes已经完成本次工作，将结构化情报、简报或两者一起写入知流。

输入：

```json
{
  "idempotencyKey": "稳定且可重试的本次发布标识",
  "topic": "本次整理主题",
  "kind": "news",
  "requestSummary": "用户原始意图的简短概括",
  "items": [
    {
      "title": "标题",
      "summary": "摘要",
      "url": "https://原文地址",
      "source": "原始来源",
      "keywords": ["关键词"],
      "reason": "推荐理由",
      "importance": 0.9
    }
  ],
  "briefing": {
    "title": "简报标题",
    "content": "简报正文",
    "periodStart": "2026-08-01T00:00:00Z",
    "periodEnd": "2026-08-02T00:00:00Z"
  }
}
```

规则：

- `items`与`briefing`至少提供一个；
- `kind`只能是`news`、`paper`或`job`，本次情报和简报统一使用该类型；
- 情报条目必须提供HTTP或HTTPS原文地址；没有可引用来源的叙述性内容应写成简报；
- 单次最多20条情报；标题、摘要、正文、关键词数量和URL长度使用明确上限；
- `importance`限制为0到1；
- 写入的情报来源显示为`原始来源 · 微信Hermes`；
- 简报标题显示为`微信整理 · 标题`；
- 返回发布回执ID、写入条数、跳过去重条数、简报ID和时间。

### `zhiliu_create_monitor`

用途：用户明确表达“持续关注、每天整理、定期监测”等长期意图时创建知流监测规则。

输入：

```json
{
  "name": "监测名称",
  "kind": "news",
  "keywords": ["关键词"],
  "schedule": "0 8 * * *",
  "prompt": "后续交给Hermes执行的完整任务说明"
}
```

规则：

- `kind`只能是`news`、`paper`或`job`；
- `schedule`必须是合法Cron；
- 相同名称、schedule和prompt已存在时返回原记录；
- 意图不确定时Hermes必须先在微信询问用户，不得擅自创建；
- 创建成功后复用现有scheduler和Hermes执行链路。

本期不增加搜索、删除、编辑或批量管理工具，避免扩大MCP写权限。

## 数据模型

### 自动分类

一次性发布按`kind`归入系统维护的“微信整理·情报”“微信整理·论文”或“微信整理·岗位”Subscription：

- `enabled=false`，不参与定时调度；
- 使用固定系统prompt标识；
- 对应分类在首次发布时惰性创建，不要求用户手动创建或选择；
- 被用户删除后，下次发布自动重建；
- 在设置页作为普通的禁用分类可见，保持数据归属透明。

现有`IntelligenceItem`和`Briefing`继续通过`subscription_id`归属该分类，无需修改已有表结构。

### 发布回执

新增`HermesPublication`表：

- `id`：主键；
- `idempotency_key`：唯一，保存Hermes提供的发布标识；
- `payload_hash`：唯一，保存规范化payload的SHA-256；
- `subscription_id`：微信整理分类；
- `briefing_id`：可空；
- `item_count`：实际新增条数；
- `skipped_count`：被现有指纹去重的条数；
- `topic`：本次主题；
- `request_summary`：用户意图概括，不保存完整微信消息；
- `origin`：固定为`weixin-hermes`；
- `created_at`：UTC时间。

新增表可由现有`Base.metadata.create_all()`安全创建，不修改生产SQLite已有列。

## 幂等与事务

知流先规范化payload并计算`payload_hash`：

1. `idempotency_key`已存在且hash相同：返回原回执；
2. `idempotency_key`已存在但hash不同：拒绝并要求Hermes重新确认；
3. hash已存在：返回已有回执，防止Hermes换key重试产生重复简报；
4. 新payload：在一个事务中创建或读取对应类型的“微信整理”分类、写入情报、写入简报和创建回执；
5. 任一步失败：全部回滚，MCP明确返回“未写入知流”。

情报仍使用现有`title + url`指纹去重。数据库唯一约束作为并发重试的最后保护，服务层捕获冲突后读取已有回执。

## 内容与隐私

- 不保存微信用户ID、昵称、群ID或完整对话；
- `request_summary`只保存完成该发布所需的意图概括；
- 不保存MCP Bearer token；
- API响应和日志不得包含token、Hermes API密钥或完整请求头；
- `raw_output`不用于保存微信原文；
- MCP错误使用稳定中文信息，不返回数据库异常或堆栈。

## Hermes侧集成

仓库提供可部署模板：

```yaml
mcp_servers:
  zhiliu:
    url: http://127.0.0.1:8080/api/mcp
    headers:
      Authorization: "Bearer ${ZHILIU_MCP_TOKEN}"
    tools:
      include:
        - zhiliu_publish
        - zhiliu_create_monitor
```

同时提供知流skill，说明：

- 用户明确提到知流并要求整理、保存或跟踪时评估工具调用；
- 一次性结果调用`zhiliu_publish`；
- 持续性意图调用`zhiliu_create_monitor`；
- 不确定是否长期监测时先询问；
- 工具返回成功前不得告诉用户“已写入”；
- 普通聊天不调用知流工具；
- 不依赖固定命令前缀。

Hermes gateway启动时发现MCP工具。部署更新后重启gateway；如工具发现超时，执行Hermes支持的MCP重载命令或再次重启并检查工具列表。

## 前端呈现

不新增页面：

- 情报进入现有情报页，来源显示`原始来源 · 微信Hermes`；
- 简报进入现有报告页，标题以`微信整理 ·`开头；
- 设置页显示已创建且禁用的“微信整理”分类；
- 长期监测规则与用户手动创建的规则使用相同列表和任务记录。

本期不新增微信会话详情、原消息回放或发布回执管理UI。

## 错误处理

- MCP未授权：拒绝调用且不访问数据库；
- schema不合法：返回字段级错误，不写入数据；
- 原文URL不合法：拒绝整个发布；
- 幂等键冲突：不覆盖原发布；
- 数据库失败：回滚全部内容；
- 长期监测重复：返回已有监测ID；
- 工具失败：Hermes在微信明确说明未写入，并可使用相同幂等键重试；
- MCP不可用不影响知流Web、调度器或Hermes普通微信对话。

## 测试策略

### 后端

- 正确token可初始化MCP，缺失或错误token被拒绝；
- 生产环境拒绝缺失、过短和示例`ZHILIU_MCP_TOKEN`；
- 发布情报、简报及两者组合均成功；
- 来源与简报标题按约定标记；
- 同key同hash、不同key同hash均幂等；
- 同key不同hash被拒绝；
- 情报指纹重复计入`skipped_count`；
- schema、URL、数量和长度限制生效；
- 中途数据库失败不留下Item、Briefing或回执；
- 长期监测创建与完全重复复用现有记录；
- 任一“微信整理”分类被删除后，在相应类型下次发布时自动重建且保持禁用。

### 前端

- 现有情报组件显示组合来源；
- 报告列表显示`微信整理 ·`标题；
- 设置页可以看到禁用的微信整理分类；
- 现有页面在MCP未配置或不可用时不受影响。

### 集成与真实验收

- 使用官方MCP客户端对本地`/api/mcp`完成工具发现和调用；
- 重复调用同payload不会增加数据库记录；
- Hermes微信gateway能发现两个知流工具；
- 微信发送一次明确的知流整理请求后，Hermes回复工具执行结果；
- 知流情报页或报告页出现对应内容和来源；
- 普通微信聊天不产生知流发布回执；
- 持续关注请求创建监测规则并能按现有流程执行。

## 部署变更

- `.env.example`和生产`.env`新增`ZHILIU_MCP_TOKEN`；
- `docker-compose.yml`向backend传入该token；
- README增加生成token、配置Hermes MCP、安装skill、重启gateway和验证工具列表步骤；
- 核云部署更新时先生成token，再同时配置知流和Hermes，最后重建backend并重启Hermes gateway；
- MCP使用`127.0.0.1:8080`，不需要新增公网端口或DNS记录。

## 完成标准

- Hermes根据微信语义自主选择是否调用知流工具；
- 一次性整理不会再次消耗Hermes任务token；
- 写入内容在现有情报页或报告页可见；
- 长期意图进入现有监测链路；
- 重试不会重复入库；
- 未授权调用、普通聊天和失败事务不会污染知流数据；
- 真实微信gateway完成至少一次一次性发布和一次长期监测创建验收。
