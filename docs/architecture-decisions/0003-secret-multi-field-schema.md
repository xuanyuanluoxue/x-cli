# ADR 0003: 密钥记录采用具名多字段 schema

- 状态：已接受
- 日期：2026-07-19

## 背景

`x secret` 的 1.0 数据模型每条记录只有一个 `value` 字符串。迁移自 Markdown 的记录常把 API key、URL、账号和其他说明塞进同一个多行 value，Web 页面只能把整块内容当作密钥掩码，或者把 URL/账号塞进无结构的 note。用户需要在同一条记录中维护多个值，并明确区分默认隐藏的密钥与直接显示的普通字符串。

该改动影响 JSON 数据格式、CLI 默认取值、Web API 明文边界和 Vue 编辑体验，必须同时保证旧数据可读、列表/搜索不泄露、迁移可恢复。

## 决策

1. DB 版本升级为 `1.1`，每条记录使用有序 `fields[]`：
   - `label`: 1-64 字符，同一记录内大小写不敏感唯一。
   - `kind`: 只允许 `secret` 或 `text`。
   - `value`: 非空字符串，可含换行。
   - `primary`: 恰好一个为 true，且必须属于 secret。
2. JSON 只持久化 `fields`，不重复持久化顶层 `value`。`SecretEntry.value` 和详情 API 的 `value` 保留为从 primary secret 计算出的兼容别名。
3. 读取 1.0 顶层 `value` 时，在内存映射为 label=`密钥` 的 primary secret。只读不改盘；第一次成功写入 1.1 前自动保存一个原样 v1.0 备份。
4. `SecretStore.set/update` 与 POST/PATCH 继续接受旧 `value`。同一调用同时提供 `value` 和 `fields` 属于歧义输入，必须拒绝。
5. PATCH 使用完整 fields 数组替换。所有字段先集中校验，再一次原子写入；本期不增加单字段 REST 路由。
6. `x secret get` 默认取 primary secret，并保留旧多行 value 的剪贴板 key 提取行为；`--field <label>` 精确取得指定字段。
7. 列表 summary 和 search 都不读取、返回或匹配任何字段值，包括 kind=text 的 URL/账号。
8. Web 查看与编辑在请求完整 fields 前确认安全提示。secret 逐字段掩码，text 直接显示；显示策略不代表落盘加密。

## 备选方案

- **继续把 URL/账号写入 note**：无法稳定区分、复制、校验或排序，否决。
- **把所有内容塞进多行 value 并由前端解析**：格式靠猜测，字段名和类型不可验证，否决。
- **同时持久化 value 与 fields**：旧客户端方便，但双写必然产生主密钥漂移风险，否决。
- **启动时强制迁移整库**：只读命令也会改盘，失败影响面大，否决。
- **每字段单独 REST 资源**：扩展性高，但本地单用户 MVP 无需额外路由和并发语义，暂缓。
- **列表/搜索普通文本字段**：URL 也可能带 token 或隐私信息，统一不进入 summary/search 更安全，否决。

## 影响

- 旧 1.0 DB 无需手工迁移，第一次写入会产生可恢复备份。
- 新版写出的 1.1 DB 不能交给只理解顶层 value 的旧版 x-cli；需要降级时必须恢复 v1.0 备份。
- Python 运行时继续 stdlib-only，不引入加密或 schema 第三方库。
- CLI set/update 的旧脚本继续可用，但多字段增删/重排本期只在 Web/API 提供。
- Web 详情响应包含所有字段明文，因此仍属于敏感端点；列表响应继续使用严格白名单。

## 不变量

- `x secret list`、`x secret search` 和 `GET /api/secrets` 不泄露任何字段值。
- 密钥明文离开存储时保留 stderr/浏览器安全提示。
- 写入采用临时文件 + `os.replace`，迁移备份失败不得覆盖原 DB。
- 未知 JSON 字段通过 `SecretEntry.extra` 往返保留。
