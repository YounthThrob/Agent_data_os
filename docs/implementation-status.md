# V1.0 实现状态

> 更新日期：2026-08-05

## 当前迭代：Iteration 4 安全知识闭环

### 已完成

- KnowledgeBase、Document、DocumentVersion、Chunk 和 IndexVersion 领域模型。
- 服务端对象路径、文件大小/MIME/SHA-256 验证和病毒扫描端口。
- Parser/OCR 组合端口、固定版本 Chunk 策略和处理幂等性。
- Chunk Tenant 内容加密和正文/向量分离存储。
- Model Gateway Embedding、Milvus、MinIO、ClamAV 和 DeepSeek 适配器。
- 完整语料蓝绿 IndexVersion 构建与原子发布。
- Knowledge API 证据、引用、证据不足降级及严格模式。
- Milvus ACL 预过滤与 PostgreSQL 当前 ACL/文档状态二次授权。
- 查询 Prompt Injection 阻断与召回内容投毒过滤。
- `CONFIDENTIAL/SECRET` 模型出站阻断和仅证据降级。
- Knowledge API 成功/拒绝审计和 `Cache-Control: no-store`。
- Iteration 4 Alembic 迁移及知识表 PostgreSQL RLS。

### 当前接口

| 方法 | 路径 | 状态 |
|---|---|---|
| POST | `/agent-data/v1/query/{api_code}` | 已实现 |
| POST | `/agent-data/v1/knowledge/{api_code}` | 已实现 |
| POST | `/api/v1/data-sources` | 已实现 |
| POST | `/api/v1/sync-jobs` | 已实现 |
| POST | `/api/v1/knowledge-bases` | 已实现 |
| POST | `/api/v1/files/uploads` | 已实现 |
| POST | `/internal/v1/knowledge/document-versions/{id}/process` | 已实现 |
| POST | `/api/v1/knowledge-bases/{kb_id}/indexes/{index_id}/publish` | 已实现 |

### 明确限制

- 开发 Parser 只解析 UTF-8 文本；生产 PDF/Office/OCR 引擎通过组合适配器注入。
- 生产 MinIO、ClamAV、Milvus、KMS、Embedding 和 DeepSeek 客户端必须由部署层配置。
- 尚未实现检索重排、Graph API、复杂知识图谱和多模型成本路由。
- OIDC、审批工作流、生产 Worker 编排与运营控制台仍需后续交付。

## 下一阶段建议

1. 完成 OIDC、企业KMS与Secret Manager生产适配。
2. 完成Airflow/Worker、Kafka Publisher和可观测性部署。
3. 增加PDF/Office/OCR沙箱、解析质量评测和检索评测集。
4. 完成DeepSeek Token成本、配额、熔断和模型路由中心。
5. 建设管理控制台与行业Agent模板。
