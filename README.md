# Agent Data OS

> Enterprise Agent Data Operating System — 面向企业内部数据和多Agent系统的统一、安全、可治理、可调用的数据基础设施。

Agent Data OS 位于企业数据与Agent应用之间，将数据库、业务系统、文件和知识转化为具有统一语义、明确权限、稳定契约和完整审计的数据能力。

它不是传统BI系统、数据仓库替代品或单一RAG应用，而是一条受控的数据能力链：

```text
企业数据
  ↓ 接入、版本、质量、分级与血缘
AI可理解的数据与知识
  ↓ 权限决策、脱敏、DLP与审计
Agent Data API
  ↓ Query / Knowledge
单Agent、多Agent和业务工作流
```

## 项目状态

项目处于 **V1.0开发阶段**。Iteration 2 已完成首个可持久化纵向切片：

- FastAPI后端工程骨架。
- 领域层、应用层、接口层和基础设施层分离。
- 统一请求ID、Trace ID、错误信封与严格参数校验。
- 用户、Agent和服务主体统一安全上下文。
- 默认拒绝的基础RBAC+ABAC策略决策。
- Agent Query API字段白名单、过滤、排序和返回限制。
- 策略生成的不可覆盖行级数据范围。
- 跨租户资源隐藏和生产环境安全配置校验。
- 内部Policy Decision接口。
- 开发/测试内存适配器、示例数据和自动化测试。
- SQLAlchemy 2.0 PostgreSQL 元数据 Repository 与 Alembic 迁移。
- Tenant、User、Agent、Policy、Grant、Data API 元数据表。
- Repository 强制租户条件与 PostgreSQL RLS 双重隔离。
- Query API 成功、拒绝和失败审计，以及 Transactional Outbox。
- 生产数据库配置安全校验与版本固定的依赖清单。

OIDC、业务数据 Serving Repository、数据接入 Worker、Outbox Kafka Relay、知识处理、Milvus、MinIO 和 DeepSeek 模型网关尚在后续迭代中。当前代码是领域行为与接口契约基线，不应直接用于生产环境。

## 产品解决的问题

| 企业问题 | Agent Data OS能力 |
|---|---|
| ERP、CRM、OA、MES和数据库形成数据孤岛 | 标准连接器、统一接入和数据资产目录 |
| 文档、表格、图片和结构化数据格式不统一 | 文件解析、Schema管理、Chunk与Embedding流水线 |
| Agent无法安全访问企业数据 | Agent Data Gateway与受控Data API |
| 权限只面向人员，不适用于Agent | Agent独立身份、用户委托、RBAC+ABAC和用途限制 |
| 多Agent重复建设RAG与数据连接 | 共享知识库、统一API目录和稳定工具契约 |
| 敏感数据可能被发送到外部模型 | 模型网关、出站DLP和数据分级路由 |
| Agent回答和执行过程不可追溯 | 数据版本、引用、策略、模型调用和审计链路 |

## V1.0范围

### 包含

- MySQL、PostgreSQL、Oracle批量/增量接入。
- PDF、Word、Excel和图片接入。
- 数据目录、Schema、标签、分级、质量和基础血缘。
- 文档解析、Chunk、Embedding、向量检索和引用。
- Query API与Knowledge API。
- Agent注册、工具绑定、用途、预算和Kill Switch。
- DeepSeek模型网关、Token统计、费用与出站安全控制。
- 多租户隔离、RBAC、基础ABAC、动态脱敏和审计。
- Docker/Kubernetes私有化部署。

### 不包含

- Agent直接访问生产数据库或自由提交SQL。
- Agent写回ERP、CRM等业务系统。
- 通用知识图谱、Graph API和Insight API生产能力。
- 可视化通用多Agent编排设计器。
- 共享型公有SaaS规模化运营能力。

## 系统架构

```mermaid
flowchart TB
    AGENT["企业Agent / LangGraph应用"] --> GATEWAY["Agent Data Gateway"]
    USER["企业管理用户"] --> CONTROL["管理控制台与Control API"]

    GATEWAY --> IDENTITY["身份与委托"]
    GATEWAY --> POLICY["策略决策PDP"]
    GATEWAY --> QUERY["Query Service"]
    GATEWAY --> KNOWLEDGE["Knowledge Service"]

    CONTROL --> INGESTION["Ingestion Service"]
    CONTROL --> CATALOG["Catalog Service"]
    CONTROL --> AGENT_MGMT["Agent Service"]

    INGESTION --> WORKER["Connector / Parser / Quality Worker"]
    WORKER --> SOURCES["ERP / CRM / OA / MES / DB / File / API"]
    WORKER --> POSTGRES["PostgreSQL Serving"]
    WORKER --> MINIO["MinIO"]

    QUERY --> POSTGRES
    KNOWLEDGE --> MILVUS["Milvus"]
    KNOWLEDGE --> MODEL["Model Gateway"]
    MODEL --> DEEPSEEK["DeepSeek API"]

    GATEWAY --> AUDIT["Audit Service"]
    QUERY --> AUDIT
    KNOWLEDGE --> AUDIT
    MODEL --> AUDIT
    AUDIT --> KAFKA["Kafka / WORM Archive"]
```

