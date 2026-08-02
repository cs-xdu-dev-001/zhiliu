# 知流内容可追溯设计

## 目标

让每条新情报和每份新报告都能证明其来源与处理过程：脱敏微信指令、Hermes整理任务、MCP写入回执、知流写入或复用的情报，以及最终生成的报告。报告详情必须展示准确的来源情报和原始链接，不能依靠时间、订阅或数量猜测关联。

## 范围

本期包含：

- 微信Hermes通过MCP发布内容的完整追踪。
- 定时订阅通过Hermes REST执行后的同结构追踪。
- 报告与实际引用情报的关系。
- 情报、报告和独立追踪详情API。
- 情报详情、报告详情和独立追踪页。
- 核云现有SQLite的无损迁移。

本期不包含：

- 保存完整微信聊天原文、微信用户ID、群ID或昵称。
- 对历史数据进行猜测性关联或批量回填。
- 通用事件溯源系统。
- 更换SQLite或重做现有订阅、任务体系。

## 隐私与追踪标识

知流只保存脱敏后的`request_summary`和不含身份信息的稳定`trace_id`。新版Hermes skill为每次微信指令生成随机追踪ID，同一次调用重试必须复用相同`trace_id`和`idempotency_key`。

`hermes_run_id`可选。Hermes网关能够取得真实任务ID时传入；不能取得时省略。知流不得生成伪任务ID，界面显示“本次网关未提供任务ID”，但链路仍由`trace_id`和MCP回执连续关联。

## 数据模型

### HermesPublication

继续使用现有`HermesPublication`作为一次内容处理的追踪根，新增以下可空字段以兼容历史数据：

- `trace_id: String(160)`：微信指令或定时任务的稳定追踪ID，建立索引。
- `hermes_run_id: String(255)`：真实Hermes任务ID，建立索引。
- `task_run_id: Integer`：可选关联现有`TaskRun.id`，建立索引。

保留并复用现有字段：

- `idempotency_key`负责发布幂等。
- `payload_hash`负责相同载荷去重。
- `request_summary`保存脱敏指令摘要。
- `origin`区分`weixin-hermes`和`subscription-hermes`。
- `briefing_id`关联最终报告。
- `item_count`和`skipped_count`保留现有MCP回执语义：分别表示本次新写入和因去重复用的数量。

`Briefing.item_count`改为本报告实际关联的全部来源情报数量，即新写入数与去重复用数之和；MCP回执中的`item_count`仍表示新写入数，二者不混用。

`trace_id`不设唯一约束。一次用户意图将来可能包含多次合法发布；真正阻止重复写入的仍是`idempotency_key`。

### PublicationItem

新增`publication_items`关联表：

- `publication_id`：外键关联`hermes_publications.id`，删除Publication时级联。
- `item_id`：外键关联`intelligence_items.id`。
- `ordinal`：情报在Hermes整理结果中的原始顺序，从0开始。
- `was_inserted`：本次发布是否新建该情报；`false`表示复用既有去重记录。
- `created_at`：建立关联的时间。
- `(publication_id, item_id)`唯一约束。

一次发布必须关联载荷中实际引用的全部情报，包括按`fingerprint`复用的既有情报。报告通过其`HermesPublication`和`publication_items`获得准确来源，不再根据`item_count`猜测。情报可关联多次发布，最早记录是“首次写入”，后续记录是“再次引用”。

## 数据写入流程

### 微信MCP发布

1. 微信用户向Hermes下达自然语言指令。
2. Hermes生成脱敏摘要、稳定`trace_id`和`idempotency_key`。
3. Hermes完成检索与整理，调用`zhiliu_publish`。
4. 知流验证幂等键与载荷哈希。
5. 知流写入新情报或解析到已存在的去重情报。
6. 知流创建`HermesPublication`与全部`PublicationItem`关系。
7. 载荷包含报告时创建`Briefing`并写入`briefing_id`。
8. 整个过程在同一事务中提交，返回MCP回执。

新版`zhiliu_publish`参数新增：

- `traceId`：必填，8至160个字符。
- `hermesRunId`：可选，最长255个字符。

回执新增`traceId`，保留可点击使用的`receiptId`。Hermes skill必须同步升级；缺少`traceId`时返回明确的参数校验错误。

### 定时订阅

现有`RunService`在Hermes执行成功并完成情报、报告写入后，同时创建：

- `origin = subscription-hermes`的`HermesPublication`。
- `trace_id = task-run:{task_run_id}`。
- `task_run_id`和真实`hermes_run_id`。
- 本次结果中全部新建或复用情报的`PublicationItem`。

定时任务不伪装成MCP调用；追踪页明确显示写入方式为“定时订阅”。

## 查询API

### GET /api/items/{item_id}

详情响应在现有情报字段外增加`publications`数组，每项包含：

- Publication ID、`traceId`、`origin`、`requestSummary`和创建时间。
- `hermesRunId`、`taskRunId`。
- `wasInserted`、`ordinal`。
- 可选关联报告的ID和标题。

数组按Publication创建时间升序排列，首项标记为首次写入，后续项为再次引用。历史数据返回空数组和`traceAvailable = false`。

