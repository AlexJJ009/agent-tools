# Win11 Proxy Relay

Portable Windows runtime for the dedicated v2rayN/sing-box relay used by a Windows laptop to keep a local development proxy and a reverse SSH tunnel alive.

The public package contains only runtime source, installer/control entrypoints, `relay.cmd`, this README, and `support/codex_target_guard.py`. It must not contain `state/`, private `server-config.json`, v2rayN databases, generated caches, logs, SSH keys, or copied user profiles.

## Install Shape

The installer writes:

- `InstallRoot\settings.json`
- `InstallRoot\runtime\*`
- `InstallRoot\state\server-config.json` when a private config is imported
- `InstallRoot\state\ssh_config` and `InstallRoot\state\known_hosts`

`settings.json` is the runtime contract. The Python scripts read it through `--settings`; PowerShell scripts read it through `-SettingsPath`. When omitted, both loaders use `runtime\..\settings.json`.

Supported settings fields:

- `v2rayn_dir`
- `core_exe`
- `ssh_host`
- `ssh_config`
- `ssh_identity_file`
- `ssh_known_hosts`
- `local_proxy_port`
- `remote_proxy_port`
- `controller_port`
- `main_controller_ports`
- `main_ai_subscriptions`
- `state_dir`
- `owner_home`
- `python_exe`
- `startup_mode`
- `ai_primary_port`
- `ai_fallback_port`
- `ai_measure_port`
- `feitu_measure_port`

## Startup Mode

`-StartupMode Logon` registers all four tasks for the interactive owner account. This is the default and is easiest to debug because the tasks inherit a normal user session after login.

`-StartupMode Boot` registers the server proxy, reverse tunnel, and quality manager as SYSTEM startup tasks. The interactive AI fallback task is preserved as a user logon task when it already exists, because it manages the interactive main v2rayN AI selector. Boot mode requires elevated PowerShell during installation and uses an installer-generated service SSH config so the runtime does not depend on `~\.ssh` under SYSTEM.

No user password is stored for either mode.

## Private Migration

Private relay config is imported separately with `-PrivateConfig <path>`. The installer copies the JSON into `state\server-config.json`, rewrites its sing-box cache path to `state\server-cache.db`, and records a schema snapshot. The public ZIP does not export subscription data, node credentials, v2rayN DB files, or SSH private keys.

When `runtime\build-configs.py` is used for private migration, it reads the local v2rayN DB in read-only mode and stages a server-only sing-box config from enabled `feitu` and `miaomiao` subscriptions. Selector tags remain `server-feitu`, `feitu-quality`, `feitu-measure`, and `feitu-auto`; leaf tags use `feitu-*` and `miaomiao-*`. Taiwan rows and subscription metadata/error rows are excluded, including rows such as `当出现较长时间error时...`.

The main v2rayN AI pool has a separate source contract. Set `main_ai_subscriptions`
to the enabled subscription names that should appear under `us-ai-auto-READONLY`
(for example `["搬瓦工"]`). A `--with-main-templates` build fails when this list is
empty. Each build deletes the previous AI leaf members and reconstructs
`us-ai-auto-READONLY`, `ai-quality`, and `ai-measure` from the current subscription
rows. Old template nodes are never inherited. The generated
`state\main-ai-source.json` and `state\main-ai-node-labels.json` are the auditable,
credential-free record of that decision; the v2rayN database remains the private
node source of truth.

AI leaf tags are stable SHA-256-derived identifiers built from the subscription
name and the node's non-secret network identity. They must not use v2rayN
`IndexId`: v2rayN assigns fresh IDs and may reorder rows after every subscription
refresh. Credential rotation at the same named endpoint preserves its tag, while
an address, port, protocol, SNI, or other routing-identity change produces a new
tag. Duplicate stable identities fail the build instead of silently sharing a
selector tag.