### 领域划分

| 领域 | 主要职责 |
|---|---|
| 租户与身份 | Tenant、User、Agent Principal、服务主体和委托Token |
| 策略与数据安全 | RBAC、ABAC、用途、授权、行列权限和脱敏 |
| 数据接入 | DataSource、Connector、SyncJob、Checkpoint和隔离区 |
| 数据资产与治理 | Dataset、Schema、质量、分级、责任、血缘和生命周期 |
| 知识处理与检索 | Document、Chunk、Embedding、IndexVersion和引用 |
| 数据服务 | Query API、Knowledge API、版本、发布和运行控制 |
| Agent管理 | Agent定义、版本、工具绑定、预算和Kill Switch |
| 模型管理 | DeepSeek适配、路由、DLP、Token和成本 |
| 审计与安全运营 | AuditEvent、SecurityEvent、告警和证据包 |

## 当前代码结构

```text
Agent_data_os/
├─ src/agent_data_os/
│  ├─ api/                    FastAPI路由、Schema和依赖
│  ├─ application/            应用用例编排
│  ├─ core/                   配置、身份、上下文、错误与中间件
│  ├─ domains/
│  │  ├─ data_service/        Query API领域模型与端口
│  │  └─ policy/              策略领域模型与决策服务
│  ├─ infrastructure/         内存适配器与SQLAlchemy持久化适配器
│  ├─ container.py            显式依赖组装
│  └─ main.py                 FastAPI应用工厂
├─ tests/                     接口、安全和配置测试
├─ migrations/                Alembic数据库迁移与PostgreSQL RLS
├─ docs/                      架构、开发规范与实现状态
├─ Agent_Data_OS_PRD_SRS.md
├─ Agent_Data_OS_V1.0_Domain_Service_Design.md
├─ Agent_Data_OS_V1.0_API_Design.md
├─ pyproject.toml
├─ requirements.txt           固定版本的运行时依赖
├─ requirements-dev.txt       固定版本的开发/测试依赖
└─ .env.example
```

依赖方向固定为：

```text
API → Application → Domain
Infrastructure ────────┘
```

领域层不依赖FastAPI、数据库驱动或模型SDK；基础设施通过领域端口接入。

## 快速开始

### 环境要求

- Python 3.10及以上；生产建议Python 3.12。
- 默认内存模式无需外部基础设施；持久化模式需要 PostgreSQL 14 及以上。

### 安装

PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Bash：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ''.[dev]''
```

### 开发配置

PowerShell：

```powershell
$env:ADOS_ENVIRONMENT=''development''
$env:ADOS_ALLOW_INSECURE_DEV_AUTH=''true''
```

Bash：

```bash
export ADOS_ENVIRONMENT=development
export ADOS_ALLOW_INSECURE_DEV_AUTH=true
```

其他参数见 [`.env.example`](./.env.example)。项目当前不自动加载`.env`，配置由终端、IDE、容器或部署平台注入。

### 启动

```powershell
python -m uvicorn agent_data_os.main:app --app-dir src --reload
```

| 地址 | 用途 |
|---|---|
| `http://127.0.0.1:8000/docs` | Swagger UI |
| `http://127.0.0.1:8000/openapi.json` | OpenAPI 3.1契约 |
| `http://127.0.0.1:8000/health/live` | 存活检查 |
| `http://127.0.0.1:8000/health/ready` | 就绪检查 |

## Query API示例

开发Token格式：

```text
dev.<tenant_id>.<actor_type>.<actor_id>.<region>
```

例如：`dev.tenant_001.AGENT.sales_risk_agent.EAST`。

该Token没有密码学签名，只允许本地开发和测试使用。生产环境检测到开发认证开关会拒绝启动。

```powershell
$headers = @{
  Authorization = ''Bearer dev.tenant_001.AGENT.sales_risk_agent.EAST''
  ''X-Purpose'' = ''sales_risk_followup''
}

$body = @{
  api_version = ''1.0.0''
  select = @(''customer_name'', ''region'', ''overdue_amount'', ''currency'')
  filters = @(@{field=''overdue_days''; op=''gte''; value=30})
  order_by = @(@{field=''overdue_amount''; direction=''desc''})
  limit = 20
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri ''http://127.0.0.1:8000/agent-data/v1/query/customer_receivable_query'' `
  -Headers $headers `
  -ContentType ''application/json'' `
  -Body $body
