# LLM 调用审计日志

> 范围：`xiaoyi_metrics/shared/` 下所有大模型调用的统一审计日志机制。
>
> eval_server 里所有 LLM 裁判调用都汇聚到单一入口 `shared/llm_client.py:call_llm()`。本机制在该入口处为**每次调用**（成功或失败）写一条 JSONL 审计日志，记录 token、原始请求（剥离 base64）、原始响应、失败原因，供事后回溯与排障。

---

## 0. 设计决策（用户确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 保存位置 | eval_server **文件日志**（JSONL，按日） | eval_server 无 SQL DB（任务也是按日 JSON 文件）；与评估结果流解耦，不污染 calculator 结果、不写主应用 DB |
| 与应用日志关系 | **完全分开**，单独目录 | 不与 `eval_server.log`（`LOG_DIR`）混在一起，独立可查 |
| base64 音视频 | **剥离为占位符**（保留字节数） | 一次音频请求可达几十 MB，原样落盘撑爆磁盘；占位符 + 全部文本 prompt/元数据保留，够审计够调试 |
| 保留策略 | **永不删除 / 不轮转** | 用户明确要求"都保留下来不要删除" |
| 成功/失败 | **都记**，失败记原因后原样 raise | 失败也要可追溯；但必须 raise 保留，评估"按原逻辑失败"行为不变 |
| 日志自身失败 | 只 warning，**绝不抛** | 日志不能影响评估 |

---

## 1. 配置

`eval_server/app/config.py`：

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `LLM_CALL_LOG_DIR` | `static/eval_server/llm_call_logs` | 日志目录，按日一个 `.jsonl` 文件 |
| `LLM_CALL_LOG_ENABLED` | `True` | 开关，env `LLM_CALL_LOG_ENABLED=0` 可关（**改 env 需重启 eval_server 生效**，非热切） |

---

## 2. 日志文件与条目结构

### 文件位置
```
static/eval_server/llm_call_logs/<YYYY-MM-DD>.jsonl
```
每行一条 JSON，`ensure_ascii=False`（中文直出），追加写。

### 条目结构
```json
{
  "ts": "2026-09-07T11:07:18.886589",
  "model": "gpt-5.6-sol",
  "status": "success",                       // "success" | "failed"
  "attempts": 1,                             // 实际发起的 HTTP 请求次数（含重试）
  "tokens": {"input": 123, "output": 456, "total": 579},  // 失败时全 0
  "raw_request": { /* 剥离 base64 后的完整 payload */ },
  "raw_response": { /* 成功：choices + usage；失败：null */ },
  "error": {                                 // 失败时填，成功为 null
    "type": "HTTPStatusError",
    "message": "Client error '401 Unauthorized' ...",
    "status_code": 401,                      // 仅 HTTPStatusError 有
    "body_snippet": "{\"error\":{...}}"      // 仅 HTTPStatusError 有，响应体前 500 字
  },
  "context": {"dimension": "interruption_judge"}  // 调用方传入，可选
}
```

### `raw_request` 剥离规则（`_sanitize`）
深拷贝 payload 后遍历：
- `input_audio.data`（纯 base64 音频，同级有 `format` 键标识）→ `<base64 omitted, N chars>`
- `image_url.url` 以 `data:` 开头（base64 视频/图片 data URI）→ `<data uri omitted, N chars>`
- 其余字段（`model` / `messages` / 文本 `text` / `max_tokens` / `temperature` / `response_format` 等）**原样保留**

> 深拷贝确保不污染原 payload——后续重试仍用未剥离的原 payload 发送。

---

## 3. 接入点：`call_llm()`

`shared/llm_client.py:call_llm()` 新增可选参数 `log_context: Optional[dict] = None`，签名其余不变，**返回 dict 也不变**（仍只含 `content/tokens_used/input_token/output_token`，不污染 calculator 结果结构）。

### 运行逻辑
```
call_llm(...)
  ├─ 构 payload（含 base64 音视频）
  ├─ attempts_made = 0
  ├─ try:
  │    └─ for attempt in range(max_retries+1):
  │         attempts_made = attempt+1
  │         POST /chat/completions
  │         ├─ 成功 → 解析 data(choices+usage) → break
  │         └─ 失败 → 原重试逻辑（429/5xx 退避重试，其余立即 raise）
  │    else: raise last_exc                      # 重试耗尽
  ├─ except Exception as e:                      # 任何逃逸异常
  │    log_llm_call(..., status='failed',
  │                 error=_extract_error(e),     # HTTPStatusError→status_code+body_snippet
  │                 attempts=attempts_made)
  │    raise                                     # 原样抛出，评估按原逻辑失败
  └─ log_llm_call(..., status='success',        # 成功
                   error=None, attempts=attempts_made)
     return {content, tokens_used, input_token, output_token}   # 不变
```

