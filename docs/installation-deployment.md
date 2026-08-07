# Agent Data OS V1.0 安装与部署手册

## 1. 文档范围

本文档用于开发、测试、预生产和生产环境的安装、部署、验证、升级与回滚。Iteration 4 已提供 API、领域服务、PostgreSQL 持久化、知识流水线端口及生产适配器基线；企业生产上线仍必须完成身份、密钥、对象存储、病毒扫描、解析、Embedding、向量库和模型网关的环境组装。

生产发布遵循以下硬性门禁：

- Agent 只能通过 Agent Data API 访问数据，不得获得 PostgreSQL、MinIO、Milvus 或模型密钥。
- `ADOS_ENVIRONMENT=production`，并保持 `ADOS_ALLOW_INSECURE_DEV_AUTH=false`、`ADOS_DATABASE_AUTO_CREATE=false`。
- 运行账号不得是 PostgreSQL 超级用户，也不得拥有 `BYPASSRLS`。
- API、迁移 Job、Worker 使用不同服务账号和最小权限凭据。
- Secret 只能来自 Vault、云 Secret Manager 或 Kubernetes Secret CSI，不写入镜像、Git、ConfigMap和日志。
- 未注入生产适配器时系统按失败关闭策略拒绝知识处理，不得通过修改代码绕过。

## 2. 部署拓扑

```text
Ingress / WAF / API Gateway
          |
          v
Agent Data OS API (无状态，多副本，非 root)
    |        |          |             |
    |        |          |             +--> Model Gateway --> DeepSeek API
    |        |          +----------------> Milvus
    |        +---------------------------> MinIO
    +------------------------------------> PostgreSQL

Knowledge Worker --> ClamAV --> Parser/OCR --> Embedding Gateway --> Milvus
        |
        +--> PostgreSQL 状态、审计和 Outbox

Observability: Metrics / Logs / Traces / Alerting
Secrets: Vault/KMS/Secret Manager
```

开发模式将以上外部端口替换为内存对象存储、确定性 Embedding、内存向量索引和开发生成器，仅用于本地功能验证。

## 3. 版本与资源基线

### 3.1 软件版本

Python 包的精确版本以仓库根目录唯一的 `requirements.txt` 为准。基础设施建议范围如下；正式交付时应在客户环境完成兼容性验证，并将容器镜像固定到不可变 digest。

| 组件 | 支持/建议基线 | 用途 |
|---|---|---|
| Python | 3.10+；镜像使用 3.12 | API、Worker、迁移 |
| PostgreSQL | 14+ | 元数据、状态、审计、Outbox、Serving |
| MinIO | 客户当前受支持稳定版 | 原始文件和解析产物 |
| Milvus | 2.x，与客户端版本匹配 | 向量索引与租户/ACL预过滤 |
| ClamAV | 1.x | 上传文件恶意内容扫描 |
| Kubernetes | 1.28+ | 生产编排 |
| DeepSeek | OpenAI兼容 Chat Completions API | V1.0生成模型 |

不得使用 `latest` 镜像标签。平台、数据库、Milvus 和 MinIO 的具体版本、digest、升级窗口应写入每个客户的部署物料清单。

### 3.2 最小资源建议

| 环境 | API | PostgreSQL | Milvus | MinIO | Worker |
|---|---:|---:|---:|---:|---:|
| 开发 | 2 CPU / 2 GiB | 2 CPU / 4 GiB | 4 CPU / 8 GiB | 2 CPU / 2 GiB | 2 CPU / 4 GiB |
| 测试 | 2×2 CPU / 4 GiB | 4 CPU / 8 GiB | 8 CPU / 16 GiB | 4 CPU / 8 GiB | 2×4 CPU / 8 GiB |
| 生产起步 | 3×4 CPU / 8 GiB | 高可用 8 CPU / 32 GiB | 按向量规模压测 | 分布式 4 节点起 | 3×4 CPU / 8 GiB |

生产容量必须根据文档量、平均 Chunk 数、Embedding 维度、查询 QPS、索引重建窗口和保留周期压测后确定。

## 4. 本地开发安装

### 4.1 获取代码并创建虚拟环境

PowerShell：

```powershell
git clone https://github.com/YounthThrob/Agent_data_os.git
Set-Location Agent_data_os
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
```

