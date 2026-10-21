# 智能音频测试（Intelligent Audio Test）平台能力

通过本 skill / MCP，外部 agent（Claude Code / Codex 等）可以调用智能音频测试平台的业务能力：任务、测试用例、音频、被测设备、评估维度、报告、算法、标签、用例分组等。

## 配置

两个环境变量（或在你使用工具时按需提供）：

- `INTELLIGENT_AUDIO_TEST_BASE_URL`：平台服务地址，默认为 `{{BASE_URL}}`。多网络环境下可改为你实际可访问的地址（IP 或 http(s) 链接）。
- `INTELLIGENT_AUDIO_TEST_ACCESS_TOKEN`：你的 Access Token（在平台「个人配置页」创建，创建时明文仅显示一次）。权限 scopes 与有效时间在创建时配置。

> 注意：Access Token 只存哈希、明文仅显示一次，请妥善保存。

## 认证方式

所有请求都通过 `Authorization: Bearer <ACCESS_TOKEN>` 头携带 Access Token 调用：

```bash
curl -H "Authorization: Bearer $INTELLIGENT_AUDIO_TEST_ACCESS_TOKEN" \
  "$INTELLIGENT_AUDIO_TEST_BASE_URL/api/v1/tasks"
```

同一 Access Token 在 skill（curl 指令）与 MCP 两种方式下通用。

## 能力覆盖

平台能力经 skill / MCP 暴露，覆盖业务能力、排除个人信息与系统设置：

- **覆盖**：任务（task）、测试用例（testcase）、音频（audio）、被测设备（device）、评估维度（evaluation）、报告（report）、算法（algorithm）、标签（tag）、用例分组（group）、数据可见性分享（*:share）、数据转移（task 导入导出）、收藏/回收站、Benchmark 排行、Report Studio、日志只读（log:read）。
- **除外**：用户/角色/权限/ OAuth 提供方管理（系统设置）、个人信息（auth me/self/改密/OAuth 绑定）、系统选项（option）、系统健康/状态、日志管理类（log:manage/log:websocket）、SSE 长连接推送。

## 常用示例（curl）

```bash
BASE_URL="${INTELLIGENT_AUDIO_TEST_BASE_URL:-{{BASE_URL}}}"
TOKEN="${INTELLIGENT_AUDIO_TEST_ACCESS_TOKEN}"

# 列出任务
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/tasks"

# 任务详情
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/tasks/1"

# 列出测试用例
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/testcases?keyword=唤醒"

# 音频列表
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/audios"

# 报告列表
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/reports"

# 被测设备列表
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/test-devices"
```

写操作示例（权限不足会返回 403）：

```bash
# 创建标签
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"新标签"}' "$BASE_URL/api/v1/tags"
```

## MCP 配置

`mcp.json`（同目录）为 MCP 配置模板，URL 指向本平台的 MCP 端点。在支持 MCP 的客户端（如 Claude Code）中按客户端方式添加远程 MCP：

```json
{
  "name": "intelligent-audio-test",
  "description": "智能音频测试平台 MCP（联接你的 agent）",
  "type": "http",
  "url": "{{BASE_URL}}/api/v1/mcp",
  "headers": {
    "Authorization": "Bearer 在此填入你的 Access Token"
  }
}
```

MCP 端点实现 JSON-RPC 2.0 协议：`initialize` / `tools/list` / `tools/call`。工具清单与覆盖能力一致（`tools/list` 返回全部工具及入参 Schema）。同一 Access Token 与 skill 通用。

## 注意事项

- token scopes 不含某能力所需权限时，调用会被拒绝（403 越权语义）。
- 个人信息与系统设置类接口不在覆盖范围，MCP 工具清单中不提供。
- 服务地址 `{{BASE_URL}}` 默认取你下载时的站点地址；如网络环境不同，请修改为实际可访问的地址。
