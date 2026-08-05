# Agent Data OS V1.0 接口设计文档

> 文档版本：V1.0-API-1.0  
> 文档状态：接口评审基线  
> 上游文档：[Agent_Data_OS_PRD_SRS.md](./Agent_Data_OS_PRD_SRS.md)、[Agent_Data_OS_V1.0_Domain_Service_Design.md](./Agent_Data_OS_V1.0_Domain_Service_Design.md)  
> 适用范围：V1.0管理控制台API、Agent Data API、内部服务API、异步领域事件  
> 协议基线：HTTPS、REST/JSON、OpenAPI 3.1、JSON Schema 2020-12、OAuth 2.0/OIDC、W3C Trace Context

## 1. 文档目标与接口范围

### 1.1 目标

本文定义Agent Data OS V1.0各领域之间以及平台与外部调用方之间的接口契约，作为前端、后端、Agent SDK、测试、交付与第三方集成的共同基线。

接口设计必须保证：

- Agent只能通过Agent Data API获得数据，不能直连数据库、MinIO、Milvus或模型厂商。
- 租户、身份、用途、策略版本和链路标识贯穿全部数据请求。
- 外部契约不暴露物理数据库表名、连接信息、内部服务地址和敏感配置。
- 创建、发布、重试和状态变更接口具备幂等或乐观锁机制。
- API、事件Schema和错误码均可独立版本化并支持兼容性测试。
- 任何成功的数据调用都能通过`trace_id`还原身份、策略、数据版本、模型调用与审计事件。

### 1.2 接口类型

| 类型 | 路径/协议 | 调用方 | 主要用途 |
|---|---|---|---|
| 管理API | `/api/v1/**` | Web控制台、管理员SDK | 租户、接入、资产、知识、API、Agent、模型和审计管理 |
| Agent Data API | `/agent-data/v1/**` | 企业Agent、Workflow Agent | 受控结构化查询和知识检索 |
| 内部服务API | `/internal/v1/**` | 平台内部工作负载 | 身份解析、策略决策、任务回调、模型调用等 |
| 上传接口 | 预签名URL+管理API | Web/SDK/连接器 | 大文件分片上传，不经业务服务转发正文 |
| 领域事件 | Kafka+Schema Registry | 内部服务 | 状态传播、投影更新、审计与异步处理 |
| 运维接口 | `/health/**`、`/metrics` | Kubernetes、监控系统 | 健康检查与指标采集，不对普通用户开放 |

### 1.3 V1.0接口边界

- 对外提供Query API与Knowledge API。
- Insight API、Graph API仅保留类型枚举，不提供生产端点。
- 数据服务只读，不提供Agent数据写入接口。
- 不提供用户自由SQL端点。
- 不提供通用Agent运行或可视化编排接口。

## 2. API分区与网关路由

### 2.1 建议域名

| 用途 | 示例域名 | 暴露范围 |
|---|---|---|
| 管理控制台API | `https://ados.example.com/api/v1` | 企业用户网络 |
| Agent Data API | `https://data.ados.example.com/agent-data/v1` | 已登记Agent网络 |
| 文件上传 | `https://objects.ados.example.com` | 短期预签名URL |
| 内部服务API | `https://<service>.<namespace>.svc/internal/v1` | Kubernetes集群内部 |
| 运维接口 | Pod/Service内部地址 | 仅监控和编排系统 |

私有化部署允许使用统一域名和不同路径，但网关必须将管理流量、Agent流量和上传流量应用不同的认证、限流和WAF策略。

### 2.2 网关路由规则

```text
/api/v1/identity/**          → control-api / Identity模块
/api/v1/roles/**             → control-api / Policy模块
/api/v1/access-requests/**   → control-api / Policy模块
/api/v1/data-sources/**      → ingestion-api
/api/v1/sync-*/**            → ingestion-api
/api/v1/assets/**            → control-api / Catalog模块
/api/v1/datasets/**          → control-api / Catalog模块
/api/v1/knowledge-*/**       → knowledge-service
/api/v1/documents/**         → knowledge-service
/api/v1/data-apis/**         → query-service / Data API管理模块
/api/v1/agents/**            → control-api / Agent模块
/api/v1/model-*/**           → model-gateway管理面
/api/v1/audit/**             → audit-service
/agent-data/v1/query/**      → agent-data-gateway → query-service
/agent-data/v1/knowledge/**  → agent-data-gateway → knowledge-service
```

## 3. 通用协议规范

### 3.1 HTTP与内容类型

- 所有生产接口必须使用HTTPS，最低TLS 1.2。
- 请求与响应编码为UTF-8。
- JSON接口使用`Content-Type: application/json`。
- OpenAPI导出使用`application/yaml`或`application/json`。
- 文件上传使用预签名URL；业务API只传文件元数据。
- 禁止在URL查询参数中传Token、Secret、身份证号等敏感信息。

### 3.2 认证方式

| 调用方 | 认证方式 | Token建议有效期 | 补充控制 |
|---|---|---:|---|
| 管理控制台用户 | OIDC Authorization Code + PKCE | 15分钟 | MFA、SSO、刷新Token轮换 |
| Agent | OAuth2 Client Credentials或Token Exchange | ≤15分钟 | Agent Principal、Audience、Purpose、Scope |
| 内部服务 | 工作负载身份+mTLS | ≤10分钟 | ServiceAccount、NetworkPolicy |
| 上传客户端 | 用户Token申请预签名URL | URL≤15分钟 | 文件大小、MIME、对象路径绑定 |

### 3.3 通用请求头

| 请求头 | 外部调用 | 必填 | 说明 |
|---|---:|---:|---|
| `Authorization` | 是 | 是 | `Bearer <token>` |
| `X-Request-Id` | 可传 | 否 | 未传则网关生成ULID |
| `traceparent` | 可传 | 否 | W3C链路上下文，未传则生成 |
| `X-Purpose` | 数据类接口 | 是 | 已注册业务用途编码 |
| `Idempotency-Key` | 命令类接口 | 条件必填 | 24小时内同主体、同接口唯一 |
| `If-Match` | 更新/发布接口 | 条件必填 | 资源ETag或版本号，防止并发覆盖 |
| `Accept-Language` | 是 | 否 | `zh-CN`/`en-US`，默认`zh-CN` |
| `X-Tenant-Id` | 否 | 禁止信任 | 租户由Token解析并由网关注入内部上下文 |

内部服务上下文还包含`X-Actor-Type`、`X-Actor-Id`、`X-Delegated-User-Id`、`X-Environment`和签名。下游服务必须拒绝未经网关签名的身份上下文。

### 3.4 成功响应信封

单对象响应：

```json
{
  "request_id": "req_01J4Z5G6T7",
  "trace_id": "tr_01J4Z5G6T7",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "CRM生产库"
  },
  "meta": {
    "api_version": "v1",
    "served_at": "2026-08-04T10:30:00Z"
  }
}
```

创建接口返回`201 Created`并设置`Location`。异步任务创建返回`202 Accepted`，`data`包含任务ID和状态查询地址。

### 3.5 列表与游标分页

请求：

```http
GET /api/v1/assets?limit=20&cursor=eyJpZCI6Ii4uLiJ9&sort=-updated_at
```

响应：

```json
{
  "request_id": "req_01J...",
  "trace_id": "tr_01J...",
  "data": [
    {"id": "ds_001", "name": "客户主数据"}
  ],
  "page": {
    "limit": 20,
    "next_cursor": "eyJpZCI6ImRzXzAwMSJ9",
    "has_more": true
  }
}
```

分页约束：默认20，最大200；游标必须签名并绑定租户、过滤条件和排序；不返回精确总数时可提供`estimated_total`。

### 3.6 异步任务响应

```json
{
  "request_id": "req_01J...",
  "trace_id": "tr_01J...",
  "data": {
    "job_id": "job_01J...",
    "status": "QUEUED",
    "status_url": "/api/v1/jobs/job_01J...",
    "submitted_at": "2026-08-04T10:30:00Z"
  }
}
```