Bash：

```bash
git clone https://github.com/YounthThrob/Agent_data_os.git
cd Agent_data_os
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
```

`requirements.txt` 已统一包含运行、开发与测试依赖。安装后执行：

```powershell
python -m pytest --cov=agent_data_os --cov-report=term-missing
python -m compileall -q src
```

### 4.2 无外部依赖启动

PowerShell：

```powershell
$env:ADOS_ENVIRONMENT='development'
$env:ADOS_ALLOW_INSECURE_DEV_AUTH='true'
$env:ADOS_DATABASE_AUTO_CREATE='false'
python -m uvicorn agent_data_os.main:app --app-dir src --reload
```

Bash：

```bash
export ADOS_ENVIRONMENT=development
export ADOS_ALLOW_INSECURE_DEV_AUTH=true
export ADOS_DATABASE_AUTO_CREATE=false
python -m uvicorn agent_data_os.main:app --app-dir src --reload
```

此模式的数据在进程退出后丢失，不执行真实病毒扫描、OCR、Embedding 或模型调用。

### 4.3 本地 PostgreSQL 模式

创建独立数据库和运行角色，示例中的密码必须替换：

```sql
CREATE ROLE agent_data_os_runtime LOGIN PASSWORD 'replace-me' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE DATABASE agent_data_os OWNER agent_data_os_runtime;
```

设置连接串并迁移：

```powershell
$env:ADOS_DATABASE_URL='postgresql+psycopg://agent_data_os_runtime:replace-me@127.0.0.1:5432/agent_data_os'
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

启动应用时仍保持 `ADOS_DATABASE_AUTO_CREATE=false`。`true` 只允许一次性测试，不允许任何共享环境使用。

## 5. 配置清单

### 5.1 应用内置环境变量

| 变量 | 开发值 | 生产要求 |
|---|---|---|
| `ADOS_ENVIRONMENT` | `development` | 必须为 `production` |
| `ADOS_SERVICE_NAME` | `agent-data-os` | 按环境命名 |
| `ADOS_LOG_LEVEL` | `INFO` | `INFO`，排障窗口可临时调高 |
| `ADOS_ALLOW_INSECURE_DEV_AUTH` | `true` | 必须为 `false` |
| `ADOS_DATABASE_URL` | 可空 | 必填，从 Secret 注入 |
| `ADOS_DATABASE_ECHO` | `false` | 必须为 `false`，避免数据进入日志 |
| `ADOS_DATABASE_AUTO_CREATE` | `false` | 必须为 `false` |
| `ADOS_DEFAULT_QUERY_LIMIT` | `20` | 按租户策略配置 |
| `ADOS_MAX_QUERY_LIMIT` | `100` | 不得高于容量与数据泄露阈值 |

### 5.2 生产组装层配置

下列配置由客户的生产 bootstrap/依赖注入层读取，不应直接加入领域模型：

| 配置 | 示例 | Secret |
|---|---|---|
| MinIO endpoint/bucket/region | `https://minio.internal` / `ados-documents` | 否 |
| MinIO access/secret key | Secret 引用 | 是 |
| ClamAV host/port | `clamav.security.svc:3310` | 否 |
| Parser/OCR endpoint | `https://parser.internal` | 认证信息是 |
| Embedding Gateway endpoint/model | 内网地址/企业模型编码 | Token 是 |
| Milvus endpoint/collection | 内网地址/固定 collection | Token 是 |
| Model Gateway endpoint/model | 内网地址/DeepSeek 路由编码 | API Key 是 |
| KMS key id | 客户主密钥别名 | 授权凭据是 |
| OIDC issuer/audience/JWKS | 企业 IdP | Client Secret 是 |

## 6. 外部组件初始化

### 6.1 PostgreSQL

1. 创建 migration owner 和 runtime 两个角色；migration owner 仅由发布 Job 使用。
2. runtime 角色授予业务表最小 `SELECT/INSERT/UPDATE` 权限，不授予 DDL、超级用户或 `BYPASSRLS`。
3. 执行 `alembic upgrade head`。迁移会为租户表启用并强制 PostgreSQL RLS。
4. 连接池每个事务必须设置 `app.current_tenant`，事务结束后清理；Repository 同时包含显式 `tenant_id` 条件。
5. 启用 TLS、静态加密、PITR、慢查询监控和连接数告警。
6. 验收时使用两个租户执行负向查询，确认无法跨租户读取。