### `_extract_error(e)` 失败原因提取
| 异常类型 | error 字段 |
|----------|-----------|
| `httpx.HTTPStatusError` | `type` + `message` + `status_code` + `body_snippet`(响应体前 500 字) |
| `httpx.RequestError` 及其他 | `type` + `message` |

---

## 4. 调用方上下文（`log_context`）

各 calculator 在调 `call_llm` 时传入 `log_context` 标注来源，便于审计定位：

| caller 文件 | log_context |
|-------------|-------------|
| `llm_judge/strategy.py` `_score_one` | `{'dimension': 'llm_judge'}` |
| `llm_judge/llm_judge_calculator.py` `evaluate_with_llm` | `{'dimension': 'llm_judge'}` |
| `env_judge/interruption_judge.py`（每用例一次，含行为分类/内容评分/停止遵从） | `{'dimension': 'interruption_judge'}` |
| `env_judge/rejection_judge.py` | `{'dimension': 'rejection_judge'}` |
| `turn_taking/high_freq_llm_judge.py` | `{'dimension': 'high_freq_llm_judge'}` |

> `log_context` 为可选参数（默认 None），不传也不影响日志写入（只是 `context` 字段为空）。

---

## 5. 并发与线程安全

- `call_llm` 在 eval_server 的 `ThreadPoolExecutor`（各维度并发 10）下被并发调用。
- `llm_call_logger.py` 模块级 `threading.Lock` 保护文件追加写，单进程内并发安全。
- 当前 eval_server 是单 waitress 进程 + 线程池，锁有效；若将来改多进程部署，需另加跨进程锁。

---

## 6. 验证

1. **单元（sanitize）**：5000 字符 base64 → `<base64 omitted, 5000 chars>`，text 原样，断言无 base64 残留。
2. **失败路径（真 401）**：`attempts=1`（401 不重试）、`error.status_code=401`、`body_snippet` 含真实 API 错误体、`raw_response=null`、评估仍按原逻辑失败。
3. **失败路径（不可达端点）**：`ConnectError`、`attempts=4`（重试 3 次）、原样 raise。
4. **成功路径**：换有效 key 后跑一次打断裁判评估（或 `PYTHONPATH=. python -m app.services.calculators.xiaoyi_metrics.env_judge.interruption_judge <ai_wav> --user_wav <user_wav>`），看 JSONL 出现 `status=success` + 真实 token 数 + `raw_response`（choices+usage）。
5. **开关**：`LLM_CALL_LOG_ENABLED=0` 重启后跑一次，确认不生成文件、评估正常。

---

## 7. 注意事项

- **磁盘增长**：永不轮转，按日文件持续增长。如将来需保留期策略可再加，当前按用户硬要求不做。
- **`false_takeover.py` 未接入**：该文件有独立死代码 bug（`from ..interruptbility.interruption_llm import _call_llm_json` 拼写错 + 引用已删函数；`interruptibility/interruption_llm.py` 现已整体删除），其 LLM 路径本就跑不起来，不在本机制覆盖内，需单独修复。
- **omni 流式模型 token**：若某模型不回 `usage` chunk，`tokens` 会静默记 0（不崩）。换新模型后建议先确认日志里 token 非零。
- **token 已在 `call_llm` 返回值里**：本机制额外把 token 落到文件日志；calculator 结果结构里的 token 字段（部分 caller 有、部分丢）未改动——如需在主应用 UI 按维度看 token，可另加"token 汇总回流"链路。

---

## 8. 相关文件

| 文件 | 作用 |
|------|------|
| `shared/llm_call_logger.py` | `_sanitize()` 剥离 base64 + `log_llm_call()` 写 JSONL（锁保护） |
| `shared/llm_client.py` | `call_llm()` 接入日志（成功失败都记）+ `_extract_error()` |
| `eval_server/app/config.py` | `LLM_CALL_LOG_DIR` / `LLM_CALL_LOG_ENABLED` |
| 各 calculator | 传 `log_context` 标注来源维度 |

## 关联文档
- [[../README.md]] — xiaoyi_metrics 总览
- [[interruption_io.md]] — 打断入参/出参（含 LLM 评估链路）
- [[API.md]] — eval_server 对外 API