异步任务统一状态：`QUEUED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`CANCEL_REQUESTED`、`CANCELLED`、`QUARANTINED`。

### 3.7 错误响应

```json
{
  "request_id": "req_01J...",
  "trace_id": "tr_01J...",
  "error": {
    "code": "POLICY_DENIED",
    "message": "当前身份无权执行该操作",
    "details": [
      {"field": "purpose", "reason": "PURPOSE_NOT_ALLOWED"}
    ],
    "retryable": false,
    "documentation_url": "/docs/errors/POLICY_DENIED"
  }
}
```

错误响应不得包含SQL、物理表名、堆栈、内部地址、Token、Secret或未脱敏数据。

### 3.8 通用错误码

| HTTP | 错误码 | 说明 | 是否可重试 |
|---:|---|---|---:|
| 400 | `INVALID_ARGUMENT` | 参数格式或语义不合法 | 否 |
| 400 | `PURPOSE_REQUIRED` | 数据接口缺少业务用途 | 否 |
| 401 | `UNAUTHENTICATED` | Token缺失、无效或过期 | 重新认证 |
| 401 | `TOKEN_AUDIENCE_INVALID` | Token受众不匹配 | 否 |
| 403 | `POLICY_DENIED` | RBAC/ABAC/用途策略拒绝 | 否 |
| 403 | `DELEGATION_SCOPE_EXCEEDED` | Agent超出用户委托范围 | 否 |
| 404 | `RESOURCE_NOT_VISIBLE` | 资源不存在或不可见 | 否 |
| 409 | `VERSION_CONFLICT` | 乐观锁或版本冲突 | 获取新版本后重试 |
| 409 | `IDEMPOTENCY_CONFLICT` | 同一幂等键请求体不同 | 否 |
| 409 | `INVALID_STATE_TRANSITION` | 当前状态不允许该操作 | 否 |
| 413 | `PAYLOAD_TOO_LARGE` | 请求或文件超限 | 否 |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | 文件或内容类型不支持 | 否 |
| 422 | `QUALITY_BLOCKED` | 数据质量门禁阻断 | 修复数据后重试 |
| 422 | `SCHEMA_INCOMPATIBLE` | Schema不兼容 | 否 |
| 422 | `INSUFFICIENT_EVIDENCE` | 知识证据不足 | 可调整查询 |
| 429 | `RATE_LIMIT_EXCEEDED` | QPS超限 | 是，遵循Retry-After |
| 429 | `BUDGET_EXCEEDED` | Agent/模型预算超限 | 否/申请预算 |
| 500 | `INTERNAL_ERROR` | 未分类内部错误 | 视`retryable` |
| 502 | `UPSTREAM_BAD_RESPONSE` | 上游返回不符合契约 | 是 |
| 503 | `UPSTREAM_UNAVAILABLE` | 数据源、模型或存储不可用 | 是 |
| 503 | `POLICY_SERVICE_UNAVAILABLE` | 策略服务不可用，失败关闭 | 是 |
| 503 | `AUDIT_CHANNEL_UNAVAILABLE` | 敏感操作无法可靠审计 | 是 |
| 504 | `REQUEST_TIMEOUT` | 调用超时 | 是 |

### 3.9 幂等规范

- 创建同步运行、重试、发布、撤销、导出、Token交换等命令必须使用`Idempotency-Key`。
- 服务保存`tenant_id + actor_id + method + path + idempotency_key + request_hash`。
- 相同键和相同请求体返回首次结果；相同键但请求体不同返回`409 IDEMPOTENCY_CONFLICT`。
- 默认保留24小时；文件分片和长任务可保留7天。

### 3.10 乐观锁与ETag

获取可变资源时返回：

```http
ETag: "7"
```

更新请求必须包含：

```http
If-Match: "7"
```

服务更新成功后版本变为8；版本不一致返回`409 VERSION_CONFLICT`，禁止后写覆盖。

## 4. 管理API总览

### 4.1 租户、用户与服务主体

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/tenant` | `tenant:read` | 获取当前租户配置 |
| PATCH | `/api/v1/tenant` | `tenant:update` | 更新允许修改的租户配置 |
| GET | `/api/v1/users` | `user:list` | 用户列表 |
| POST | `/api/v1/users` | `user:create` | 创建/邀请用户 |
| GET | `/api/v1/users/{user_id}` | `user:read` | 用户详情 |
| PATCH | `/api/v1/users/{user_id}` | `user:update` | 更新部门和属性 |
| PATCH | `/api/v1/users/{user_id}/status` | `user:status` | 锁定、启用、停用 |
| GET | `/api/v1/service-principals` | `principal:list` | 服务主体列表 |
| POST | `/api/v1/service-principals` | `principal:create` | 创建服务主体 |
| POST | `/api/v1/service-principals/{id}/rotate` | `principal:rotate` | 轮换凭据，Secret只返回一次 |
| DELETE | `/api/v1/service-principals/{id}/credentials/{credential_id}` | `principal:revoke` | 吊销凭据 |

#### 创建用户

```http
POST /api/v1/users
Authorization: Bearer <token>
Idempotency-Key: 6d9407bc-1b5e-4ddf-a562-64f59cb79118
Content-Type: application/json
```

```json
{
  "external_subject": "idp|zhangsan",
  "username": "zhangsan",
  "display_name": "张三",
  "email": "zhangsan@example.com",
  "department_id": "dept_sales_east",
  "attributes": {
    "job_code": "sales_manager",
    "region": "EAST"
  },
  "role_ids": ["role_business_user"]
}
```

响应中的邮箱根据调用者权限动态脱敏；创建用户不返回本地密码。

### 4.2 角色、权限与访问申请

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/roles` | `role:list` | 角色列表 |
| POST | `/api/v1/roles` | `role:create` | 创建自定义角色 |
| GET | `/api/v1/roles/{role_id}` | `role:read` | 角色详情与权限摘要 |
| PATCH | `/api/v1/roles/{role_id}` | `role:update` | 更新角色，需If-Match |
| POST | `/api/v1/roles/{role_id}/permissions` | `role:grant` | 绑定权限 |
| DELETE | `/api/v1/roles/{role_id}/permissions/{permission_id}` | `role:revoke` | 移除权限 |
| GET | `/api/v1/policies` | `policy:list` | 策略列表 |
| POST | `/api/v1/policies` | `policy:create` | 创建策略草稿 |
| POST | `/api/v1/policies/{policy_id}/simulate` | `policy:simulate` | 使用样例上下文模拟 |
| POST | `/api/v1/policies/{policy_id}/publish` | `policy:publish` | 发布策略版本 |
| POST | `/api/v1/access-requests` | 已认证主体 | 发起访问申请 |
| GET | `/api/v1/access-requests` | `access_request:list` | 按范围查询申请 |
| POST | `/api/v1/access-requests/{id}/approve` | `access_request:approve` | 审批通过 |
| POST | `/api/v1/access-requests/{id}/reject` | `access_request:approve` | 驳回 |
| POST | `/api/v1/grants/{grant_id}/revoke` | `grant:revoke` | 提前回收授权 |

#### 创建访问申请

```json
{
  "subject": {
    "type": "AGENT_VERSION",
    "id": "agent_version_sales_1_2_0"
  },
  "resource": {
    "type": "DATA_API_VERSION",
    "id": "api_receivable_v1"
  },
  "actions": ["INVOKE"],
  "purpose": "sales_risk_followup",
  "environment": "PROD",
  "requested_obligations": {
    "max_rows": 20,
    "allow_export": false
  },
  "valid_from": "2026-08-05T00:00:00Z",
  "valid_to": "2026-11-05T00:00:00Z",
  "reason": "销售回款风险助手生产上线"
}
```

审批请求：

```json
{
  "decision": "APPROVE",
  "comment": "限定华东区域和20行返回",
  "obligations": {
    "row_filters": [{"field": "region", "op": "eq", "value_from": "subject.region"}],
    "max_rows": 20,
    "allow_export": false
  }
}
```

### 4.3 数据源与连接器

| 方法 | 路径 | 权限 | 异步/幂等 | 说明 |
|---|---|---|---|---|
| GET | `/api/v1/connectors` | `connector:list` | 否 | 支持的连接器和参数Schema |
| GET | `/api/v1/data-sources` | `datasource:list` | 否 | 数据源列表 |
| POST | `/api/v1/data-sources` | `datasource:create` | 幂等 | 创建数据源 |
| GET | `/api/v1/data-sources/{id}` | `datasource:read` | 否 | 详情，不返回Secret |
| PATCH | `/api/v1/data-sources/{id}` | `datasource:update` | If-Match | 更新非Secret配置 |
| POST | `/api/v1/data-sources/{id}/credentials` | `datasource:credential` | 幂等 | 创建/替换Secret引用 |
| POST | `/api/v1/data-sources/{id}/test` | `datasource:test` | 异步+幂等 | 网络、TLS、认证和只读权限测试 |
| POST | `/api/v1/data-sources/{id}/discover` | `datasource:discover` | 异步+幂等 | 发现Schema |
| GET | `/api/v1/data-sources/{id}/discoveries/{job_id}` | `datasource:read` | 否 | 获取发现结果 |
| PATCH | `/api/v1/data-sources/{id}/status` | `datasource:status` | If-Match | 启用、暂停、归档 |

#### 创建数据库数据源

```json
{
  "name": "CRM生产只读库",
  "source_type": "POSTGRESQL",
  "connector_version": "postgresql-1.0",
  "connection": {
    "host": "crm-db.internal",
    "port": 5432,
    "database": "crm",
    "tls_mode": "VERIFY_FULL",
    "network_zone": "enterprise-data-zone"
  },
  "credential": {
    "secret_ref": "vault://ados/tenant001/datasource/crm-ro"
  },
  "owner_id": "user_data_admin",
  "description": "CRM客户与商机数据，只读账号"
}
```

数据源详情只能返回`credential_status`、`last_rotated_at`和Secret引用的不可逆别名，不能返回用户名或密码明文。

### 4.4 同步任务与运行

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/sync-jobs` | `sync_job:list` | 同步任务列表 |
| POST | `/api/v1/sync-jobs` | `sync_job:create` | 创建任务 |
| GET | `/api/v1/sync-jobs/{id}` | `sync_job:read` | 任务配置和当前状态 |
| PATCH | `/api/v1/sync-jobs/{id}` | `sync_job:update` | 更新草稿或暂停任务 |
| POST | `/api/v1/sync-jobs/{id}/runs` | `sync_job:execute` | 启动运行，必须幂等 |
| GET | `/api/v1/sync-jobs/{id}/runs` | `sync_run:list` | 运行历史 |
| GET | `/api/v1/sync-runs/{run_id}` | `sync_run:read` | 运行详情、统计和错误摘要 |
| POST | `/api/v1/sync-runs/{run_id}/retry` | `sync_job:execute` | 从Checkpoint重试 |
| POST | `/api/v1/sync-runs/{run_id}/cancel` | `sync_job:execute` | 请求取消 |
| GET | `/api/v1/sync-runs/{run_id}/logs` | `sync_run:logs` | 脱敏后的结构化运行日志 |

