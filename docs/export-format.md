# 内容导出格式

在“设置→数据导出”选择JSON或Markdown，并可按开始日期、结束日期、主题和内容类型筛选。服务端先在权限为600的临时文件中完整生成结果，成功后才开始下载；生成失败会删除临时文件，不返回看似可用的半成品。

也可直接调用：

```text
GET /api/export?format=json&fromDate=2026-08-01&toDate=2026-08-31&topicId=3&kind=paper&include=items&include=reports
```

- `format`：`json`或`markdown`。
- `fromDate`、`toDate`：闭区间，按各记录的创建/开始时间筛选。
- `topicId`：只保留该主题关联的情报、报告和任务；偏好仅保留该主题规则。
- `kind`：`news`、`paper`或`job`。
- `include`：可重复，取值为`items`、`reports`、`sources`、`tags`、`topics`、`preferences`、`tasks`；省略时导出全部。

## JSON结构

顶层字段为：

```json
{
  "schemaVersion": 1,
  "exportedAt": "2026-08-24T12:00:00+00:00",
  "filters": {},
  "data": {},
  "counts": {}
}
```

`data`按选择范围包含以下数组：

- `subscriptionRefs`：内容引用到的订阅名称和类型，不包含关键词、Cron或Hermes任务说明；导入时用于匹配目标订阅。
- `items`、`sources`、`tags`：情报正文、公开来源和标签。
- `topics`、`itemTopics`：主题及情报与主题的关联。
- `reports`、`reportSources`：报告及按引用顺序排列的来源情报。`reportSources`直接保留来源标题、来源名和公开原始链接，即使未选择`items`也不会丢失引用证据。
- `preferences`：当前偏好规则。
- `tasks`、`publications`：任务状态、重试关系和知流写入记录；保留非密钥`traceId`，用于在迁移后重新连接同一次Hermes处理链路。

所有关系使用文件内ID连接，导入时会重新映射，绝不直接当作目标数据库ID。损坏的JSON文本字段会降级为空值，避免破坏整个导出文件。

## 安全边界

导出采用字段白名单，不包含Hermes API密钥、MCP Token、加密密钥、Authorization、Hermes运行ID、任务原始输出、错误正文、完整微信消息、订阅Prompt或内部服务器地址。公开URL中的`token`、`api_key`、`signature`等敏感查询参数会被移除；公网原始链接与普通查询参数会保留。

知流没有应用登录，导出接口沿用站点的Nginx/IP访问控制。不要单独把`/api/export`暴露到公网。

## 导入与恢复

JSON内容导出可在“设置→数据迁移”中预览并导入。导入只恢复情报、标签、主题、偏好、报告和报告来源；任务、原始发布记录、用户、密钥和集成配置不会写入目标系统。报告版本冲突时默认保留现有版本，也可明确选择创建新版。

导入采用两步确认：预览凭证绑定文件SHA-256并在30分钟后过期，确认阶段重新验证同一文件，整批内容在单个数据库事务中写入。每次成功导入生成审计批次；只有内容未被后续修改或引用时才能原子撤销。

也可在转移文件后先运行只读校验：

```bash
cd /opt/zhiliu/backend
uv run python -m app.ops.content_export /path/to/zhiliu-export.json
```

校验器检查schema版本、各数组计数以及情报、报告、主题间的基本引用；输出`status=ok`后，文件才适合作为迁移输入。Markdown用于人工阅读，不是恢复输入。

## 与SQLite备份的区别

内容导出可跨环境阅读和迁移，但不包含用户、集成配置、密钥、全部内部状态和数据库迁移信息。灾难恢复、版本回滚和原样恢复必须使用`deploy/scripts/sqlite-backup.sh`生成的SQLite一致性快照及SHA-256文件，不能用JSON或Markdown替代。
