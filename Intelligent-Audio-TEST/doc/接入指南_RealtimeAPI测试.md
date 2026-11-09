# 接入指南 · Realtime API 测试（websocket_api）

> 受众：接入新被测 Realtime API（WebSocket 实时会话接口）的开发者。
> 核心原则：**执行器通用，特殊处理固定三处落点（适配器 / 配置 / 评估计算器）**，与 E2E「通用 executor + 特殊全在 driver」同构。

## 一、接入总览（3 件事）

| 你要做的事 | 放哪 | 写代码？ |
| --- | --- | --- |
| ① 厂商协议适配器（WS 事件/握手/输出） | `api_test_service/infrastructure/adapters/vendors/你的厂商.py` | ✅ |
| ② 厂商注册（枚举 + 映射 + @register） | `common_enums.py` + `registry.py` | ✅（约 5 行） |
| ③ 参数配置（评估字段/会话/用例） | 算法配置 field_mapper + APIs 表 + 用例配置 | ❌ 纯配置 |

执行器（RealtimeSessionExecutor）是通用的：正常轮/打断轮/推流节奏/等待全是通用编排，用例配置驱动。**接任何厂商都不改执行器。**

## 二、写适配器（= Realtime 的 driver）

### 2.1 继承谁

```
ApiVendorAdapter (Port，抽象契约，domain/ports/)
   ├── RealtimeAdapterBase   ← Realtime 厂商继承这个（协议级，protocol/）
   │      └── OpenAIRealtimeAdapter  （官方样例：5 个类属性，零覆写）
   │      └── 你的厂商适配器
   └── (HTTP 厂商) 直接实现 Port（见《接入指南·普通 HTTP API》）
```

继承 `RealtimeAdapterBase` 白拿：WS 连接、事件队列、`pre_process/send/recv/output/close` 同形方法面、代理透传、密钥链、会话亲和。

### 2.2 最小模板（事件协议与 OpenAI 相同 → 5 行就够）

```python
# adapters/vendors/my_vendor_adapter.py
from shared.models.common_enums import AdapterProtocol, AdapterVendor, VendorAdapterType
from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import RealtimeAdapterBase
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

@register_vendor_adapter
class MyVendorRealtimeAdapter(RealtimeAdapterBase):
    protocol = AdapterProtocol.REALTIME
    vendor = AdapterVendor.MY_VENDOR
    adapter_type = VendorAdapterType.MY_VENDOR
    display_name = 'xx Realtime 适配器'
    _transport_vendor = 'openai'   # 事件协议与 OpenAI 相同 → 到此结束
```

### 2.3 协议不同 → 覆写点表

| 厂商差异 | 覆写方法 | 写什么 |
| --- | --- | --- |
| 握手载荷不同 | `pre_process` | 你的 session.update 字段 |
| 事件字段不同 | `recv` | 厂商事件 → 归一化 `RealtimeFrameType`（打断依赖 `user_speech_started` / `response_cancelled`） |
| 输出结构不同 | `output` / `post_process` | 聚合 audio/text/frame |
| 等待语义不同 | `wait_ai_speaking` / `wait_ai_complete` | AI 开口/完成判定 |
| 打断字段方言不同 | `resolve_round_mode` | 默认读 `is_interruption`（`_as_bool` 兼容 int/bool/str）；厂商用 `barge_in` 等覆写 |
| 传输完全私有 | `_build_client` | 替换默认 WS 客户端 |

```python
# 覆写示例：厂商打断事件名不同 → 归一化
def recv(self, timeout=5.0):
    evt = self._client.recv(timeout)
    if evt.get('type') == 'vendor_a_barge':   # 厂商自己的打断事件
        return {'type': RealtimeFrameType.USER_SPEECH_STARTED.value, ...}
    return evt
```

## 三、注册（20 家也就这几行）

```python
# common_enums.py
class AdapterVendor(str, Enum):     MY_VENDOR = 'my_vendor'
class VendorAdapterType(str, Enum): MY_VENDOR = 'my_vendor'

# registry.py
_FLAT_KEY_DIMENSIONS = { ..., VendorAdapterType.MY_VENDOR: (AdapterProtocol.REALTIME, AdapterVendor.MY_VENDOR) }
```

