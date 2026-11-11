# wechat-mac-tool (`wxmac`)

本地导出 macOS 版微信 4.x 的聊天记录和图片：数据库 → SQLite、图片解密（含 wxgf/HEVC 转 JPG）、只读 MCP 服务。
Local export toolkit for WeChat 4.x on macOS: databases → SQLite, image decryption (incl. wxgf/HEVC → JPG), and a read-only MCP server.

> 只用于导出**你自己**设备上**你自己**的数据。Only for exporting your own data on your own Mac.

## 命令 / Commands

| 命令 | 作用 | What it does |
|---|---|---|
| `wxmac keys` | 说明如何提取密钥；`wxmac keys extract` 用 sudo 运行内置的 wcdb-key-tool | Key setup instructions; `wxmac keys extract` runs the bundled wcdb-key-tool under sudo |
| `wxmac export` | 用已保存的密钥解密数据库，重建 `export/wechat.sqlite`（无需 sudo，不会登出） | Decrypt DBs with saved keys, rebuild `export/wechat.sqlite` (no sudo, no logout) |
| `wxmac images` | 增量解密图片到 `export/images/<聊天名>/<yyyy-mm>/` | Incrementally decrypt images into `export/images/<chat>/<yyyy-mm>/` |
| `wxmac sync` | export + images，若设置 `WXMAC_SYNC_DEST` 再 rsync | export + images, then rsync if `WXMAC_SYNC_DEST` is set |
| `wxmac mcp` | 只读 MCP 服务（`mode=ro`） | Read-only MCP server over the export |
| `wxmac paths` | 打印解析后的路径（不显示密钥） | Print resolved paths (never key contents) |

`wxmac images` 选项 / options: `--chat <md5(chat_id)>`, `--month YYYY-MM`, `--out DIR`, `--keep-wxgf`, `--qr`（用 zbarimg 扫二维码，写入 `<out>/qr.tsv` / scan QR codes with zbarimg into `<out>/qr.tsv`）。

## 安装 / Install

```sh
brew install ffmpeg zbar          # ffmpeg: wxgf→jpg；zbar 可选 / optional, for --qr
xcode-select --install            # lldb，仅提取密钥时需要 / only for key extraction
git clone https://github.com/whan6023/wechat-mac-tool && cd wechat-mac-tool
python3 -m pip install -e .       # 或 / or: pip install -e '.[mcp]'
# 不安装也可以直接跑 / or run without installing:  ./bin/wxmac --help
```

依赖 / Requirements: Python ≥ 3.9, `cryptography`, `zstandard`; `ffmpeg`（wxgf 图片）, 可选 / optional `zbar`, `mcp<2`.

## 密钥放在哪里 / Where keys live

密钥**只存在本机**，默认在 `~/wcdb-key-tool/`（`WXMAC_HOME`）：
Keys live **only on your Mac**, by default in `~/wcdb-key-tool/` (`WXMAC_HOME`):

| 文件 / File | 内容 / Contents |
|---|---|
| `all_keys.json` | 数据库密钥，由 `wxmac keys extract` 生成 / database keys from `wxmac keys extract` |
| `image_key.bin` | 16 字节图片 AES 密钥（V2 `.dat`），需另行获取 / 16-byte image AES key for V2 `.dat`, obtain separately |

- **密钥永远不进 git。** `.gitignore` 已排除密钥、`*.bin`、`*.json` 密钥文件、`export/`、`decrypted/`、`daily/`、图片和所有 `*.sqlite` / `*.db`。不要把密钥贴到 issue、聊天或日志里。
- **Keys never go into git.** `.gitignore` excludes key files, `*.bin`, key `*.json`, `export/`, `decrypted/`, `daily/`, images and every `*.sqlite` / `*.db`. Never paste keys into issues, chats or logs.
- 代码里没有任何写死的密钥或账号信息：运行时读取上面的文件或环境变量。V2 图片的 XOR 字节每个账号固定，运行时从缩略图（`*_t.dat`，JPEG 以 `FF D9` 结尾）推算，不保存。
- No key or account identifier is hardcoded; everything is read at runtime. The per-account V2 XOR byte is derived at runtime from thumbnails (`*_t.dat` are JPEGs ending in `FF D9`) and never stored.

