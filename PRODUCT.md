# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

主要用户是将知流部署在个人VPS上的单用户。用户在手机或电脑浏览器中管理长期关注的主题，集中阅读、筛选和回顾热点、论文与招聘情报。

## Product Purpose

知流持续监测用户关注的信息源，将联网检索和分析结果整理为可管理的情报历史与日报、周报。产品成功意味着用户能以较低维护成本掌握重要更新，并快速完成阅读、收藏、忽略和回看。

## Positioning

知流不重复实现通用Agent能力：Hermes负责联网检索、网页阅读、论文分析与摘要，知流负责订阅需求配置、定时调度、结果校验、去重入库和面向个人的信息消费界面。

## Operating Context

- 用户维护包含名称、类型、关键词、执行周期和Hermes任务说明的订阅。
- 系统定时或按用户手动触发Hermes任务，并持续记录排队、执行、完成或失败状态。
- 用户通过首页概览、情报流、日报/周报、订阅设置和任务记录完成日常使用。
- 产品运行在个人VPS上，Hermes仅通过宿主机本地地址访问；公网入口由Nginx或Caddy提供HTTPS。

## Capabilities and Constraints

- 情报类型限定为热点、论文和招聘，支持未读、收藏与忽略状态。
- 情报结果按原文URL和标题指纹去重，失败任务不得覆盖已有数据。
- 同一订阅避免重叠运行；调度时区为Asia/Shanghai。
- 应用采用单操作者模型，不提供登录；公网访问必须由Nginx/Caddy等部署层IP白名单保护。
- 首版不建设通用爬虫、自建RAG向量库、复杂工作流或知识库全量同步。
- 技术边界为React 19、TypeScript、Vite、FastAPI、SQLite、APScheduler、Docker Compose和Nginx。

### Hermes连接与任务状态

Hermes连接状态分为未配置（unconfigured）、不可达（unreachable）、未授权（unauthorized）、已连接（connected）和错误（error）五种。操作者在“订阅与任务→Hermes连接”填写地址和密钥并保存/测试；前端先无认证GET `/health`确认可达，再用Bearer GET `/v1/capabilities`确认授权。提交任务后必须产生非空`hermesRunId`并写入新情报，才是端到端成功证明。旧部署可通过`HERMES_API_KEY`迁移fallback，新部署从UI保存配置。

## Brand Commitments

产品名称为“知流”。界面语言为简洁、直接的中文，产品术语沿用“情报”“订阅”“简报”“任务记录”和“Hermes任务说明”。

## Evidence on Hand

- `README.md`与`docs/`包含产品范围、架构、部署和安全约束。
- `backend/app/seed.py`提供3个示例订阅、8条示例情报、2份简报和4条任务记录，仅可作为演示内容，不得包装成真实客户数据或效果证明。
- 当前没有真实客户评价、使用规模、准确率、节省时间等对外证明，后续设计不得虚构。

## Product Principles

- 让重要信息浮现，而不是增加新的信息噪声。
- 保持Hermes与知流的职责边界清晰。
- 优先支持单用户在手机上的快速查看和处理。
- 任务失败必须可见、可追踪，且不损害已有数据。
- 用可靠的筛选、状态和去重建立长期可回看的个人情报库。
