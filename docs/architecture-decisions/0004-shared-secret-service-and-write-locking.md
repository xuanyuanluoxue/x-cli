# ADR 0004: CLI 与 Web 共享密钥业务层并在存储边界串行写入

- 状态：已接受
- 日期：2026-07-19

## 背景

CLI 的每个 `x secret` handler 与 Web 的密钥 REST handler 都直接调用 `SecretStore`。两端虽然读写同一个 `secrets.json`，但没有统一的应用业务入口，后续规则很容易只在一端生效。同时，`SecretStore` 只通过临时文件加 `os.replace` 保证单次写入原子性；CLI 进程与 `x web` 进程若同时执行“读取—修改—写回”，后写者仍可能覆盖先写者的成功结果。

统一不能以“CLI 改调 localhost HTTP”为代价。`x secret` 必须在 Web 服务未启动、端口不可用或认证配置不同的情况下继续工作。

## 决策

1. 新增 `core.secret_service.SecretService`，作为 CLI 与 Web 共同使用的应用业务 API。依赖方向固定为：

   ```text
   CLI adapter ─┐
                ├─> SecretService ─> SecretStore ─> secrets.json
   Web adapter ─┘
   ```

2. `SecretService` 提供 list/get/find/search/create/update/delete/import/export，并透传领域异常。它不包含 argparse、剪贴板、HTTP 状态码、JSON 响应或安全提示等适配器逻辑。
3. `SecretStore` 继续负责 JSON schema、字段校验、迁移备份和原子落盘。CLI 与 Web 生产代码不再直接发起密钥 CRUD；WebServer 仍保留 `secrets` 存储别名，兼容既有注入和测试代码。
4. 并发控制放在 `SecretStore` 的完整读—校验—写事务外层，而不是只锁 `_save` 或只锁 `SecretService`。这样不同进程、不同服务实例也能协调。
5. 每个 DB 使用同目录 sidecar 文件 `<db 文件名>.lock`：
   - 进程内先取得按规范化 DB 路径共享的 `threading.RLock`；
   - Windows 使用 `msvcrt.locking`，POSIX 使用 `fcntl.flock` 取得 1 字节排他锁；
   - `_init_db`、set、update、delete、import 的完整事务都在锁内；
   - 等待超时转换为 `SecretError`，锁在 `finally` 中释放，进程退出时由操作系统释放；
   - sidecar 只保存一个占位字节，绝不保存名称、字段或密钥值。
6. 只读 list/get/find/search/export 不持有事务锁。DB 最终写入仍使用临时文件加 `os.replace`，因此读取者只会看到写入前或写入后的完整版本。

## 备选方案

- **CLI 统一调用 Web REST API**：表面上只有一套接口，但会让所有 CLI 操作依赖后台服务、端口和 Web 认证，否决。
- **继续让两端直接调用 SecretStore**：改动最小，却无法建立稳定的业务扩展边界，否决。
- **只在 SecretService 中使用线程锁**：只能保护同一 Python 进程中的同一 service，无法协调独立 CLI 与 Web 进程，否决。
- **只锁 `_save`**：两个进程仍能先读到同一旧快照，随后依次写回并丢失更新，否决。
- **改用 SQLite**：自带事务能力，但会引入数据迁移、备份格式和手工可读性的显著变化；当前单用户 JSON 规模不需要，暂缓。
- **把所有展示/HTTP 错误也放进 service**：会把业务层绑定到具体入口，降低复用性，否决。

## 影响

- CLI 与 Web 在业务入口上统一，但仍保留各自合适的交互协议和错误呈现。
- CLI 无需启动 Web；Web 也无需通过子进程调用 CLI。
- 同一 DB 的成功写操作会串行执行，不再因 CLI/Web 同时写入而静默丢失。
- 数据目录会多出一个无敏感信息的 `.lock` sidecar 文件；它可以长期保留，不代表服务仍在运行。
- 锁等待可能让并发命令短暂阻塞；异常持锁进程退出后操作系统会自动释放锁。
- 继续保持 Python 运行时零第三方依赖。

## 不变量

- `x secret list`、`x secret search`、`GET /api/secrets` 不返回或匹配任何字段值。
- 明文详情离开存储时仍由 CLI/Web 适配器显示安全提示。
- schema 1.0 首次写入前的原样备份顺序与失败保护不变。
- 未知 JSON 字段继续通过 `SecretEntry.extra` 往返保留。
- Web 的 HTTP 状态码与 CLI 的退出码属于适配器契约，不由 service 混合处理。