### GET /api/briefings/{briefing_id}

详情响应在现有报告字段外增加：

- `sourceItems`：按`ordinal`排列的情报摘要，包含ID、标题、两行摘要所需文本、来源、原始URL、是否本次新写入。
- `publication`：生成该报告的追踪摘要。
- `traceAvailable`。

历史报告没有Publication时返回空来源列表，不推断关系。

### GET /api/publications/{publication_id}/trace

返回独立追踪页所需的完整聚合结果：

- 脱敏指令摘要和`traceId`。
- Hermes任务ID或缺失状态。
- 写入方式、回执ID、写入时间、写入数和复用数。
- 可选订阅与TaskRun摘要。
- 按顺序排列的全部关联情报和原始链接。
- 可选最终报告摘要。

不存在时返回404。API不返回`TaskRun.raw_output`、聊天原文、密钥或Token。

## 前端体验

### 情报详情

在现有正文后增加“写入记录”。每条记录以脱敏指令摘要作为主要信息，并显示：

- 首次写入或再次引用。
- 微信MCP或定时订阅。
- 写入时间。
- 可选关联报告。
- “查看完整链路”链接。

没有追踪关系时显示“历史数据，暂无完整追踪信息”。

### 报告详情

在正文后增加“来源情报”，按Hermes原始顺序展示：

- 标题和两行摘要。
- 来源。
- 情报详情链接。
- 独立的“打开原文（新窗口）”操作。

生成链路摘要提供“查看生成链路”入口。来源情报的原始链接不得嵌套在情报详情链接内。

### 独立追踪页

新增`/traces/:publicationId`，使用单列时间线展示：

1. 微信指令摘要或定时订阅输入。
2. Hermes整理任务。
3. MCP写入回执或内部任务写入。
4. 知流写入或复用的情报。
5. 最终生成的报告。

缺失`hermes_run_id`时明确说明，不将其渲染为错误。页面沿用当前知流视觉体系和Lucide图标；手机端保持单列，核心信息使用正常正文，不用小字承载。

## 数据迁移

引入Alembic作为正式迁移机制。首个迁移必须兼容：

- 空数据库：创建最新模型结构并写入Alembic版本。
- 核云现有数据库：保留全部表和数据，只增加追踪字段、索引及`publication_items`表。

由于现有项目依赖`Base.metadata.create_all()`启动，首个迁移使用SQLAlchemy Inspector检测核心表、字段和索引：空库直接按当前模型创建完整结构；旧库只补充缺失的追踪字段、索引和`publication_items`表。迁移完成后写入同一个Alembic版本。既有SQLite增加的可空字段不得要求历史数据回填。

应用启动路径移除`Base.metadata.create_all()`，结构创建和升级统一交给Alembic；测试夹具也先执行`alembic upgrade head`再启动应用，避免生产与测试走两套建表逻辑。

容器启动顺序调整为：

1. `alembic upgrade head`。
2. 启动Uvicorn。

部署前必须使用SQLite backup API创建一致性备份，禁止删除Docker卷或执行`down -v`。

## 异常与一致性

- 相同`idempotency_key`和相同载荷返回原回执，不新增关系。
- 相同`idempotency_key`但载荷不同继续返回冲突。
- 相同情报被`fingerprint`去重时仍建立本次Publication关系，`was_inserted = false`。
- Publication、情报关系和报告在同一事务中写入，失败时整体回滚。
- `hermes_run_id`缺失是正常状态。
- 历史数据缺少追踪关系是兼容状态。
- 关联数据异常缺失时API返回可恢复的空状态，不制造虚假链路。

## 测试与验收

后端必须覆盖：

- 旧版SQLite带历史数据升级后数据完整。
- 空数据库迁移。
- MCP字段验证与camelCase协议。
- 微信MCP发布产生完整追踪。
- 去重情报仍出现在Publication和报告来源中。
- 定时订阅创建相同结构的追踪记录。
- 幂等重试不新增PublicationItem。
- 情报详情、报告详情、追踪详情成功和404。
- 历史数据返回兼容空状态。
- 响应不暴露聊天原文、`raw_output`或密钥。

前端必须覆盖：

- 情报写入记录与历史空状态。
- 报告来源情报、详情链接和独立原文链接。
- 完整链路五个节点及缺少Hermes任务ID的状态。
- 动态路由、加载、错误和404。
- 桌面端与390px移动端布局。

Playwright验收路径：报告详情→来源情报→情报详情→完整链路，并核对返回导航和外部原文链接。

## 部署与回滚

核云同步流程：

1. 确认Git状态和本机部署覆盖文件。
2. 对`/data/zhiliu.db`创建一致性备份并复制到宿主机。
3. 拉取指定Commit。
4. 检查最终Compose配置仍保持端口隔离。
5. 构建并启动，启动过程自动执行Alembic迁移。
6. 验证迁移版本、健康检查、MCP发布、详情API和三类详情页面。
7. 更新服务器Hermes publisher skill，使其传入`traceId`。

回滚应用代码前必须同时恢复迁移前SQLite备份；不得只回滚容器镜像而继续使用不匹配的数据结构。
