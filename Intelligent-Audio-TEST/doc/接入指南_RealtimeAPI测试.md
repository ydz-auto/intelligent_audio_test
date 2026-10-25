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
| **打断轮（插话）** | `is_interruption: true` + `interruption_delay_ms`（默认 1000ms） | **仅 voice_llm 等对话类** | 执行器 `_execute_interruption_round` 通用编排 |
| **推流中打断** | API 配置 `allow_barge_in` 节奏策略 | **仅 voice_llm 等对话类** | 执行器 `_pacing_gate` |
| **拒识** | `is_reject: true` + `timing`（静默/回复过程中） | **仅 voice_llm（reject_judge 维度）** | 评估侧计算器 |
| 评估字段名/映射 | param_mapping（source→target） | 按算法各自声明 | field_mapper（配置） |

> **打断轮 / 拒识 / 推流中打断是 voice_llm 这类「对话/拒识算法」的用例语义，其他算法（asr/der/wer 等）不需要**，各自有自己的字段与评估计算器，字段区分靠 field_mapper 按 algorithm_type 的 param_mapping。

**关键：这些特殊处理你不需要写代码。** 打断轮时序（等 AI 开口 → 延时 → 推打断音频 → 检测窗口）由通用执行器编排；拒识判定由评估侧 `reject_judge` 计算器负责；字段名映射由 field_mapper 配置驱动。适配器唯一要保证：**厂商事件正确归一到 `user_speech_started` / `response_cancelled`**（打断）和**如实采集轮次结果**（拒识）。

## 五、APIs 表 + 建任务（配置）

- **APIs 表一行**：`vendor=my_vendor`、`api_url`（`ws://` 或 `wss://`）、`device_type=websocket_api`、`audio_config`（顶层列，目标音频格式；meta.audio_config 仅存量兼容，INT-1771）、meta（session_config / ws_headers / api_key）、proxy_type / proxy_url
- **建任务**：选用例 + 选 API（可同时选多个 API 和物理设备混跑）→ 用例在选中目标上分别执行（case_devices 指派 device_type）

## 六、验证

1. **mock 冒烟**：`mock_realtime_api.py --barge-in`（预置「AI 说话 + 打断」事件序列）→ 正常轮 + 打断轮跑通
2. **真机**：换 `api_url` 为被测端点，核对事件协议与归一化（`response.audio.delta` 等）
3. **回归**：`test_int497_openai_realtime_e2e.py`（分发 + 打断轮）、`test_int475_realtime_pacing.py`（节奏策略）

## 七、FAQ

- **Q：我的服务事件字段和 OpenAI 不同？** 在适配器 `recv` 归一化即可，用户侧能力不受影响。
- **Q：怎么确认打断测试生效？** 看轮次结果打断指标（barge_in 统计）；页面有实时帧可观察。
- **Q：被测端要满足什么才能测打断？** 会话跨轮保持且会自主回复；VAD 能检出用户开口（发 `user_speech_started`）或主动取消回复（发 `response.cancelled`）。不满足也能跑正常对话轮。