#### 创建同步任务

```json
{
  "name": "CRM客户每日同步",
  "data_source_id": "ds_source_crm",
  "source_objects": [
    {
      "schema": "public",
      "object": "customers",
      "columns": ["id", "name", "region", "owner_id", "updated_at"],
      "primary_key": ["id"]
    }
  ],
  "sync_mode": "INCREMENTAL_TIMESTAMP",
  "incremental": {
    "column": "updated_at",
    "lookback_seconds": 300
  },
  "schedule": {
    "type": "CRON",
    "expression": "0 1 * * *",
    "timezone": "Asia/Shanghai"
  },
  "source_limits": {
    "fetch_size": 5000,
    "max_parallelism": 2,
    "query_timeout_seconds": 300
  },
  "target": {
    "logical_dataset_name": "crm.customers"
  }
}
```

### 4.5 文件上传

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/v1/files/uploads` | `file:upload` | 创建上传会话 |
| GET | `/api/v1/files/uploads/{upload_id}` | `file:upload` | 获取上传状态 |
| POST | `/api/v1/files/uploads/{upload_id}/parts` | `file:upload` | 获取分片预签名URL |
| POST | `/api/v1/files/uploads/{upload_id}/complete` | `file:upload` | 提交分片清单并完成 |
| DELETE | `/api/v1/files/uploads/{upload_id}` | `file:upload` | 取消上传会话 |

创建上传会话：

```json
{
  "file_name": "销售回款管理制度.pdf",
  "size_bytes": 8450012,
  "mime_type": "application/pdf",
  "sha256": "17f6e1...",
  "classification_hint": "INTERNAL",
  "source_acl": {
    "departments": ["sales", "finance"]
  }
}
```

服务端根据租户、文件大小和MIME创建固定对象路径；客户端不得指定Bucket或对象存储绝对路径。

### 4.6 数据资产、质量与血缘

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/assets` | `asset:list` | 权限裁剪后的统一资产搜索 |
| GET | `/api/v1/assets/{asset_id}` | `asset:read` | 统一资产详情 |
| GET | `/api/v1/datasets/{dataset_id}` | `dataset:read` | 数据集详情 |
| PATCH | `/api/v1/datasets/{dataset_id}` | `dataset:update` | 维护业务元数据 |
| GET | `/api/v1/datasets/{dataset_id}/versions` | `dataset:read` | Schema和数据版本列表 |
| POST | `/api/v1/datasets/{dataset_id}/certify` | `dataset:certify` | 提交认证 |
| POST | `/api/v1/datasets/{dataset_id}/publish` | `dataset:publish` | 发布当前认证版本 |
| POST | `/api/v1/datasets/{dataset_id}/deprecate` | `dataset:publish` | 弃用并设置兼容期 |
| GET | `/api/v1/quality-rules` | `quality:list` | 质量规则列表 |
| POST | `/api/v1/quality-rules` | `quality:create` | 创建质量规则 |
| POST | `/api/v1/quality-rules/{id}/test` | `quality:test` | 规则试运行 |
| GET | `/api/v1/quality-runs` | `quality:list` | 质量执行结果 |
| GET | `/api/v1/lineage` | `lineage:read` | 上下游血缘和影响分析 |

资产搜索参数：`q`、`asset_type`、`business_domain`、`classification`、`owner_id`、`tags`、`status`、`sort`、`cursor`、`limit`。搜索结果必须先通过Policy批量裁剪。

#### 发布数据集

```json
{
  "dataset_version": 12,
  "certification_id": "cert_01J...",
  "effective_at": "2026-08-05T00:00:00Z",
  "change_summary": "新增客户区域字段并完成敏感分级",
  "approval_ticket": "APR-2026-0804-001"
}
```

### 4.7 知识库、文档与索引

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/knowledge-bases` | `knowledge_base:list` | 知识库列表 |
| POST | `/api/v1/knowledge-bases` | `knowledge_base:create` | 创建知识库 |
| GET | `/api/v1/knowledge-bases/{id}` | `knowledge_base:read` | 详情和活动索引版本 |
| PATCH | `/api/v1/knowledge-bases/{id}` | `knowledge_base:update` | 更新草稿检索配置 |
| POST | `/api/v1/knowledge-bases/{id}/documents` | `knowledge_base:update` | 关联文档版本 |
| DELETE | `/api/v1/knowledge-bases/{id}/documents/{document_id}` | `knowledge_base:update` | 从知识库撤销文档 |
| GET | `/api/v1/documents/{document_id}` | `document:read` | 文档元数据和处理状态 |
| GET | `/api/v1/documents/{document_id}/versions` | `document:read` | 文档版本列表 |
| GET | `/api/v1/documents/{document_id}/parse-preview` | `document:preview` | 权限控制的解析预览 |
| DELETE | `/api/v1/documents/{document_id}` | `document:revoke` | 撤销文档并异步清理 |
| POST | `/api/v1/knowledge-bases/{id}/index-runs` | `index:build` | 构建候选索引 |
| GET | `/api/v1/index-runs/{run_id}` | `index:read` | 构建进度和评测摘要 |
| POST | `/api/v1/index-versions/{id}/publish` | `index:publish` | 原子切换活动索引 |
| POST | `/api/v1/knowledge-bases/{id}/test-retrieval` | `knowledge_base:test` | 管理员检索测试 |

#### 创建知识库

```json
{
  "code": "kb_sales_policy",
  "name": "销售制度知识库",
  "owner_id": "user_sales_steward",
  "classification": "INTERNAL",
  "retrieval_config": {
    "mode": "HYBRID",
    "dense_weight": 0.7,
    "sparse_weight": 0.3,
    "top_k": 8,
    "rerank": true,
    "minimum_score": 0.65
  },
  "chunk_strategy": {
    "type": "HEADING_AWARE",
    "max_tokens": 600,
    "overlap_tokens": 80
  },
  "embedding_model_id": "model_embedding_default"
}
```

#### 构建索引

```json
{
  "document_versions": [
    {"document_id": "doc_1008", "version": 6}
  ],
  "base_index_version": 9,
  "evaluation_suite_id": "eval_sales_policy_v2",
  "publish_on_success": false
}
```

### 4.8 Data API管理

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/data-apis` | `data_api:list` | Data API目录 |
| POST | `/api/v1/data-apis` | `data_api:create` | 创建API主体 |
| GET | `/api/v1/data-apis/{id}` | `data_api:read` | API详情 |
| POST | `/api/v1/data-apis/{id}/versions` | `data_api:update` | 创建不可变版本 |
| GET | `/api/v1/api-versions/{id}` | `data_api:read` | 版本契约与测试状态 |
| POST | `/api/v1/api-versions/{id}/test` | `data_api:test` | 启动契约、安全、性能测试 |
| POST | `/api/v1/api-versions/{id}/submit` | `data_api:submit` | 提交发布审批 |
| POST | `/api/v1/api-versions/{id}/publish` | `data_api:publish` | 发布到指定环境 |
| POST | `/api/v1/data-apis/{id}/suspend` | `data_api:suspend` | 紧急停用全部或指定版本 |
| POST | `/api/v1/data-apis/{id}/deprecate` | `data_api:publish` | 设置弃用计划 |
| GET | `/api/v1/data-apis/{id}/openapi` | `data_api:read` | 导出机器可读契约 |
| GET | `/api/v1/data-apis/{id}/tool-schema` | `data_api:read` | 导出Agent Tool JSON Schema |