迁移前检查：

```powershell
python -m alembic current
python -m alembic heads
python -m alembic check
```

迁移后检查：

```powershell
python -m alembic current
python -m pytest -q tests/test_iteration4_persistence.py
```

### 6.2 MinIO

1. 创建私有 bucket `ados-documents`，禁止匿名访问和公网暴露。
2. 启用服务端加密、版本控制、生命周期和审计日志；生产建议启用对象锁/WORM保存关键证据。
3. API 账号只允许生成短期上传 URL，Worker 账号只允许指定 tenant 前缀读写。
4. 对象键只能由服务端生成，格式为 `tenants/{tenant_id}/knowledge/{kb_id}/documents/{document_id}/versions/{version_id}/...`。
5. 配置 CORS 仅允许管理控制台域名、`PUT` 和必要请求头。
6. 接入 `MinioObjectStorage` 时注入官方客户端；不得将 Secret 暴露给浏览器或 Agent。

### 6.3 ClamAV 与解析/OCR

1. 部署独立 ClamAV 服务并更新病毒库；NetworkPolicy 只允许 Knowledge Worker 访问 3310 端口。
2. 上传对象先校验声明大小、SHA-256 和文件魔数，再进入病毒扫描。
3. 扫描超时、服务不可用或命中恶意内容均失败关闭；文档进入 `QUARANTINED`，不得解析或索引。
4. PDF、DOCX、XLSX、图片解析器在无网络、只读文件系统、CPU/内存限制的隔离 Worker 中运行。
5. 设置页数、压缩比、递归深度、OCR时长和单文件大小上限，防止压缩炸弹与资源耗尽。
6. `CompositeDocumentParser` 按 MIME 注册解析器；未注册类型必须拒绝。

### 6.4 Milvus

为生产创建固定 collection，禁止按租户动态创建无限 collection。字段至少包括：

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| `chunk_id` | 主键字符串 | 与 PostgreSQL Chunk 对应 |
| `tenant_id` | 字符串，标量索引 | 强制租户预过滤 |
| `knowledge_base_id` | 字符串，标量索引 | 知识库过滤 |
| `index_version_id` | 字符串，标量索引 | 蓝绿发布版本 |
| `acl_tokens` | 字符串数组 | 用户/部门/组/角色 ACL |
| `embedding` | FloatVector | 维度必须与模型一致 |

向量索引和检索指标使用 `COSINE`。查询表达式必须同时包含 `tenant_id`、`knowledge_base_id`、已发布 `index_version_id` 和 ACL；召回后还要到 PostgreSQL 复核文档当前状态和 ACL。上线前执行索引构建、召回率、延迟和跨租户负向测试。

### 6.5 Embedding 与 DeepSeek Model Gateway

1. Agent Data OS 只调用企业 Model Gateway，不在业务 Pod 中保存 DeepSeek Key。
2. `HttpEmbeddingGateway` 调用内网 `/internal/v1/models/embeddings`；Gateway 负责路由、限流、重试、熔断、Token与成本统计。
3. `DeepSeekGenerationGateway` 使用固定系统边界，将召回内容标记为不可信证据。
4. `CONFIDENTIAL`、`SECRET` 内容默认禁止发送外部模型；只有通过数据分级和出站 DLP 的内容可生成回答。
5. Gateway 日志不得记录完整 Prompt、证据正文、Authorization 或 API Key。

## 7. 容器构建与单机验证

仓库 `Dockerfile` 使用 Python 3.12、非 root UID 10001，并包含存活检查。

```powershell
docker build --pull -t agent-data-os:iteration4 .
docker run --rm -p 8000:8000 `
  -e ADOS_ENVIRONMENT=development `
  -e ADOS_ALLOW_INSECURE_DEV_AUTH=true `
  agent-data-os:iteration4