The human-facing `us-ai` selector intentionally exposes only two choices:
`ai-auto-fallback` and the current ordinary `proxy`. `ai-quality`, `ai-measure`,
and `us-ai-auto-READONLY` remain internal because the reliability manager needs
separate production, isolated-measurement, and native-delay paths. The bundled
dashboard hides those internal groups under a collapsed diagnostic section.
Use `build-configs.py --with-main-templates --main-only` when refreshing this
pool on a live machine; it stages the main normal/TUN templates without
rewriting the dedicated PHAI relay `server-config.json`.

For SSH, the installer resolves the owner account's host alias with `ssh -G`, copies only `known_hosts`, and writes `state\ssh_config` with absolute paths. The private key remains at the resolved `IdentityFile`; it is referenced, not copied into the package.

## Runtime Behavior

`runtime\run-server-proxy.ps1` supervises the dedicated sing-box process using `settings.core_exe` and `state\server-config.json`.

`runtime\phai-reverse-proxy.ps1` supervises:

```text
ssh -N -T -F state\ssh_config -R 127.0.0.1:<remote_proxy_port>:127.0.0.1:<local_proxy_port> <ssh_host>
```

It also passes explicit `IdentityFile` and `UserKnownHostsFile` options when those fields are present in settings.

`runtime\quality-manager.py` and `runtime\ai-fallback.py` use Clash-compatible controller GET/PUT calls and fresh HTTP(S) probes. Their retry loops only repeat selector reads, selector writes with readback, and idempotent GET probes. They do not replay application CONNECT streams or user requests.

`runtime\probe.py` is the bounded canary used by Doctor. It performs no retries and exits 1 on any failed payload check. `control.ps1 -Action Doctor` runs it once through the laptop proxy, then streams the same script to the PHAI host over SSH stdin and runs it against the reverse tunnel port.

The Hy2 path is limited to the notebook-node leg handled by the private v2rayN/sing-box configuration. The relay runtime does not synthesize or broaden Hy2 routing rules.

## Build Package

From the repository root:

```powershell
python tools\win11-proxy-relay\build-package.py
```

The script writes `tools\win11-proxy-relay\dist\win11-proxy-relay.zip` and a sidecar `win11-proxy-relay.SHA256SUMS.json`. The ZIP also contains `SHA256SUMS.json`.

The builder uses an explicit file allowlist and rejects cache, DB, log, state, private config, SSH config, and key-like outputs.

## 日常入口与迁移步骤

安装完成后运行 `InstallRoot\relay.cmd`，菜单提供 Status、Start、Stop、Restart、Doctor、Dashboard。也可以直接运行 `control.ps1 -Action Status`。Boot 模式的启停需要正常 UAC 提权；无需保留可见的 PowerShell 窗口。不要按进程名批量结束 PowerShell 或 SSH，其他终端、编辑器和隧道也使用这些程序。

迁移到另一台 Win11：

1. 安装 Python 3.10+、Windows OpenSSH Client 和兼容的 sing-box（当前验证版本 1.13.4），解压公开 ZIP。
2. 在新机器生成自己的 SSH key，并在开发服务器授权。配置 SSH alias，先确认 `ssh -o BatchMode=yes <alias> true` 成功；确认已核验服务器主机密钥。不要为了省事关闭主机密钥校验。
3. 单独传递私有 `server-config.json`。该文件含节点凭据，不属于公开包；可选同目录 `node-labels.json` 用于面板中文名称。不要复制 Codex、CC Switch 的认证文件或整个 Windows 用户目录。
4. 以管理员 PowerShell 执行（路径替换为实际路径）：

```powershell
.\install.ps1 -InstallRoot 'C:\Program Files\Win11ProxyRelay' `
  -CoreExe 'C:\Tools\sing-box\sing-box.exe' `
  -PythonExe 'C:\Tools\Python\python.exe' `
  -SshHost 'dev-server' `
  -MainAiSubscriptions '搬瓦工' `
  -PrivateConfig 'C:\Private\server-config.json' `
  -StartupMode Boot -Start
```