#### 创建Query API版本

```json
{
  "semantic_version": "1.0.0",
  "type": "QUERY",
  "description": "查询客户逾期应收数据",
  "resource_bindings": [
    {"dataset_id": "dataset_receivable", "minimum_version": 12}
  ],
  "purpose_allowlist": ["sales_risk_followup", "management_review"],
  "query_template": {
    "dimensions": ["customer_name", "region", "currency"],
    "metrics": ["overdue_amount"],
    "allowed_filters": {
      "region": ["eq", "in"],
      "overdue_days": ["gte", "lte"]
    },
    "allowed_order_fields": ["overdue_amount", "overdue_days"],
    "default_limit": 20,
    "maximum_limit": 100,
    "timeout_seconds": 5
  },
  "output_schema": {
    "type": "object",
    "required": ["customer_name", "overdue_amount", "currency"],
    "properties": {
      "customer_name": {"type": "string"},
      "overdue_amount": {"type": "number"},
      "currency": {"type": "string"}
    }
  },
  "rate_limit": {"requests_per_minute": 60, "burst": 10}
}
```

### 4.9 Agent管理

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/agents` | `agent:list` | Agent列表 |
| POST | `/api/v1/agents` | `agent:create` | 注册Agent |
| GET | `/api/v1/agents/{id}` | `agent:read` | Agent详情 |
| PATCH | `/api/v1/agents/{id}` | `agent:update` | 更新Owner等主体信息 |
| POST | `/api/v1/agents/{id}/versions` | `agent:update` | 创建不可变版本 |
| GET | `/api/v1/agent-versions/{id}` | `agent:read` | 版本详情 |
| POST | `/api/v1/agent-versions/{id}/tool-bindings` | `agent:tool_bind` | 绑定Data API工具 |
| DELETE | `/api/v1/agent-versions/{id}/tool-bindings/{binding_id}` | `agent:tool_bind` | 移除工具 |
| POST | `/api/v1/agent-versions/{id}/submit` | `agent:submit` | 提交发布审批 |
| POST | `/api/v1/agent-versions/{id}/publish` | `agent:publish` | 发布版本 |
| POST | `/api/v1/agents/{id}/suspend` | `agent:suspend` | Kill Switch |
| POST | `/api/v1/agents/{id}/resume` | `agent:suspend` | 安全复核后恢复 |
| GET | `/api/v1/agents/{id}/usage` | `agent:usage` | 调用量、Token和成本 |

#### 注册Agent

```json
{
  "code": "sales_risk_agent",
  "name": "销售回款风险Agent",
  "agent_type": "SPECIALIST",
  "owner_id": "user_agent_owner",
  "purpose": "sales_risk_followup",
  "risk_level": "MEDIUM",
  "environments": ["DEV", "TEST"],
  "budget_policy": {
    "daily_api_calls": 5000,
    "monthly_model_cost_cny": 3000,
    "on_exceeded": "BLOCK"
  },
  "support_contact": "销售数字化团队"
}
```

### 4.10 模型管理与用量

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/model-providers` | `model:list` | Provider列表，不返回密钥 |
| POST | `/api/v1/model-providers` | `model:manage` | 注册DeepSeek Provider配置 |
| POST | `/api/v1/model-providers/{id}/credentials` | `model:credential` | 更新Secret引用 |
| GET | `/api/v1/model-deployments` | `model:list` | 模型部署列表 |
| POST | `/api/v1/model-deployments` | `model:manage` | 注册模型能力与限制 |
| POST | `/api/v1/model-deployments/{id}/test` | `model:test` | 连接、Schema和DLP测试 |
| GET | `/api/v1/model-routes` | `model:list` | 路由规则 |
| POST | `/api/v1/model-routes` | `model:route_manage` | 创建路由草稿 |
| POST | `/api/v1/model-routes/{id}/publish` | `model:route_publish` | 发布路由 |
| GET | `/api/v1/model-usage` | `model:usage` | Token、成本、延迟与错误统计 |
| GET | `/api/v1/model-budgets` | `model:budget` | 预算列表 |
| PATCH | `/api/v1/model-budgets/{id}` | `model:budget_manage` | 更新预算和阈值 |

用量查询支持`from`、`to`、`group_by=tenant|department|agent|model|task`、`agent_id`、`model_id`和`environment`。