分发是表驱动的（`resolve_for`）：配置了 `vendor_adapter=my_vendor` 走你的适配器；未配置走默认。执行器零改动。

## 四、用例特殊处理（纯配置）

| 用例场景 | 配什么 | 适用算法 | 谁来处理 |
| --- | --- | --- | --- |
| 正常对话轮 | 每轮输入音频 + `query` | 全部 | 执行器通用编排 |
| **打断轮（插话）** | `is_interruption: true` + `interruption_delay_ms`（默认 1000ms）/ `interrupt_mode`（默认 `fixed_delay`，见 §六） | **仅 voice_llm 等对话类** | 执行器 `_execute_interruption_round` 通用编排 |
| **推流中打断** | `pacing.pacing_strategy=allow_barge_in`（用例级或 API meta 级） | **仅 voice_llm 等对话类** | 执行器 `_pacing_gate` |
| **拒识** | `is_reject: true` + `timing`（静默/回复过程中） | **仅 voice_llm（reject_judge 维度）** | 评估侧计算器 |
| 评估字段名/映射 | param_mapping（source→target） | 按算法各自声明 | field_mapper（配置） |

> **打断轮 / 拒识 / 推流中打断是 voice_llm 这类「对话/拒识算法」的用例语义，其他算法（asr/der/wer 等）不需要**，各自有自己的字段与评估计算器，字段区分靠 field_mapper 按 algorithm_type 的 param_mapping。

**关键：这些特殊处理你不需要写代码。** 打断轮时序（等 AI 开口 → 延时 → 推打断音频 → 检测窗口）由通用执行器编排；拒识判定由评估侧 `reject_judge` 计算器负责；字段名映射由 field_mapper 配置驱动。适配器唯一要保证：**厂商事件正确归一到 `user_speech_started` / `response_cancelled`**（打断）和**如实采集轮次结果**（拒识）。

> **时序口径（负责人 2026-10-23 拍板）**：
> - **正常轮完成判定**：事件驱动——`ai_audio_delta` 起始窗口判「已开口」、`ai_audio_done` 收尾窗口判「完成」，**超时仅兜底**（不改变成败语义；`success = bool(complete and output['ai_complete'])`）。
> - **打断点**：模式化——`fixed_delay` 按固定延时（`interruption_delay_ms`）或 `output_duration` 按已返回 AI 音频流长度（`interrupt_after_ms`）判定打断时机（见 §六）。
> - **时延指标**：帧时间戳实测（帧记录 `ts`；设计 schema 另含 `offset_ms`——当前实现逐帧 `{ts,type,payload}`，INT-263 已记录；首帧 `first_frame_latency_ms`、打断 `barge_in_latency_ms`），**与超时无关**。

## 五、WS 非实时接入（protocol=websocket + streaming=false）

除 Realtime 会话式外，被测 WS API 还支持**请求-响应式（非会话式）**接入：`apis` 配 `protocol=websocket` + `streaming=false`（INT-2079 已合入）。一轮 = 一次 WS 请求-响应往返，不维持会话。

| 维度 | WS 实时（Realtime 会话式） | WS 非实时（请求-响应式） |
| --- | --- | --- |
| `apis.protocol` / `apis.streaming` | `websocket` / `true` | `websocket` / `false` |
| 执行道 / 执行器 | 流式道 → `RealtimeSessionExecutor` | 非流式道 → `APISessionExecutor` + `WebSocketAdapter`（协议级 `(AdapterProtocol.WEBSOCKET, AdapterVendor.ANY)`） |
| 交互形态 | 会话式全双工流式（逐 chunk 推 `input_audio_buffer.append` + 事件回流） | 连接 → 发一条请求消息 → 收响应（可多条）→ 断开 |
| 可测轮次 | 正常轮 / 打断轮 / 推流节奏（pacing） | **正常轮 / 多轮**（每轮一次往返） |
| 打断 / 拒识 / 推流中打断 | 有（`is_interruption` / `pacing`） | **无**——非流式道不声明会话能力：`APISessionExecutor` 不消费 `is_interruption` / `pacing` / 拒识字段，配了也不生效 |
| 完成判定 | 事件驱动：`ai_audio_delta` → `ai_audio_done`，超时仅兜底 | 响应收敛：命中会话结束标记 / 服务端断开 / 首响应后静默超时（`meta.recv_timeout`，默认 2s）/ `meta.max_responses`（默认 100） |
| 时延 / 时长 | 帧时间戳实测（`first_frame_latency_ms` / `barge_in_latency_ms`） | 轮次请求-响应实测（`latency`）；无帧时间戳指标 |