可先加 `-Plan` 检查解析结果，不修改任务。Boot 会复制 Python 和 sing-box 到受保护的安装目录，升级原安装不会自动升级服务副本；更新服务请重新安装并验证。不要同时让两台笔记本争用同一个远端 `17890`，迁移时先停止旧机器的 relay，或为试运行配置不同端口。

5. 执行 `control.ps1 -Action Doctor`。三个网站均成功才算这一轮 HTTPS 验收通过；再从实际容器执行其启动前检查。随后在可中断时安排一次重启、未登录验收。任务显示 Running 不能代替这些检查。

电脑必须开机、联网且不休眠。插电常驻可选 `-KeepAwakeOnAC`，它会调整插电休眠和合盖行为；默认不修改电源设置。电脑关机、断网或所有节点故障时，无法保证代理可用。

安装前会保存旧任务 XML 与已有配置到 `state\backup-*`。安装报错会尝试恢复。手工回退应在管理员 PowerShell 中停止三个 relay 任务，再用备份 XML 的 `Register-ScheduledTask -TaskName <名称> -Xml (Get-Content <备份.xml> -Raw) -Force` 恢复任务，恢复同目录配置后再启动；保留旧安装目录直到验收完成。回退不是删除所有 PowerShell 进程。

## 重试与节点切换

下载客户端可以为 GET/HEAD 配置有限重试：例如最多 4 次、指数退避并增加随机抖动、总期限 2 分钟；大文件用断点续传并核验哈希。TCP/TLS 断开、429（遵守 Retry-After）及部分 5xx 可重试。404、指定版本不存在、认证失败不能通过反复切节点修好，也不应据此惩罚节点。

切换节点后，客户端必须重新建立请求。代理无法安全重放加密 CONNECT 内的 HTTPS 内容；POST、模型生成和已有部分输出的请求可能重复计费或重复操作，须由调用端依据幂等键或业务协议决定重试。SSH keepalive 和自动重连只能恢复通道，不会恢复已经失败的下载。

选节点先要求目标站真实 HTTPS 内容成功，再比较吞吐量、请求失败比例和延时抖动。新加坡可作为候选偏好，但地区不能代替实测。当前台湾节点排除策略保存在 `runtime\feitu-node-policy.json`，生成配置时生效；外部导入的配置也应先检查候选列表。

Hysteria2 使用 QUIC/UDP，只改变笔记本到节点这一段，开发机到笔记本的 OpenSSH 仍是 TCP。需要订阅实际提供 Hysteria2 服务，不能把 AnyTLS 配置改名当成 Hy2。先用同一批 HF/PyPI 下载进行端到端对照测试，再决定是否迁移。

服务升级采用新的版本目录（例如 `C:\Program Files\Win11ProxyRelay-v2`），导入旧私有配置后替换同名任务；安装器拒绝覆盖已有 settings.json 的目录，以保留可回退的旧程序。Boot 安装目录的父目录也必须由管理员控制，推荐 Program Files。

## 双订阅自动回退

开发机候选包含 `feitu` 和 `miaomiao`。保留旧 API selector 标签以兼容既有工具，面板显示“飞兔优先 / 喵喵备用”。先要求实际 HF/PyPI/Cloudflare 内容成功，合格的飞兔优先；没有合格飞兔时使用喵喵。两个订阅都无合格节点时记录故障，不声称恢复。手动指定外层节点时，健康管理器不会擅自覆盖用户选择。

正常评估与紧急恢复都为备用订阅保留候选位置。内容验证在测速前执行，失败节点不会耗掉备用的测速预算。Cloudflare 测速端点返回 403/404 时，开发机策略改用 HF tokenizer 的完整文件、字节数和词表结构验证吞吐量；这不等于饱和带宽测试。AI 的原有测速策略不变。

更新订阅后重新生成私有配置并执行核心校验，再重载专用核心；不要只修改 API 中临时选项。VLESS REALITY 转换保留 ProtoExtra.Flow、xudp 和 uTLS 参数。后台 Python 任务在可用时使用 pythonw.exe，PowerShell 使用隐藏窗口；已有任务定义的更新可能需要管理员权限。
