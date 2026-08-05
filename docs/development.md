# V1.0开发说明

## 开发原则

1. 领域规则不得写在FastAPI路由中。
2. 领域层不得依赖FastAPI、数据库驱动或外部模型SDK。
3. 每类业务数据只能有一个权威写入模块。
4. 默认拒绝；身份、用途或策略不可用时不得返回数据。
5. Agent输入只能使用发布契约中的逻辑字段，不能提交SQL和物理表名。
6. 错误、日志和审计事件不得包含Token、Secret或查询结果正文。
7. 新接口必须包含类型定义、注释、错误行为和自动化测试。

## 目录约定

```text
src/agent_data_os/
├─ api/              FastAPI路由、依赖和协议适配
├─ application/      用例编排，不保存领域状态
├─ core/             配置、上下文、错误和中间件
├─ domains/          领域实体、值对象、规则和端口
└─ infrastructure/   内存、数据库、消息和外部服务适配器
```

依赖方向：

```text
API → Application → Domain
Infrastructure ────────┘
```

领域层通过`Protocol`定义端口，基础设施层实现端口。应用启动时在容器中完成依赖组装。

## 开发身份模拟

`ADOS_ALLOW_INSECURE_DEV_AUTH=true`只允许在`development`或`test`环境使用。应用在`production`环境检测到该配置时会直接启动失败。

开发Token只携带最小测试身份：租户、主体类型、主体ID和区域。它不模拟真实OIDC签名验证。正式实现应由Identity Service/OIDC适配器替换，并保持`IdentityResolver`端口不变。

## 新增领域功能步骤

1. 在`domains/<domain>`定义实体、值对象、异常和Repository端口。
2. 在`application`实现用例服务，明确事务边界。
3. 在`infrastructure`实现适配器。
4. 在`api`增加请求/响应Schema和路由。
5. 增加领域单元测试、接口测试和安全负向测试。
6. 更新OpenAPI示例和本说明文档。

## 注释规范

- 模块Docstring解释边界与安全假设。
- 公共类和方法Docstring说明职责、参数、返回和异常。
- 注释解释“为什么”和约束，不逐行翻译代码。
- 安全关键逻辑需要明确失败关闭、不可覆盖字段和数据泄露风险。

## 下一迭代

- PostgreSQL元数据Repository和迁移框架。
- OIDC/JWT验证与Token Exchange。
- Policy Service独立部署适配器。
- DataSource与同步任务领域。
- Transactional Outbox及审计事件。