```

响应包含：

- `request_id`与`trace_id`。
- 返回字段Schema和受控数据行。
- 数据集版本、新鲜度和质量分。
- 策略决策ID、策略版本和实际结果上限。
- API编码、版本和截断状态。

示例Agent属于`EAST`区域。即使请求没有提交区域条件，Policy Service仍会追加不可覆盖的`region = EAST`行级过滤。

## 配置参数

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ADOS_ENVIRONMENT` | `development` | `development`、`test`或`production` |
| `ADOS_ALLOW_INSECURE_DEV_AUTH` | `false` | 启用开发身份；production禁止 |
| `ADOS_SERVICE_NAME` | `agent-data-os` | 服务名称 |
| `ADOS_LOG_LEVEL` | `INFO` | 日志级别 |
| `ADOS_DEFAULT_QUERY_LIMIT` | `20` | Query API默认返回条数 |
| `ADOS_MAX_QUERY_LIMIT` | `100` | Query API全局最大返回条数 |

生产环境不得使用`.env`保存数据库、OIDC或DeepSeek Secret。正式实现将使用Vault/KMS等Secret Manager，并在业务配置中只保存Secret引用。

## 测试与验证

```powershell
python -m pytest -q
python -m compileall -q src
```

当前测试覆盖健康检查、认证拒绝、策略行级过滤、字段/操作符白名单、用途限制、跨租户隐藏、未知参数拒绝和生产安全配置。

## 安全原则

### 默认拒绝

身份、用途、API发布状态、Grant或策略决策任何一项不满足时，平台不返回数据。

### Agent不直连数据源

```text
Agent → Agent Data Gateway → Policy → Query/Knowledge Service → 数据中心
```

Agent不得获得数据库、MinIO、Milvus或DeepSeek直连凭证。

### 权限取交集

```text
有效权限 =
租户安全基线
∩ 委托用户权限
∩ Agent自身权限
∩ Data API发布权限
∩ 当前用途和环境约束
```

### 数据泄露控制

- 不信任客户端提交的`tenant_id`、角色或部门。
- 不开放自由SQL和物理Schema。
- 错误响应不包含SQL、堆栈、连接串和内部地址。
- 日志和审计不得记录Token、Secret或数据正文。
- 模型出站必须经过Model Gateway和DLP。
- 检索内容视为不可信数据，不能修改系统权限或工具Scope。

## 项目文档

| 文档 | 内容 |
|---|---|
| [PRD + SRS](./Agent_Data_OS_PRD_SRS.md) | 产品定位、核心模块、安全、数据模型、版本和商业化 |
| [V1.0领域与服务边界](./Agent_Data_OS_V1.0_Domain_Service_Design.md) | 限界上下文、服务职责、数据所有权、事件和关键流程 |
| [V1.0接口设计](./Agent_Data_OS_V1.0_API_Design.md) | 管理API、Agent Data API、内部API和Kafka事件契约 |
| [代码架构](./docs/architecture.md) | 当前依赖方向、安全边界和适配器替换点 |
| [开发规范](./docs/development.md) | 目录、领域功能开发步骤、注释和安全要求 |
| [实现状态](./docs/implementation-status.md) | 已完成范围、验证结果、限制和下一迭代 |

## 开发路线

### Iteration 1：安全骨架与Query API

状态：已完成。

### Iteration 2：PostgreSQL元数据与审计基础

- Tenant、User、Agent、Policy、Grant和DataAPI持久化。
- 数据库迁移、租户约束和PostgreSQL Repository。
- Transactional Outbox和审计事件。
- 数据库集成与跨租户负向测试。

### Iteration 3：数据接入闭环

- DataSource和SyncJob领域。
- PostgreSQL/MySQL/Oracle连接器。
- Schema发现、Checkpoint、Manifest和DatasetVersion。
- Serving PostgreSQL查询适配器。

### Iteration 4：知识闭环

- 文件上传、DocumentVersion、Parser、OCR和Chunk。
- MinIO、Milvus和Embedding适配器。
- DeepSeek Model Gateway与Knowledge API。
- 文档ACL和引用定位测试。

### Iteration 5：企业化交付

- Kafka审计、WORM归档与安全事件。
- Kubernetes、Helm、备份恢复和升级工具。
- SSO、密钥轮换、监控告警和容量测试。

## 开发约定

1. 领域规则不得写在FastAPI路由中。
2. 领域层不得依赖Web框架、数据库或外部SDK。
3. 不得跨领域直接修改其他模块的数据表。
4. 新接口必须定义Schema、错误码、权限、幂等、审计和测试。
5. 安全关键代码必须解释失败关闭与不可覆盖约束。
6. 提交前必须运行相关测试和编译检查。
7. 禁止提交`.env`、Token、数据库密码、模型Key和真实客户数据。

## 许可证

当前仓库尚未确定开源许可证。在许可证文件发布前，默认保留所有权利；如需外部使用、分发或商业集成，请先与项目所有者确认。