- **写侧**：`(websocket, false)` 已在可用矩阵（`AVAILABLE_PROTOCOL_STREAMING`），不再 400「实现未上线」。
- **用例 `rounds`**：与普通轮一致（`round_number` / `audio_id` / `audio_path` / `query` / `question` / `correct_answer`），不配置 `is_interruption` / `pacing` 等会话能力字段。
- **请求体**：`body_template`（用例级 > API `meta.body_template` > `meta.body`）递归渲染 `{{placeholder}}`，占位符取轮次上下文（`session_id` / `round_number` / `total_rounds` / `input_text` / `input_audio` / `input_type` / `source_lang` / `target_lang` / `translation_direction` / `algorithm_type` / `context` / `context_for_request` / `algorithm_params` / `case_algorithm_params`）；未配模板时整份轮次上下文 JSON 作为请求消息。
- **端点 / 头 / 密钥 / 代理**：`api_endpoints` 中首个 `ws://` / `wss://` 条目**即端点**（唯一来源——INT-1361 已移除 `api_url`）；无 ws 条目直接判轮次失败并报「未配置 WebSocket 端点」，不做兜底；`meta.ws_headers` 直传；密钥链与密钥池轮换、`proxy_type` / `proxy_url` 与 Realtime 同源（字段见 §七）。
- **响应与失败收敛**：最后一条 JSON 作为归一 payload（`raw_response['json']`），字段映射走既有统一入口（`meta.result_parser` / `asr_mapping` / `trans_mapping`）；连接/握手/发送异常、首响应前断开、首响应超时、`{"type": "error"}` 协议错误帧都收敛为轮次失败，不静默成功。
- **不需要新写适配器**：`WebSocketAdapter` 是协议级 base，厂商差异用配置表达（`body_template` / 响应映射）；确需替换传输语义时，才按第二节注册厂商适配器（`protocol = AdapterProtocol.WEBSOCKET` + `vendor = 你的厂商`，精确匹配优先于协议级 base）。

## 六、打断点模式（`interrupt_mode`）

打断轮（barge-in）的「AI 开口后何时推打断音频」由 `interrupt_mode` 模式化配置（INT-2080 已合入）：

| 模式 | 值 | 打断点判定 | 配置键 |
| --- | --- | --- | --- |
| 固定延时（缺省） | `fixed_delay` | AI 开口后按**固定延时**推打断音频 | `interruption_delay_ms`（默认 1000，round 级可覆盖） |
| 输出时长 | `output_duration` | 按**已返回 AI 音频流长度**判定——累计换算时长 ≥ 阈值即打断 | `interrupt_after_ms`（默认 3000） |

- **适用**：voice_llm 打断轮（`is_interruption: true`，见 §四）。
- **配置兜底链**：`round_config` → `api.meta` → 用例 → 全局（`realtime_session` 段）→ 默认；未知 `interrupt_mode` 回退 `fixed_delay`（fail-safe，不破坏既有用例）。
- **大块回复（一次返回多秒音频）场景**：模型的音频可能在一帧内大量返回，固定延时容易错过「AI 已说够一会儿」的时机；`output_duration` 按已返回音频长度触发更精确：

```json
{
  "round_number": 2,
  "is_interruption": true,
  "interrupt_mode": "output_duration",
  "interrupt_after_ms": 3000,
  "audio_id": 123
}
```

- **判定细节**：`output_duration` 轮询已返回音频字节数，按**回传音频格式采样率**（`resolve_audio_sample_rate(api_config, direction='output')`，s16 单声道每样本 2 字节）换算为毫秒；累计 ≥ `interrupt_after_ms` 即推打断音频。AI 输出 turn 结束（`ai_audio_done` / `ai_text_done`）、打断信号已到（`user_speech_started` / `response_cancelled`）、连接收敛或任务停止时提前结束等待，不无限等待。
- **轮次结果**：打断轮 result 含打断点依据 `interrupt_mode` / `interrupt_trigger_ms`（`fixed_delay`=延时；`output_duration`=触发时已返回音频实际时长）/ `interrupt_after_ms`。