### 4.11 审计与安全事件

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/audit/events` | `audit:read` | 审计事件查询 |
| GET | `/api/v1/audit/events/{event_id}` | `audit:read` | 单事件详情 |
| GET | `/api/v1/audit/traces/{trace_id}` | `audit:trace` | 重建完整调用链 |
| POST | `/api/v1/audit/exports` | `audit:export` | 创建签名导出任务 |
| GET | `/api/v1/audit/exports/{job_id}` | `audit:export` | 导出状态及短期下载地址 |
| GET | `/api/v1/security-events` | `security_event:list` | 安全事件列表 |
| GET | `/api/v1/security-events/{id}` | `security_event:read` | 事件证据和处置记录 |
| POST | `/api/v1/security-events/{id}/triage` | `security_event:manage` | 分级和指派 |
| POST | `/api/v1/security-events/{id}/contain` | `security_event:contain` | 隔离Agent/API/模型出口等 |
| POST | `/api/v1/security-events/{id}/resolve` | `security_event:manage` | 解决并记录结论 |

审计查询不支持模糊搜索请求正文；默认只返回摘要。读取受保护的调试证据需要单独审批并产生新的审计事件。

## 5. Agent Data API详细契约

### 5.1 通用调用要求

所有Agent Data API请求必须：

- 使用Agent Principal签发的短期Token。
- Token `aud`包含`agent-data-gateway`。
- 携带已注册`X-Purpose`，且与Token中的purpose一致。
- 用户触发任务携带有效`delegated_user`；后台任务绑定批准的服务用途。
- 携带`traceparent`或接受网关生成的新链路。
- 遵守API版本、QPS、并发、结果行数、Token和费用预算。

### 5.2 Query API

#### 请求

```http
POST /agent-data/v1/query/customer_receivable_query
Authorization: Bearer <agent_token>
X-Purpose: sales_risk_followup
X-Request-Id: req_01J4Z...
Content-Type: application/json
```

```json
{
  "api_version": "1.0.0",
  "select": ["customer_name", "region", "overdue_amount", "currency"],
  "filters": [
    {"field": "overdue_days", "op": "gte", "value": 30}
  ],
  "order_by": [
    {"field": "overdue_amount", "direction": "desc"}
  ],
  "limit": 20,
  "cursor": null,
  "context": {
    "task_id": "task_01J4Z...",
    "parent_span_id": "span_01J4Z..."
  }
}
```

调用方不能传入物理数据集名称、SQL、租户、行级安全条件或脱敏策略。

#### 响应

```json
{
  "request_id": "req_01J4Z...",
  "trace_id": "tr_01J4Z...",
  "data": {
    "schema": [
      {"name": "customer_name", "type": "string", "masked": false},
      {"name": "region", "type": "string", "masked": false},
      {"name": "overdue_amount", "type": "decimal", "masked": false},
      {"name": "currency", "type": "string", "masked": false}
    ],
    "rows": [
      {
        "customer_name": "华东某客户",
        "region": "EAST",
        "overdue_amount": "320000.00",
        "currency": "CNY"
      }
    ],
    "next_cursor": null
  },
  "freshness": {
    "dataset_version": 12,
    "as_of": "2026-08-04T01:00:00Z",
    "sla": "PT24H",
    "status": "FRESH"
  },
  "quality": {
    "score": 96.0,
    "status": "PASS",
    "warnings": []
  },
  "policy": {
    "decision_id": "pd_01J4Z...",
    "policy_version": 38,
    "masked_fields": [],
    "result_limit_applied": 20
  },
  "meta": {
    "api_code": "customer_receivable_query",
    "api_version": "1.0.0",
    "duration_ms": 183,
    "truncated": false
  }
}
```

金额使用JSON字符串或明确decimal格式，避免二进制浮点误差。日期、时间、货币和枚举必须在API Schema中定义。

#### Query字段操作符

| 类型 | 允许操作符 |
|---|---|
| string | `eq`、`neq`、`in`、`starts_with`；`contains`需API显式批准 |
| number/decimal | `eq`、`neq`、`gt`、`gte`、`lt`、`lte`、`between` |
| date/datetime | `eq`、`before`、`after`、`between` |
| boolean | `eq` |
| enum | `eq`、`in` |

字段是否允许某操作符以已发布API版本为准。V1.0不支持正则、任意表达式、子查询和调用函数。

#### Query专用错误码

| HTTP | 错误码 | 说明 |
|---:|---|---|
| 400 | `FIELD_NOT_SELECTABLE` | 请求了未发布字段 |
| 400 | `FILTER_NOT_ALLOWED` | 字段或操作符未授权 |
| 400 | `ORDER_NOT_ALLOWED` | 排序字段未授权 |
| 403 | `ROW_SCOPE_DENIED` | 行级范围与委托不匹配 |
| 409 | `DATASET_VERSION_UNAVAILABLE` | API绑定版本不可用 |
| 422 | `QUERY_COST_EXCEEDED` | 预计扫描量或复杂度超限 |
| 422 | `DATA_QUALITY_BLOCKED` | 当前数据版本质量不满足调用要求 |
| 504 | `QUERY_TIMEOUT` | 查询超过API定义的超时 |

### 5.3 Knowledge API

#### 请求

```http
POST /agent-data/v1/knowledge/sales_policy_knowledge
Authorization: Bearer <agent_token>
X-Purpose: sales_risk_followup
Content-Type: application/json
```

```json
{
  "api_version": "1.0.0",
  "query": "华东区大客户逾期超过30天时应如何升级？",
  "retrieval": {
    "top_k": 8,
    "mode": "HYBRID",
    "rerank": true
  },
  "filters": {
    "effective_at": "2026-08-04",
    "document_types": ["POLICY"]
  },
  "generate_answer": true,
  "response_language": "zh-CN",
  "context": {
    "task_id": "task_01J4Z..."
  }
}
```

`top_k`不能超过API发布配置；客户端不能指定Embedding模型、Milvus Collection、系统Prompt或绕过ACL的过滤条件。

#### 响应

```json
{
  "request_id": "req_02J4Z...",
  "trace_id": "tr_02J4Z...",
  "data": {
    "answer": "逾期超过30天且达到A级金额阈值时，应提交区域财务复核。",
    "sufficient_evidence": true,
    "evidence": [
      {
        "citation_id": "cit_01",
        "document_id": "doc_1008",
        "document_version": 6,
        "title": "销售回款管理制度",
        "page": 12,
        "section": "4.3 逾期升级",
        "snippet": "……",
        "score": 0.91,
        "effective_from": "2026-01-01"
      }
    ]
  },
  "retrieval": {
    "knowledge_base_id": "kb_sales_policy",
    "index_version": 10,
    "candidate_count": 36,
    "authorized_count": 8,
    "returned_count": 1,
    "duration_ms": 245
  },
  "model": {
    "generated": true,
    "deployment_id": "deepseek_generation_default",
    "usage": {
      "input_tokens": 1532,
      "output_tokens": 96
    }
  },
  "policy": {
    "decision_id": "pd_02J4Z...",
    "policy_version": 38
  }
}
```

若证据不足，HTTP仍可返回200，但必须满足：

```json
{
  "data": {
    "answer": null,
    "sufficient_evidence": false,
    "evidence": []
  },
  "warnings": [
    {"code": "INSUFFICIENT_EVIDENCE", "message": "未检索到足够的授权证据"}
  ]
}
```

`422 INSUFFICIENT_EVIDENCE`仅用于调用方要求`fail_on_insufficient_evidence=true`的场景。

#### Knowledge专用错误码

| HTTP | 错误码 | 说明 |
|---:|---|---|
| 400 | `RETRIEVAL_OPTION_NOT_ALLOWED` | 请求覆盖了禁止修改的检索参数 |
| 403 | `KNOWLEDGE_SCOPE_DENIED` | 无知识库或文档范围权限 |
| 409 | `INDEX_VERSION_UNAVAILABLE` | 活动索引不可用或正在切换 |
| 422 | `PROMPT_INJECTION_BLOCKED` | 输入或上下文被安全策略阻断 |
| 422 | `MODEL_EGRESS_BLOCKED` | 当前数据分级禁止外部模型生成 |
| 503 | `RETRIEVAL_UNAVAILABLE` | 检索服务不可用 |
| 503 | `GENERATION_UNAVAILABLE` | 生成模型不可用；可按API配置降级到纯证据 |

### 5.4 Agent Data API响应缓存

- Query和Knowledge默认不使用跨主体公共缓存。
- 缓存键必须包含tenant、Agent版本、委托用户、purpose、API版本、策略版本、数据/索引版本和规范化请求哈希。
- 含高度敏感数据的结果禁止缓存。
- 权限撤销、API停用、数据分级提高、数据/索引版本切换必须主动失效。
- 响应通过`Cache-Control: no-store`告知Agent客户端不得持久缓存，除非API明确授权。

## 6. 内部服务API

### 6.1 身份解析

```http
POST /internal/v1/identity/resolve
```

```json
{
  "token_reference": "gateway_verified_token_hash",
  "requested_audience": "agent-data-gateway",
  "request_context": {
    "source_ip": "10.10.1.8",
    "device_id": null,
    "environment": "PROD"
  }
}
```

```json
{
  "principal": {
    "tenant_id": "tenant_001",
    "actor_type": "AGENT",
    "actor_id": "agent_principal_1024",
    "agent_id": "sales_risk_agent",
    "agent_version": "1.2.0",
    "delegated_user_id": "user_9001",
    "attributes": {
      "department": "sales",
      "region": "EAST"
    }
  },
  "purpose": "sales_risk_followup",
  "scope": ["api:receivable.query"],
  "expires_at": "2026-08-04T11:00:00Z",
  "revocation_version": 19
}
```

内部接口不传递原始Bearer Token；Token验证应在边界网关完成，或通过标准Token Introspection安全调用。

### 6.2 委托Token交换

```http
POST /internal/v1/tokens/exchange
Idempotency-Key: <uuid>
```

```json
{
  "subject_token_ref": "verified_user_session_ref",
  "agent_id": "sales_risk_agent",
  "agent_version": "1.2.0",
  "audience": ["agent-data-gateway"],
  "requested_scope": ["api:receivable.query"],
  "purpose": "sales_risk_followup",
  "parent_task_id": "task_01J...",
  "requested_ttl_seconds": 600,
  "max_calls": 20
}
```

返回的Token TTL、Scope和最大调用数只能小于或等于请求值。

### 6.3 策略决策

```http
POST /internal/v1/policy/decisions
```

```json
{
  "subject": {
    "tenant_id": "tenant_001",
    "actor_type": "AGENT",
    "actor_id": "agent_principal_1024",
    "agent_id": "sales_risk_agent",
    "agent_version": "1.2.0",
    "delegated_user_id": "user_9001",
    "attributes": {"department": "sales", "region": "EAST"}
  },
  "resource": {
    "type": "DATA_API_VERSION",
    "id": "api_receivable_v1",
    "attributes": {
      "classification": "SENSITIVE",
      "business_domain": "finance"
    }
  },
  "action": "INVOKE",
  "context": {
    "purpose": "sales_risk_followup",
    "environment": "PROD",
    "request_time": "2026-08-04T10:30:00Z",
    "source_network": "CORPORATE"
  }
}
```

```json
{
  "decision_id": "pd_01J...",
  "effect": "ALLOW_WITH_OBLIGATIONS",
  "policy_version": 38,
  "obligations": {
    "row_filters": [
      {"field": "region", "op": "eq", "value": "EAST", "immutable": true}
    ],
    "field_masks": [
      {"field": "contact_phone", "strategy": "KEEP_LAST_4"}
    ],
    "max_rows": 20,
    "allow_export": false,
    "model_egress_level": "INTERNAL_ONLY"
  },
  "reason_codes": ["ROLE_ALLOWED", "REGION_RESTRICTED"],
  "expires_at": "2026-08-04T10:31:00Z"
}
```

批量决策接口`POST /internal/v1/policy/batch-decisions`最多接收200个资源，并对每个资源返回独立决策；部分允许不代表全部允许。

### 6.4 Catalog发现登记

```http
POST /internal/v1/catalog/discoveries
Idempotency-Key: <run_id>
```

```json
{
  "data_source_id": "source_crm",
  "discovery_run_id": "run_01J...",
  "connector_version": "postgresql-1.0",
  "objects": [
    {
      "source_qualified_name": "public.customers",
      "object_type": "TABLE",
      "schema": {
        "columns": [
          {"name": "id", "source_type": "uuid", "nullable": false},
          {"name": "name", "source_type": "varchar", "nullable": false},
          {"name": "updated_at", "source_type": "timestamptz", "nullable": false}
        ],
        "primary_key": ["id"]
      },
      "estimated_rows": 120000,
      "schema_fingerprint": "sha256:..."
    }
  ]
}
```

Catalog返回已创建或匹配的数据集ID。重复提交相同发现运行必须返回相同映射。

### 6.5 Ingestion Worker回调

```http
POST /internal/v1/ingestion/runs/{run_id}/callbacks
Idempotency-Key: <run_id>-<sequence>
```

```json
{
  "sequence": 18,
  "status": "VALIDATING",
  "progress": {
    "completed_partitions": 17,
    "total_partitions": 20,
    "rows_read": 850000,
    "rows_written": 849998,
    "bytes_written": 82000412
  },
  "checkpoint": {
    "type": "TIMESTAMP",
    "value": "2026-08-04T01:00:00Z"
  },
  "output_manifest_ref": "minio://internal-ref/manifests/run_01J.json",
  "warnings": [
    {"code": "ROW_REJECTED", "count": 2}
  ]
}
```

回调只接受状态单向推进；旧`sequence`返回200并标记`ignored=true`，不重复处理。

### 6.6 Knowledge内部检索

```http
POST /internal/v1/knowledge/retrieve
```

```json
{
  "api_version_id": "api_sales_policy_v1",
  "identity_context_ref": "ctx_signed_01J...",
  "policy_decision_id": "pd_02J...",
  "query": "逾期升级规则",
  "retrieval": {"top_k": 8, "mode": "HYBRID", "rerank": true},
  "filters": {"effective_at": "2026-08-04"},
  "generate_answer": false
}
```

Knowledge Service必须根据`decision_id`获取或验证决策内容，不接受调用方自行构造ACL Token。

### 6.7 模型生成调用

```http
POST /internal/v1/models/invoke
```

```json
{
  "task_type": "GENERATION",
  "tenant_id": "tenant_001",
  "agent_id": "sales_risk_agent",
  "purpose": "sales_risk_followup",
  "data_classification": "INTERNAL",
  "route_hint": "knowledge_answer",
  "messages": [
    {"role": "system", "content": "根据授权证据回答；证据不足时不得推测。"},
    {"role": "user", "content": "华东区客户逾期时如何升级？"},
    {
      "role": "tool",
      "content": "<evidence id=\"cit_01\">……</evidence>",
      "trust_level": "UNTRUSTED_DATA"
    }
  ],
  "response_schema": {
    "type": "object",
    "required": ["answer", "citation_ids"],
    "properties": {
      "answer": {"type": "string"},
      "citation_ids": {"type": "array", "items": {"type": "string"}}
    }
  },
  "limits": {"max_output_tokens": 500, "timeout_seconds": 20},
  "trace_id": "tr_02J..."
}
```

响应：

```json
{
  "invocation_id": "mi_01J...",
  "deployment_id": "deepseek_generation_default",
  "output": {
    "answer": "……",
    "citation_ids": ["cit_01"]
  },
  "usage": {
    "input_tokens": 1532,
    "output_tokens": 96,
    "estimated_cost": {"amount": "0.018", "currency": "CNY"}
  },
  "security": {
    "dlp_action": "ALLOW",
    "masked_entity_count": 0,
    "response_validation": "PASS"
  }
}
```

### 6.8 Embedding调用

`POST /internal/v1/models/embeddings`单批最多128个输入或按Token上限取较小值。每项必须携带`content_hash`，返回顺序与输入一致。相同模型版本和内容哈希应支持去重。

```json
{
  "deployment_id": "deepseek_embedding_default",
  "data_classification": "INTERNAL",
  "items": [
    {"id": "chunk_001", "content_hash": "sha256:...", "text": "……"}
  ]
}
```

```json
{
  "model_version": "embedding-model-version",
  "dimension": 1024,
  "items": [
    {"id": "chunk_001", "content_hash": "sha256:...", "vector": [0.012, -0.034]}
  ],
  "usage": {"input_tokens": 382}
}
```

### 6.9 审计事件写入

低吞吐管理事件可调用：

```http
POST /internal/v1/audit/events
```

```json
{
  "event_id": "audit_01J...",
  "tenant_id": "tenant_001",
  "trace_id": "tr_01J...",
  "actor": {
    "type": "USER",
    "id": "user_001",
    "delegated_user_id": null
  },
  "action": "DATA_API_PUBLISH",
  "resource": {
    "type": "DATA_API_VERSION",
    "id": "api_receivable_v1"
  },
  "purpose": "platform_administration",
  "policy_decision_id": "pd_01J...",
  "request_digest": "sha256:...",
  "result": {"status": "SUCCESS", "count": 1},
  "security_labels": ["INTERNAL"],
  "occurred_at": "2026-08-04T10:30:00Z"
}
```

高吞吐运行事件使用Kafka，结构保持一致。审计接口拒绝正文、Secret和超过长度限制的自由文本字段。

## 7. 领域事件接口

### 7.1 事件信封

```json
{
  "event_id": "evt_01J...",
  "event_type": "catalog.dataset.published.v1",
  "event_version": 1,
  "tenant_id": "tenant_001",
  "aggregate_type": "Dataset",
  "aggregate_id": "dataset_receivable",
  "aggregate_version": 12,
  "occurred_at": "2026-08-04T10:30:00Z",
  "producer": "catalog-service",
  "trace_id": "tr_01J...",
  "actor": {"type": "USER", "id": "user_data_owner"},
  "data_classification": "INTERNAL",
  "payload": {}
}
```

### 7.2 Topic规划

| Topic | 生产者 | 主要消费者 |
|---|---|---|
| `ados.identity.events.v1` | Identity | Policy、Gateway、Agent、Audit |
| `ados.policy.events.v1` | Policy | Gateway、Data、Knowledge、Model、Audit |
| `ados.ingestion.events.v1` | Ingestion | Catalog、Knowledge、Audit、Platform |
| `ados.catalog.events.v1` | Catalog | Data、Policy、Audit |
| `ados.knowledge.events.v1` | Knowledge | Data、Audit、Platform |
| `ados.dataservice.events.v1` | Data Service | Gateway、Agent、Audit |
| `ados.agent.events.v1` | Agent | Gateway、Policy、Audit |
| `ados.model.events.v1` | Model Gateway | Agent、Audit、Platform |
| `ados.audit.security-events.v1` | Audit/Security | Gateway、Agent、Model、Platform |

### 7.3 事件目录

| 事件类型 | 关键Payload | 消费动作 |
|---|---|---|
| `identity.principal.revoked.v1` | principal_id、reason、effective_at | 清理身份/策略缓存，阻断调用 |
| `policy.version.published.v1` | policy_version、affected_resource_patterns | 失效决策和结果缓存 |
| `policy.grant.revoked.v1` | grant_id、subject、resource、effective_at | 立即收紧权限 |
| `ingestion.schema.discovered.v1` | source_id、discovery_id、object_count、manifest_ref | Catalog登记发现结果 |
| `ingestion.dataset_version.ready.v1` | dataset_ref、version、manifest_ref、quality_summary | Catalog创建候选版本 |
| `ingestion.document_version.ready.v1` | document_id、version、object_ref、ACL引用 | Knowledge启动解析 |
| `catalog.dataset.published.v1` | dataset_id、version、schema_fingerprint | Data Service执行兼容检查 |
| `catalog.classification.changed.v1` | resource、old/new、effective_at | 收紧策略、缓存失效、模型路由复核 |
| `knowledge.index.published.v1` | kb_id、index_version、document_count | Data Service刷新Knowledge API快照 |
| `knowledge.document.revoked.v1` | document_id、versions、reason | 检索阻断、缓存失效 |
| `dataservice.api.published.v1` | api_id、version、environment | Gateway刷新API目录 |
| `dataservice.api.suspended.v1` | api_id、versions、reason | 立即阻断调用 |
| `agent.status.suspended.v1` | agent_id、principal_ids、reason | Gateway Kill Switch |
| `model.budget.threshold_reached.v1` | subject、threshold、usage | 告警、降级或阻断 |
| `model.invocation.blocked.v1` | invocation_id、rule_ids、classification | 创建安全事件 |

### 7.4 DatasetPublished事件示例

```json
{
  "event_id": "evt_01J...",
  "event_type": "catalog.dataset.published.v1",
  "event_version": 1,
  "tenant_id": "tenant_001",
  "aggregate_type": "Dataset",
  "aggregate_id": "dataset_receivable",
  "aggregate_version": 12,
  "occurred_at": "2026-08-04T10:30:00Z",
  "producer": "catalog-service",
  "trace_id": "tr_01J...",
  "actor": {"type": "USER", "id": "user_data_owner"},
  "data_classification": "SENSITIVE",
  "payload": {
    "dataset_version": 12,
    "schema_fingerprint": "sha256:...",
    "serving_binding_ref": "serving-ref-01J...",
    "quality": {"score": 96.0, "status": "PASS"},
    "freshness_at": "2026-08-04T01:00:00Z",
    "sensitive_fields": ["contact_phone"],
    "effective_at": "2026-08-05T00:00:00Z"
  }
}
```

`serving_binding_ref`为内部不透明引用，事件不得包含数据库连接、Schema或凭证。

### 7.5 消费规则

- 至少一次投递，消费者必须按`event_id`幂等。
- 同一聚合按`aggregate_version`处理；小于当前版本的事件记录并忽略。
- 无法解析的事件进入DLQ，不允许无限重试阻塞分区。
- P0控制事件使用独立高优先级Consumer Group并监控端到端延迟。
- 事件处理成功后再提交Offset；涉及本地写入时使用Inbox表与业务事务一起提交。

## 8. 通用数据类型与Schema

### 8.1 ID与时间

| 类型 | 格式 | 示例 |
|---|---|---|
| Resource ID | UUID或带前缀ULID字符串 | `ds_01J4Z...` |
| Date | RFC 3339 full-date | `2026-08-04` |
| DateTime | RFC 3339 UTC | `2026-08-04T10:30:00Z` |
| Duration | ISO 8601 duration | `PT15M` |
| Decimal | 字符串 | `"320000.00"` |
| Currency | ISO 4217 | `CNY` |
| Locale | BCP 47 | `zh-CN` |
| Content Hash | 算法前缀+十六进制 | `sha256:17f6...` |

### 8.2 数据分级

```text
PUBLIC < INTERNAL < SENSITIVE < HIGHLY_SENSITIVE
```

分级只能提高或通过审批降低。接口接收的`classification_hint`不是最终分级，Catalog/安全流程拥有最终结论。

### 8.3 资源引用

```json
{
  "type": "DATASET",
  "id": "dataset_receivable",
  "version": 12,
  "display_name": "客户逾期应收"
}
```

### 8.4 质量摘要

```json
{
  "score": 96.0,
  "status": "PASS",
  "evaluated_at": "2026-08-04T01:05:00Z",
  "rule_summary": {
    "passed": 18,
    "warned": 1,
    "failed": 0
  },
  "warnings": [
    {"rule_id": "quality_late_settlement", "code": "PARTIAL_DELAY"}
  ]
}
```

### 8.5 引用对象

```json
{
  "citation_id": "cit_01",
  "source_type": "DOCUMENT",
  "document_id": "doc_1008",
  "document_version": 6,
  "title": "销售回款管理制度",
  "page": 12,
  "section": "4.3 逾期升级",
  "snippet": "……",
  "score": 0.91,
  "content_hash": "sha256:..."
}
```

`snippet`在返回前再次执行权限和DLP；审计事件只保存`citation_id`与内容哈希。

## 9. 权限Scope设计

### 9.1 Scope命名

```text
<resource>:<action>
```

示例：

- `datasource:create`
- `dataset:publish`
- `knowledge_base:test`
- `data_api:invoke`
- `agent:suspend`
- `audit:trace`

Token Scope只是调用入口条件，最终仍由Policy Service根据资源和上下文决策。

### 9.2 资源动作矩阵

| 资源 | 动作 |
|---|---|
| Tenant | READ、UPDATE、SUSPEND |
| User/Principal | CREATE、READ、UPDATE、STATUS、ROTATE、REVOKE |
| Policy/Role | CREATE、READ、UPDATE、SIMULATE、PUBLISH、GRANT、REVOKE |
| DataSource | CREATE、READ、UPDATE、TEST、DISCOVER、STATUS、CREDENTIAL |
| Dataset | READ、UPDATE、CERTIFY、PUBLISH、DEPRECATE |
| KnowledgeBase | CREATE、READ、UPDATE、BUILD_INDEX、TEST、PUBLISH |
| DataAPI | CREATE、READ、UPDATE、TEST、SUBMIT、PUBLISH、INVOKE、SUSPEND |
| Agent | CREATE、READ、UPDATE、TOOL_BIND、SUBMIT、PUBLISH、SUSPEND |
| Model | READ、MANAGE、TEST、ROUTE、BUDGET、USAGE |
| Audit/SecurityEvent | READ、TRACE、EXPORT、TRIAGE、CONTAIN、RESOLVE |

## 10. 限流、配额与超时

### 10.1 限流层级

最终限额取以下各级最小值：

```text
租户许可证限额
∩ Agent预算
∩ Agent版本限额
∩ Data API版本限额
∩ 用户委托限额
∩ 当前系统保护限额
```

### 10.2 限流响应头

```http
RateLimit-Limit: 60
RateLimit-Remaining: 14
RateLimit-Reset: 27
Retry-After: 27
```

### 10.3 默认超时

| 接口 | 服务端超时 | 重试原则 |
|---|---:|---|
| Policy Decision | 200ms | Gateway不做多次无界重试；失败关闭 |
| Query API | 10s，API可设置更低 | 只读且请求可重试，建议抖动退避 |
| Knowledge Retrieval | 5s，不含生成 | 可重试一次 |
| Model Generation | 30s | 仅在未产生有效响应且预算允许时重试 |
| 管理查询 | 10s | GET可安全重试 |
| 创建异步任务 | 5s | 使用幂等键重试 |
| Worker Callback | 5s | 使用序号和幂等键重试 |

## 11. API版本与兼容性

### 11.1 版本层级

| 层级 | 方式 | 示例 |
|---|---|---|
| 平台API大版本 | URL | `/api/v1` |
| Data API业务版本 | 请求字段+注册表 | `api_version: 1.0.0` |
| 事件版本 | event_type后缀 | `.v1` |
| Schema版本 | Registry ID/指纹 | `schema_fingerprint` |

### 11.2 兼容变更

以下通常为兼容变更：增加可选字段、增加新端点、增加可选枚举能力并允许旧客户端忽略。以下为破坏性变更：删除/重命名字段、改变类型或语义、必填化字段、改变默认权限或分页行为。

破坏性变更要求：

1. 发布新大版本或Data API主版本。
2. 提供至少一个约定兼容周期。
3. 在响应中增加`Deprecation`与`Sunset`头。
4. 提供调用方清单和迁移验证。

```http
Deprecation: true
Sunset: Tue, 04 Nov 2026 00:00:00 GMT
Link: </docs/migrations/query-api-v2>; rel="deprecation"
```

## 12. 安全接口要求

### 12.1 输入验证

- 所有请求使用JSON Schema白名单验证，拒绝未知字段的高风险命令接口。
- 字符串设置长度、Unicode规范化和控制字符规则。
- URL和对象引用只允许平台生成的不透明引用。
- SQL、模板、正则和脚本不作为普通输入类型开放。
- 文件名只作为展示字段；存储路径由服务端生成。

### 12.2 输出控制

- 字段脱敏在最接近数据的服务执行，Gateway再做响应DLP兜底。
- 高敏接口默认`Cache-Control: no-store`。
- 下载使用短期单次预签名URL，绑定主体、IP策略、文件哈希和有效期。
- 列表接口防止通过总数、排序和错误差异枚举不可见资源。
- 资源不存在与无权限统一返回`RESOURCE_NOT_VISIBLE`。

### 12.3 Prompt Injection接口边界

- 用户问题、系统指令、工具结果和检索证据必须使用结构化角色区分。
- Knowledge API不接受调用方自定义系统Prompt。
- 文档内容的任何命令性文本都标记为`UNTRUSTED_DATA`。
- 模型输出不能直接生成新的权限决策或修改工具Scope。
- 工具参数必须重新通过Data API Schema与Policy校验。

### 12.4 审计要求

以下接口成功或失败都必须审计：

- 登录、Token交换、凭据轮换和吊销。
- 用户、角色、权限、策略和访问申请变更。
- 数据源测试、发现、同步、文件接入和隔离处理。
- 数据集、索引、Data API、Agent和模型路由发布。
- 所有Agent Data API及模型调用。
- 审计导出、安全事件处置和Break-glass操作。

## 13. OpenAPI与SDK交付要求

### 13.1 OpenAPI拆分

建议维护以下契约文件：

```text
contracts/openapi/
├─ management-identity-v1.yaml
├─ management-policy-v1.yaml
├─ management-ingestion-v1.yaml
├─ management-catalog-v1.yaml
├─ management-knowledge-v1.yaml
├─ management-data-api-v1.yaml
├─ management-agent-v1.yaml
├─ management-model-v1.yaml
├─ management-audit-v1.yaml
├─ agent-data-query-v1.yaml
├─ agent-data-knowledge-v1.yaml
└─ internal-services-v1.yaml
```

共享Schema放入`components/schemas`包，通过版本化引用复用。CI必须校验引用、示例、Schema兼容性和operationId唯一性。

### 13.2 SDK

V1.0提供：

- Python Agent Data SDK。
- TypeScript管理API SDK。
- 标准HTTP示例和Postman/Bruno集合。
- Query API与Knowledge API的Agent Tool Schema。

SDK必须实现：Token刷新、trace/request ID、超时、有限重试、429退避、统一错误对象和敏感日志清洗。SDK不得自动扩大Scope或在本地持久化数据响应。

## 14. 契约测试与联调标准

### 14.1 契约测试

| 测试 | 覆盖要求 |
|---|---|
| OpenAPI语法 | 100%文件通过校验 |
| 请求/响应Schema | 每个operation至少一个成功、一个失败样例 |
| 向后兼容 | 合并请求自动对比上一发布版本 |
| 权限矩阵 | 每个端点覆盖允许、拒绝、跨租户、过期授权 |
| 幂等 | 命令接口覆盖重复请求与冲突请求体 |
| 乐观锁 | 更新/发布接口覆盖旧版本冲突 |
| 敏感信息 | 日志、错误、事件和响应快照扫描 |
| 事件 | Producer/Consumer Schema双向契约测试 |

### 14.2 Agent Data API验收基线

1. Agent不带Purpose、Audience错误、委托过期时请求均被拒绝。
2. 修改请求中的逻辑过滤不能覆盖系统行级过滤。
3. 请求未发布字段、排序和操作符均被拒绝。
4. 策略撤销后60秒内旧Token和缓存结果失效。
5. Knowledge检索在文档ACL变化后不得返回旧授权Chunk。
6. 模型不可用时，允许降级的Knowledge API返回证据，不允许降级的接口返回稳定错误。
7. 每次调用可由`trace_id`找到Gateway、Policy、Data/Knowledge、Model与Audit记录。

### 14.3 Mock与环境

| 环境 | 数据 | 外部依赖 | 用途 |
|---|---|---|---|
| Local | 合成数据 | Mock IdP/DeepSeek | 开发单测 |
| DEV | 脱敏样例 | Sandbox模型 | 功能联调 |
| TEST | 自动生成、多租户安全数据集 | Mock故障/限流 | E2E、性能、安全 |
| UAT | 客户批准的脱敏或隔离数据 | 客户批准模型 | 业务验收 |
| PROD | 真实数据 | 生产IdP/DeepSeek | 正式运行 |

禁止将生产数据复制到DEV/TEST。Mock服务必须能模拟超时、429、错误Schema、部分结果和安全阻断。

## 15. 接口需求追踪矩阵

| PRD/设计目标 | 接口范围 | 验收证据 |
|---|---|---|
| Agent不能直连数据库 | `/agent-data/v1/query/**`、`/knowledge/**` | 网络策略、凭据扫描、Agent E2E |
| 企业数据统一接入 | 数据源、发现、同步、上传接口 | MySQL/PostgreSQL/Oracle及四类文件契约测试 |
| 数据可治理 | 资产、版本、质量、血缘、发布接口 | 发布门禁和影响分析UAT |
| RAG可信可追溯 | 知识库、索引、检索、引用Schema | ACL、引用、索引回滚测试 |
| RBAC+ABAC | Policy Decision、Access Request | 越权矩阵、策略模拟、撤销SLA |
| 模型统一治理 | Model Invoke、Embedding、Usage | 出站DLP、Token/成本、故障降级 |
| 全链路审计 | Audit Event、Trace、Export | trace完整性和WORM校验 |
| 商业化交付 | OpenAPI、SDK、健康和版本接口 | 离线部署与客户联调报告 |

## 16. 待确认接口决策

| 编号 | 决策项 | 推荐结论 | 影响 |
|---|---|---|---|
| API-ADR-001 | 管理API是否采用GraphQL | V1.0不采用，统一REST/OpenAPI | 降低权限、缓存和交付复杂度 |
| API-ADR-002 | 内部API是否立即使用gRPC | V1.0 REST，模型/向量高吞吐后续评估gRPC | 便于调试和快速交付 |
| API-ADR-003 | Query返回行格式 | 对外使用对象数组；大批量导出不在V1.0 Agent接口开放 | 可读性优先，避免位置错配 |
| API-ADR-004 | Decimal格式 | 使用字符串并在Schema声明format=decimal | 避免金额精度损失 |
| API-ADR-005 | 证据不足HTTP状态 | 默认200+业务标志；严格模式可422 | 方便Agent按确定性字段处理 |
| API-ADR-006 | 策略决策内容传递 | 使用decision_id+签名上下文，下游可复核 | 避免调用方伪造obligations |
| API-ADR-007 | 事件交付语义 | 至少一次+Outbox/Inbox幂等 | 避免追求Exactly Once增加复杂度 |
| API-ADR-008 | 审计不可用时行为 | 敏感请求失败关闭，低敏按租户策略 | 满足最高安全优先级 |

## 17. 接口Definition of Done

接口只有满足以下条件才可标记完成：

1. OpenAPI或事件JSON Schema已进入版本库并通过CI校验。
2. 定义认证、权限Scope、请求/响应、错误码、幂等和审计行为。
3. 提供成功、参数错误、权限拒绝和依赖失败示例。
4. 完成Consumer/Provider契约测试和向后兼容检查。
5. 完成跨租户、越权、敏感信息、限流和重放测试。
6. 指标、日志和trace_id已接入，日志无Token、Secret和数据正文。
7. SDK或前端调用方已在TEST环境完成联调。
8. API负责人、安全负责人和调用方负责人共同签署发布。

---

**接口评审签署**

| 评审角色 | 结论 | 签署人 | 日期 | 备注 |
|---|---|---|---|---|
| 产品负责人 | 待评审 |  |  |  |
| API架构负责人 | 待评审 |  |  |  |
| 安全负责人 | 待评审 |  |  |  |
| 前端/SDK负责人 | 待评审 |  |  |  |
| 后端服务负责人 | 待评审 |  |  |  |
| 测试与交付负责人 | 待评审 |  |  |  |
