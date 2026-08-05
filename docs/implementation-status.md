# V1.0 实现状态

> 更新日期：2026-08-05

## 当前迭代：Iteration 3 结构化数据接入闭环

### 已完成

- DataSource、SyncJob、IngestionRun 和状态转换领域模型。
- Secret 引用校验、API 响应隐藏和可注入 Secret Resolver。
- PostgreSQL 只读连接测试与 Schema 发现适配器。
- Idempotency-Key 启动运行与 Worker 幂等结果回调。
- Checkpoint、Manifest、结果哈希和质量门禁。
- Dataset、不可变 DatasetVersion 和活跃版本指针。
- IngestionRun、DatasetVersion、Serving Rows、Domain Outbox 原子提交。
- PostgreSQL Serving QueryDataPort，保留 Query API 字段契约和策略过滤。
- Audit/Domain Outbox 租户级 Relay、并发领取、退避和幂等事件 ID。
- Iteration 3 Alembic 迁移、全部租户表 RLS 和跨租户负向测试。

### 当前接口

| 方法 | 路径 | 状态 |
|---|---|---|
| POST | `/agent-data/v1/query/{api_code}` | 已实现 |
| POST | `/internal/v1/policy/decisions` | 已实现基础决策 |
| POST | `/api/v1/data-sources` | 已实现 |
| POST | `/api/v1/data-sources/{id}/test` | 已实现 |
| POST | `/api/v1/data-sources/{id}/discover` | 已实现 |
| POST | `/api/v1/sync-jobs` | 已实现 |
| POST | `/api/v1/sync-jobs/{id}/runs` | 已实现 |
| GET | `/api/v1/sync-runs/{id}` | 已实现 |
| POST | `/api/v1/sync-runs/{id}/retry` | 已实现 |
| POST | `/api/v1/sync-runs/{id}/cancel` | 已实现 |
| POST | `/internal/v1/ingestion/runs/{id}/callbacks` | 已实现 |

### 明确限制

- V1.0 Iteration 3 只认证 PostgreSQL 连接器；MySQL和Oracle仍需驱动与方言验收。
- Airflow/Worker、企业 Secret Manager 和 Kafka Publisher 由部署适配器提供，当前仓库交付稳定端口与事务边界。
- Serving JSON 行适配器优先保证契约正确性，尚未完成大规模谓词下推与游标分页。
- OIDC、Knowledge API、Milvus、MinIO和模型网关尚未实现。

## 下一迭代：Iteration 4 知识闭环

1. 文件上传、病毒扫描和 DocumentVersion。
2. Parser/Chunk 处理流水线。
3. Model Gateway 和 Embedding 端口。
4. Milvus 索引版本与 Knowledge API。
5. 文档 ACL 预过滤、返回前复核和引用定位测试。