## 七、APIs 表 + 建任务（配置）

- **APIs 表一行**：`vendor=my_vendor`、`protocol=websocket` + `streaming=true`（Realtime 会话式；WS 请求-响应式见 §五，用 `streaming=false`，INT-1799）、`api_endpoints`（条目 `endpoint` 带 `ws://` / `wss://` 前缀，可选 `name` / `max_process` / `max_timeout` / `max_audio_duration` / `priority` / `api_keys` 端点级密钥池；`api_url` 已移除、`device_type` 列已废弃）、`audio_config`（顶层列，目标音频格式；meta.audio_config 仅存量兼容，INT-1771）、meta（session_config / ws_headers / api_key）、proxy_type / proxy_url
- **建任务**：选用例 + 选 API（可同时选多个 API 和物理设备混跑）→ 用例在选中目标上分别执行（case_devices 指派 device_type）

## 八、参数配置（三层解析）

被测 Realtime API 的输入/输出字段与映射在 **设备管理 → 测试 API → 编辑 → 「参数配置」页签**维护；新建 API 时也可直接配，随创建一起提交。

解析顺序固定为：

```text
本 API 覆盖  >  绑定策略  >  算法级默认
```

- 表格「来源」列展示生效值来自哪一层：`算法级` / `策略` / `本 API`。
- **编辑算法级或策略行 = 新增本 API 覆盖**；删除覆盖行 = 回落到上一层，不会改动算法级声明本身。
- 保存只写本 API 的覆盖行：未改动的算法级 / 策略行不会被固化成覆盖行。
- 策略可在 **算法配置页右上「参数策略」** 集中管理（按作用域筛选「全部 / API / 设备」并分别新建）；也可在页签内「另存为新策略 / 克隆当前策略」，切换绑定即时生效。
- **历史与回滚**：参数区「历史」按钮可查看最近 50 个版本并回滚。回滚只恢复本 API 的覆盖行，不动策略绑定；回滚本身也会记一版。
- 权限：读 `algorithm:read`，写 `algorithm:param_manage`（参数与映射同一权限）。

> 输出字段（`direction=output`）与评估映射是同一份三层解析结果；打断轮 / 拒识的用例语义见 §四，与参数层级无关。

## 九、验证

1. **mock 冒烟**：`mock_realtime_api.py --barge-in`（预置「AI 说话 + 打断」事件序列）→ 正常轮 + 打断轮跑通
2. **真机**：把 `api_endpoints` 里的 ws 端点指向被测服务，核对事件协议与归一化（`response.audio.delta` 等）
3. **回归**：`test_int497_openai_realtime_e2e.py`（分发 + 打断轮）、`test_int475_realtime_pacing.py`（节奏策略）
4. **WS 非实时**：`python mock_services/mock_ws_request_response_api.py --port 5095`（`--response-delay-ms` / `--disconnect-before-response` / `--protocol-error` / `--session-end` 分别注入超时兜底、断连、协议错误帧、会话结束收敛）→ 正常轮 / 多轮跑通；单测 `test_int2079_ws_non_streaming.py`
5. **output_duration 打断点**：`mock_realtime_api.py --barge-in --delta-bytes <n> --barge-in-audio-chunks <n>` 预置大块回复 → 打断点按已返回音频长度触发（`interrupt_trigger_ms` 与阈值对照）；单测 `test_int2080_interrupt_mode.py`

## 十、FAQ

- **Q：我的服务事件字段和 OpenAI 不同？** 在适配器 `recv` 归一化即可，用户侧能力不受影响。
- **Q：怎么确认打断测试生效？** 看轮次结果打断指标（barge_in 统计）；页面有实时帧可观察。
- **Q：被测端要满足什么才能测打断？** 会话跨轮保持且会自主回复；VAD 能检出用户开口（发 `user_speech_started`）或主动取消回复（发 `response.cancelled`）。不满足也能跑正常对话轮。
