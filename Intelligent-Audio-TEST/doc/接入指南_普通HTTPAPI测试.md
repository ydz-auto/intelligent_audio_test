# 接入指南 · 普通 HTTP API 测试（http_api）

> 受众：接入新被测 HTTP 接口的开发者。
> 核心原则：**执行器通用，特殊处理固定三处落点（适配器 / 配置 / 评估计算器）**。

## 一、接入总览（3 件事）

| 你要做的事 | 放哪 | 写代码？ |
| --- | --- | --- |
| ① 适配器（实现 Port 抽象方法） | `api_test_service/infrastructure/adapters/vendors/你的厂商.py` | ✅ |
| ② 注册（枚举 + 映射 + @register） | `common_enums.py` + `registry.py` | ✅（约 5 行） |
| ③ 参数配置（请求模板/输出字段/用例） | APIs 表 meta + field_mapper + 用例 | ❌ 纯配置 |

## 二、写适配器（HTTP 无协议基类，直接实现 Port）

```python
# adapters/vendors/my_http_adapter.py
from shared.models.common_enums import AdapterVendor, VendorAdapterType
from api_test_service.domain.ports.api_vendor_adapter import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

@register_vendor_adapter
class MyHttpAdapter(ApiVendorAdapter):
    vendor = AdapterVendor.MY_VENDOR
    adapter_type = VendorAdapterType.MY_VENDOR

    def render_request_parts(self, context_data):        # 请求头/体（按厂商协议）
        return headers, body                              # (rendered_headers, rendered_body)

    def execute(self, context_data, files=None, method=None):   # 发请求 → 结构化结果
        return {'success': True, 'latency_ms': ..., 'status_code': 200,
                'json': {...}, 'text': ...}

    def execute_voice_llm_chat(self, **kwargs):           # 多轮会话默认路径（可选覆写）
        ...
```

**白拿**：
- 请求模板参数来自 field_mapper `build_api_request_data`（注入 context_data）
- 输出字段按 api 输出字段定义提取（`output_field_keys` 模式，对齐 api_task_runner）
- 密钥链 / 代理透传

## 三、注册 + 配置

```python
# common_enums.py
class AdapterVendor(str, Enum):     MY_VENDOR = 'my_vendor'
class VendorAdapterType(str, Enum): MY_VENDOR = 'my_vendor'

# registry.py
_FLAT_KEY_DIMENSIONS = { ..., VendorAdapterType.MY_VENDOR: (协议维度, AdapterVendor.MY_VENDOR) }
```

- **APIs 表**：`vendor=my_vendor`、`api_url`（`http(s)://` → 自动识别 http_api）、meta（请求模板 / 密钥 / 代理）
- **用例特殊处理（纯配置）**：单轮 = `execute`；多轮 = `execute_voice_llm_chat`；评估字段映射走 field_mapper（param_mapping）

## 四、用例特殊处理（适用算法）

| 用例场景 | 配什么 | 适用算法 | 谁来处理 |
| --- | --- | --- | --- |
| 单轮一问一答 | 输入 query + 期望 answer | 全部 | 执行器通用 |
| 多轮会话 | rounds 列表（`execute_voice_llm_chat`） | 对话类（voice_llm 等） | 适配器 execute_voice_llm_chat |
| 拒识 / 打断 | `is_reject` / `timing` / `is_interruption` | **仅 voice_llm 等对话/拒识算法** | 评估侧计算器 / 执行器编排 |
| 评估字段名/映射 | param_mapping（source→target） | 按算法各自声明 | field_mapper（配置） |

> 打断 / 拒识仅 voice_llm 这类「对话/拒识算法」需要，其他算法（asr/der/wer 等）不需要，各自有自己的字段与评估计算器。

## 五、验证

1. **mock 冒烟**：`mock_dut_api.py` 跑通单轮/多轮
2. **真机**：换 api_url，核对请求/响应结构与 field_mapper 输出字段提取
3. **回归**：API 测试集成用例不回归

## 六、FAQ

- **Q：流式响应（SSE）怎么接？** 在 `execute` 内消费流式响应，聚合为结构化结果返回。
- **Q：厂商鉴权特殊？** 走密钥链（case_config → meta → env），或适配器 `render_request_parts` 自定义头。