```

另一个终端验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

构建生产镜像时应在 CI 中执行依赖漏洞扫描、Secret 扫描、SBOM 生成、镜像签名和测试，随后使用镜像 digest 发布。生产容器不得传入开发认证开关。

## 8. Kubernetes 生产部署流程

### 8.1 前置准备

1. 建立 `agent-data-os` namespace、ResourceQuota、LimitRange 和默认拒绝 NetworkPolicy。
2. 配置只读 RootFS、Pod Security Restricted、非 root ServiceAccount。
3. 由 Secret CSI 挂载数据库、OIDC、MinIO、Milvus、KMS和模型凭据；禁止明文 YAML。
4. 配置 Ingress TLS、WAF、请求体上限、速率限制和上传超时。
5. 预先完成 PostgreSQL、MinIO、Milvus、ClamAV、Parser、Model Gateway 的连通性和证书校验。

### 8.2 数据库迁移 Job

先运行一次迁移 Job，成功后才更新 API/Worker：

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: agent-data-os-migrate-iteration4
  namespace: agent-data-os
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: agent-data-os-migrator
      containers:
        - name: migrate
          image: registry.example/agent-data-os@sha256:REPLACE_WITH_DIGEST
          args: ["alembic", "upgrade", "head"]
          env:
            - name: ADOS_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: ados-migration-database
                  key: url
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 10001
```

