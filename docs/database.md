# Iteration 2 数据库与审计设计

## 交付范围

Iteration 2 将租户、用户、Agent、策略、授权和 Data API 元数据从内存适配器扩展为 SQLAlchemy 2.0 Repository，并引入审计 Transactional Outbox。业务数据查询仍由 `QueryDataPort` 抽象，Serving PostgreSQL 适配器属于后续数据接入迭代。

## 运行模式

| 模式 | 配置 | 用途 |
|---|---|---|
| 内存模式 | 不设置 `ADOS_DATABASE_URL` | 本地演示、API 契约测试 |
| 持久化模式 | 设置 PostgreSQL URL | 元数据、授权和审计持久化 |
| 测试模式 | SQLite 内存库且显式启用自动建表 | Repository 集成测试 |

生产环境必须设置 `ADOS_DATABASE_URL`，并且禁止 `ADOS_DATABASE_AUTO_CREATE=true`。生产 Schema 只能通过版本化迁移变更。

```powershell
$env:ADOS_DATABASE_URL='postgresql+psycopg://agent_data_os:password@localhost:5432/agent_data_os'
python -m alembic upgrade head
```

## 租户隔离

每个请求开启独立数据库事务，并使用 `set_config('app.current_tenant', tenant_id, true)` 设置事务局部变量。初始迁移对全部租户表启用并强制执行 PostgreSQL Row Level Security；Repository 查询仍显式携带 `tenant_id` 条件，形成纵深防御。

```text
已验证身份中的 tenant_id
          │
          ├── Repository 显式 tenant_id 条件
          │
          └── PostgreSQL transaction-local tenant
                         │
                         └── RLS USING / WITH CHECK
```

不得从 Query 参数、JSON Body 或 Agent 工具参数接受租户 ID。应用运行账号不应具备 `BYPASSRLS` 或数据库超级用户权限。

## 审计 Outbox

Query API 在返回受保护数据前同步写入 `audit_outbox`。事件只保存主体、用途、资源、结果数量、数据/策略版本等证据元数据，不保存过滤值、查询结果、Token 或 Secret。写入失败返回 `AUDIT_CHANNEL_UNAVAILABLE`，不向调用者交付数据。

Outbox 行以规范化 JSON 的 SHA-256 值提供完整性校验。Iteration 3 已实现租户级 Relay：按 `PENDING -> PUBLISHED` 状态机、`SKIP LOCKED` 行锁、指数退避和幂等事件 ID 投递。Kafka Publisher 与 WORM 归档仍由部署适配器提供。

## 版本基线

运行、开发与测试依赖的精确版本统一维护在 `requirements.txt`。`pyproject.toml` 保留运行时兼容版本区间，便于包管理器解析安全补丁；正式构建以唯一固定版本文件作为可复现基线。

## 验证命令

```bash
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
python -m pytest
python -m compileall -q src migrations
python -m alembic upgrade head
```
