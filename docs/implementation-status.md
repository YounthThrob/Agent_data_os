# V1.0实现状态

> 更新日期：2026-08-05

## 当前迭代：安全骨架与Query API纵向切片

### 已完成

- Python/FastAPI `src`工程结构与显式依赖组装。
- 环境配置和生产安全配置校验。
- 请求ID、Trace ID和统一安全响应头。
- 统一API错误信封和Pydantic严格请求校验。
- `IdentityResolver`端口、生产默认拒绝适配器及开发身份适配器。
- Policy领域模型、默认拒绝策略和行级约束义务。
- Data Service领域模型、Query API定义及端口。
- Query API字段白名单、过滤操作符、排序、限量和用途校验。
- 策略生成的不可覆盖区域过滤。
- 开发/测试内存Repository与示例数据。
- Agent Query API、内部Policy Decision API和健康检查。
- 自动化安全及契约测试。

### 当前接口

| 方法 | 路径 | 状态 |
|---|---|---|
| GET | `/health/live` | 已实现 |
| GET | `/health/ready` | 已实现 |
| POST | `/agent-data/v1/query/{api_code}` | 已实现首个纵向切片 |
| POST | `/internal/v1/policy/decisions` | 已实现基础决策 |

### 验证结果

| 检查 | 结果 |
|---|---|
| `python -m pytest -q` | 10项全部通过 |
| `python -m compileall -q src` | 通过 |
| OpenAPI生成 | OpenAPI 3.1.0，4个路径，Query路径存在 |
| 覆盖率报告 | 当前环境未安装`pytest-cov`，尚未生成；依赖已在`pyproject.toml`声明 |

### 明确限制

- 当前数据、API定义和Grant使用内存适配器，不具备生产持久化能力。
- 开发Token不进行密码学验签，只能用于development/test；production会拒绝启用。
- 尚未实现OIDC、PostgreSQL、审计Outbox、Kafka、数据接入和Knowledge API。
- 当前接口代表契约和领域行为基线，不代表V1.0全部功能已经完成。

## 下一迭代建议

### Iteration 2：PostgreSQL元数据与审计基础

1. 引入SQLAlchemy/Alembic或团队确认的数据访问方案。
2. 建立Tenant、User、Agent、Policy、Grant、DataAPI和AuditOutbox表。
3. 实现Repository的PostgreSQL适配器和租户级约束。
4. 所有发布、授权和Agent数据调用写入审计Outbox。
5. 增加数据库集成测试、迁移测试和跨租户负向测试。

### Iteration 3：数据接入闭环

1. DataSource与SyncJob领域。
2. PostgreSQL连接器只读测试和Schema发现。
3. Worker任务、Checkpoint、Manifest及回调接口。
4. Dataset/DatasetVersion登记、质量基础规则和发布状态机。
5. Serving PostgreSQL查询适配器替换内存数据端口。

### Iteration 4：知识闭环

1. 文件上传、病毒扫描接口和DocumentVersion。
2. Parser/Chunk处理流水线。
3. Model Gateway和Embedding端口。
4. Milvus索引版本及Knowledge API。
5. 文档ACL预过滤、返回前复核和引用定位测试。