### 8.3 API Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-data-os-api
  namespace: agent-data-os
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate: {maxUnavailable: 0, maxSurge: 1}
  selector:
    matchLabels: {app: agent-data-os-api}
  template:
    metadata:
      labels: {app: agent-data-os-api}
    spec:
      serviceAccountName: agent-data-os-api
      containers:
        - name: api
          image: registry.example/agent-data-os@sha256:REPLACE_WITH_DIGEST
          ports: [{name: http, containerPort: 8000}]
          env:
            - {name: ADOS_ENVIRONMENT, value: production}
            - {name: ADOS_ALLOW_INSECURE_DEV_AUTH, value: "false"}
            - {name: ADOS_DATABASE_AUTO_CREATE, value: "false"}
            - name: ADOS_DATABASE_URL
              valueFrom:
                secretKeyRef: {name: ados-runtime-database, key: url}
          readinessProbe:
            httpGet: {path: /health/ready, port: http}
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet: {path: /health/live, port: http}
            initialDelaySeconds: 10
            periodSeconds: 20
          resources:
            requests: {cpu: 500m, memory: 512Mi}
            limits: {cpu: "2", memory: 2Gi}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: {drop: ["ALL"]}
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 10001
```

示例只展示安全骨架。实际 Deployment 必须使用客户 bootstrap 入口注入 OIDC、KMS 和 `KnowledgeInfrastructure`，并挂载临时目录到独立 `emptyDir`。直接使用默认生产入口时，外部知识适配器和身份解析器会失败关闭，这是预期安全行为。

### 8.4 发布顺序

1. CI 完成单元测试、覆盖率、迁移往返、镜像扫描、SBOM和签名。
2. 备份 PostgreSQL、MinIO 元数据和 Milvus collection 元数据，记录当前镜像 digest 与 Alembic revision。
3. 在预生产执行迁移 Job、API和Worker部署，再运行验收测试。
4. 生产执行向后兼容的数据库迁移；确认 Job 成功且 revision 为 head。
5. 滚动更新 API，观察 readiness、5xx、P95、连接池和拒绝率。
6. 更新 Knowledge Worker；先构建新 IndexVersion，验证后原子发布，旧索引保留到回滚窗口结束。
7. 执行冒烟和安全负向测试，最后开放全部流量。

## 9. 健康检查与验收

`/health/live` 只表示进程存活；`/health/ready` 用于接收流量。生产 bootstrap 应扩展就绪检查，验证 PostgreSQL 和关键依赖，但不得在响应中暴露内部地址、版本或凭据。

发布验收至少包括：

- 未认证、错误 scope、错误 purpose 和跨租户请求均被拒绝。
- 上传 URL 由服务端生成；大小、SHA-256、MIME魔数和病毒扫描生效。
- 文档 ACL 在向量检索前过滤，并在 PostgreSQL 再次复核。
- Prompt Injection 查询被阻断，恶意召回片段被排除。
- 机密数据不发送到外部 DeepSeek。
- Knowledge API 返回可定位引用；证据不足按策略降级或报错。
- 新索引发布原子切换，旧索引可用于回滚。
- 审计包含主体、租户、用途、策略与结果，但不含 Token、Query正文或证据正文。
- PostgreSQL RLS 使用双租户负向用例验证。

快速检查：

```powershell
Invoke-RestMethod https://ados.example.com/health/live
Invoke-RestMethod https://ados.example.com/health/ready
python -m alembic current
```

## 10. 监控、备份与灾难恢复

必须监控 API QPS/P50/P95/P99、4xx/5xx、策略拒绝、Prompt Injection、扫描失败、解析积压、Embedding延迟、Milvus召回延迟、模型Token/费用、数据库连接池、Outbox积压和索引发布时间。

备份要求：

- PostgreSQL：每日全量加持续 WAL/PITR；至少季度恢复演练。
- MinIO：跨故障域纠删码/复制，保留对象版本和删除标记。
- Milvus：备份索引元数据；向量索引必须能由 PostgreSQL Chunk 与对象存储重新构建。
- KMS/Vault：按企业规范备份密钥元数据，不导出不可导出的主密钥。
- 审计：写入独立 WORM 存储，保留周期由法规和合同确定。

恢复顺序为 PostgreSQL → MinIO → Milvus重建/恢复 → API → Worker。恢复后必须重跑租户隔离、ACL、引用一致性和审计完整性检查。

## 11. 升级与回滚

### 11.1 升级原则

- 数据库迁移采用 expand/contract，先增加兼容结构，再发布代码，最后在后续版本删除旧结构。
- API 契约保持版本兼容；破坏性变化发布新路径或新 `api_version`。
- Knowledge 索引采用蓝绿版本；构建和验证不影响当前已发布索引。
- 每次发布记录 Git commit、镜像 digest、Alembic revision、配置版本和策略版本。

### 11.2 应用回滚

若数据库迁移向后兼容，直接将 Deployment 镜像恢复到上一 digest，并暂停新 Worker。随后将知识库指针切回上一 `PUBLISHED` IndexVersion。

### 11.3 数据库回滚

生产环境优先使用前向修复。只有迁移脚本已经在同版本数据副本演练、确认不会丢数据时，才执行：

```powershell
python -m alembic downgrade 20260805_0002
```

Iteration 4 的降级会删除知识域表，因此包含真实文档数据的环境不得直接执行。应先完整备份并获得变更审批。出现不可逆错误时从 PITR 恢复到新实例，再切换连接。

## 12. 常见故障

| 现象 | 检查 | 处理 |
|---|---|---|
| production 启动失败 | 数据库 URL、开发认证、自动建表 | 按安全提示修正，禁止绕过校验 |
| Knowledge API 返回适配器不可用 | 生产 bootstrap 是否注入全部端口 | 补齐适配器、证书和网络策略 |
| 文档进入 QUARANTINED | 哈希、MIME、ClamAV结果 | 保留证据，人工审核，禁止直接改状态 |
| 检索无结果 | 已发布索引、ACL、文档状态、purpose | 逐层检查，不得放宽租户过滤 |
| Milvus查询失败 | 维度、collection schema、索引状态 | 修正模型/collection契约，重建新版本 |
| 外部模型生成被跳过 | 数据分级或DLP | 使用私有模型或经审批调整出站策略 |
| Alembic check 有差异 | ORM与迁移不一致 | 生成并评审新迁移，禁止自动建表代替 |

## 13. 上线检查表

- [ ] 镜像使用 digest、完成扫描并签名。
- [ ] 生产配置关闭开发认证和自动建表。
- [ ] OIDC、KMS、MinIO、ClamAV、Parser、Embedding、Milvus、Model Gateway适配器齐全。
- [ ] runtime 数据库角色非超级用户且无 `BYPASSRLS`。
- [ ] RLS、ACL、Prompt Injection、DLP和审计负向测试通过。
- [ ] 数据库迁移、备份恢复、索引蓝绿切换演练通过。
- [ ] Ingress TLS、WAF、NetworkPolicy、Pod Security和限流生效。
- [ ] 监控仪表盘、告警接收人、值班和回滚负责人已确认。
- [ ] 容量、P95/P99、峰值上传和索引重建压测达标。
- [ ] Git commit、镜像 digest、迁移 revision和配置版本已归档。