### 提取数据库密钥 / Extracting database keys

```sh
sudo codesign --force --deep --sign - /Applications/WeChat.app   # 每次微信自动更新后可能要重做 / redo after WeChat updates
# 重启微信 / restart WeChat
wxmac keys extract        # 4.1.10+ 会要求重新登录 / will ask you to log in again
```

## 配置 / Configuration (env vars)

| 变量 / Variable | 默认 / Default |
|---|---|
| `WXMAC_HOME` | `~/wcdb-key-tool` |
| `WXMAC_KEYS` | `$WXMAC_HOME/all_keys.json` |
| `WXMAC_IMAGE_KEY_FILE` / `WXMAC_IMAGE_KEY` | `$WXMAC_HOME/image_key.bin` |
| `WXMAC_ACCOUNT_DIR` | 自动发现 / auto: newest `~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/*/` with `db_storage/` |
| `WXMAC_EXPORT` | `$WXMAC_HOME/export/wechat.sqlite` |
| `WXMAC_DECRYPTED` | `$WXMAC_HOME/daily` |
| `WXMAC_IMAGES` | `$WXMAC_HOME/export/images` |
| `WXMAC_IMAGE_XOR` | 自动推算 / derived from thumbnails |
| `WXMAC_SYNC_DEST` | 不同步 / none (rsync target, e.g. `host:~/wechat-mcp/data/wechat.sqlite`) |
| `WXMAC_KEY_TOOL` | 内置 / bundled `third_party/wcdb_key_tool/wcdb_key_tool_macos.py` |

默认路径和旧脚本一致，已有的 LaunchAgent 读 `export/wechat.sqlite` 不受影响。
Defaults match the earlier scripts, so anything reading `export/wechat.sqlite` keeps working.

## 导出格式 / Export schema

```sql
message(id INTEGER PRIMARY KEY, ts INTEGER, chat_id TEXT, chat TEXT, sender TEXT, kind TEXT, text TEXT)
chat(chat_id TEXT PRIMARY KEY, chat TEXT, n INTEGER, last_ts INTEGER)
```

`kind = 3` 是图片，`text` 里是带 md5 的 img XML。图片目录 `msg/attach/<md5(chat_id)>/<yyyy-mm>/Img/`。
`kind = 3` is an image; `text` holds its img XML with an md5. Images live under `msg/attach/<md5(chat_id)>/<yyyy-mm>/Img/`.

## 定时运行 / Scheduling

用 launchd 每小时跑 `wxmac sync`（或 `wxmac export`）。示例 / Example `~/Library/LaunchAgents/local.wxmac.sync.plist`:

```xml
<plist version="1.0"><dict>
  <key>Label</key><string>local.wxmac.sync</string>
  <key>ProgramArguments</key><array><string>/opt/homebrew/bin/wxmac</string><string>sync</string></array>
  <key>StartInterval</key><integer>3600</integer>
</dict></plist>
```

## MCP

```sh
uv run --with "mcp<2" --with-editable . wxmac mcp
```

工具 / Tools: `export_status`, `list_chats`, `search_messages`, `read_chat`（全部只读 / all read-only）。

## 第三方 / Third party

`third_party/wcdb_key_tool/wcdb_key_tool_macos.py` 原样来自 / is an unmodified copy of
[TANGandXUE/wcdb-key-tool](https://github.com/TANGandXUE/wcdb-key-tool), © 2025 CloudDreamAI / TANGandXUE, MIT License
(见 / see `third_party/wcdb_key_tool/LICENSE` 和 `NOTICE.md`)。

## License

MIT（本项目代码 / this project's code）。第三方代码遵循其自身许可证 / third-party code keeps its own license.
