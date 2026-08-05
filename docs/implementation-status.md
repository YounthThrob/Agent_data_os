# V1.0 实现状态

> 更新日期：2026-08-05

## 当前迭代：Iteration 2 PostgreSQL 元数据与审计基础

### 已完成

- SQLAlchemy 2.0 Engine、Session Factory 和显式依赖组装。
- Tenant、User、Agent、Policy、Grant、Data API 和 Audit Outbox ORM 模型。
- Tenant、User、Agent、Data API 元数据 Repository。
- Policy Grant 与已发布 Query API 的 PostgreSQL Repository。
- Alembic 初始迁移和 PostgreSQL Row Level Security 策略。
- Repository 显式租户过滤与事务级 `app.current_tenant` 双重隔离。
- Query API 成功、拒绝、失败三类审计事件。
- 审计事件敏感值最小化、规范化哈希与 Transactional Outbox。
- 审计通道故障时失败关闭，不交付查询结果。
- 生产环境数据库必填、禁止自动建表的启动校验。
- 精确版本的 `requirements.txt` 与 `requirements-dev.txt`。
- SQLite Repository 集成测试、跨租户负向测试与迁移验证。

### 接口状态

| 方法 | 路径 | 状态 |
|---|---|---|
| GET | `/health/live` | 已实现 |
| GET | `/health/ready` | 已实现 |
| POST | `/agent-data/v1/query/{api_code}` | 已实现首个纵向切片 |
| POST | `/internal/v1/policy/decisions` | 已实现基础决策 |

### 明确限制

- 元数据、授权和审计已支持 PostgreSQL；业务数据查询仍使用 `QueryDataPort` 内存适配器。
- Outbox Kafka Relay、失败重试和 WORM 归档尚未实现。
- 开发 Token 不进行密码学验签，只能用于 development/test；production 会拒绝启用。
- OIDC、数据接入、Knowledge API、模型网关尚未实现。
- 当前切片是领域行为、安全边界与接口契约基线，不代表 V1.0 全量可生产交付。

## 下一迭代：Iteration 3 数据接入闭环

1. DataSource、Connector、SyncJob 和 Checkpoint 领域。
2. PostgreSQL 连接器只读连通测试与 Schema 发现。
3. Worker 任务、Manifest、重试和回调接口。
4. Dataset/DatasetVersion、质量规则和发布状态机。
5. Serving PostgreSQL 查询适配器替换内存业务数据端口。
6. Audit Outbox Kafka Relay 与幂等消费。

## 后续迭代：Iteration 4 知识闭环

1. 文件上传、病毒扫描和 DocumentVersion。
2. Parser/Chunk 处理流水线。
3. Model Gateway 和 Embedding 端口。
4. Milvus 索引版本与 Knowledge API。
5. 文档 ACL 预过滤、返回前复核和引用定位测试。
