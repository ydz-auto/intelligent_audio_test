# 接入指南 · 普通 HTTP API 测试（http_api）

> 受众：接入新被测 HTTP 接口的开发者。
> 核心原则：**执行器通用，特殊处理固定三处落点（适配器 / 配置 / 评估计算器）**。
> 定位：接入方开发者指南——如何写适配器、如何处理用例特殊处理。本文只描述接入口径，不含平台安装部署（见 `doc/使用说明.md` 与部署文档）。

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

### 3.1 被测 API 配置字段

平台「API 管理」维护被测 API 配置（`api_test_service/infrastructure/persistence/models/api_models.py` `class API`，表 `apis`），接入 HTTP API 时关心的字段：

| 字段 | 说明 |
| --- | --- |
| `name` | API 显示名称 |
| `vendor` | 供应商名称（如 `volc_ast` / `ali` / `tencent`；联调用 mock 替身时填 `mock`） |
| `api_url` | API 微服务主入口 URL |
| `api_endpoints` | API 接入点配置列表（JSON），优先于 `api_url` 参与端点轮询 |
| `device_type` | `http_api`（默认值） |
| `meta` | API 元数据（鉴权信息、`vendor_adapter`、`ws_headers` 等，JSON） |
| `default_max_process` | 默认最大并发处理数（默认 5，`api_executor.default_max_process` 兜底） |
| `default_max_timeout` | 默认最大超时（秒，默认 30） |
| `default_max_audio_duration` | 支持的最大音频时长（秒，默认 60） |
| `proxy_type` / `proxy_url` | 被测 API 网络代理（INT-839）：`proxy_type` ∈ http / https / socks5 / socks5h，`proxy_url` 为 `user:pass@host:port` 不含 scheme；配置代理时认证段必填；NULL/空 = 不用代理 |

校验规则（后端 `api_test_service/infrastructure/adapters/proxy_utils.py` `validate_proxy`，前端 `frontend/src/utils/proxyValidation.ts` 镜像）：`proxy_type` 为空则 `proxy_url` 必须为空；非空则类型必须是四值之一、`proxy_url` 必填且带 `user:pass@` 认证段、不得含 scheme 前缀。

### 3.2 建任务与执行链路

HTTP 路径单轮执行由 `APITaskRunner`（`api_test_service/core/api_task_runner.py`）完成，适配器经 `vendor_adapter_registry.create_from_config(...)` 分发（`api_test_service/infrastructure/adapters/registry.py`）。建任务时在 `case_devices` 中携带 `{"case_id": ..., "device_type": "http_api", "device_id": ...}`（用例级路由依据，`task_service/infrastructure/persistence/_task_crud_mixin.py` 契约），平台按 `_dispatch_case_by_type` → `_dispatch_api_case`（`task_service/core/execution_engine/mixins/task_dispatch.py`）路由到 `api_test_service` 执行。单用例执行链路：

1. **health_check**：请求被测侧 `/health`（端点路径可经 `API_PATH_HEALTH` 环境变量配置，默认 `/health`）；404/405 视为路径不存在可跳过，其余失败视为健康检查失败；
2. **create_task**：请求被测侧 `/api/create_task`，**携带 `audio_path` 存储引用**（音频文件经平台统一存储层解析，`resolve_audio_local_path`）+ `vendor` / `max_process` / `max_timeout` / `endpoints` 等显式参数，按算法字段映射（`extract_case_all_params`）组装请求体；响应须返回 `data.task_id`；
3. **wait_for_completion**：轮询 `/api/get_status/{task_id}`（轮询间隔默认 5 秒，`api_test.poll_interval`），**超时 = 音频时长 × 1.5**（`total_audio_duration * 1.5`，上限 `api_test.max_wait_time` 默认 43200 秒，下限 30 秒）；`completed/success/failed/error/pending` 收口，`failed/error/pending` 记为轮失败；
4. **get_final_result**：查询 `/api/get_final_result/{task_id}`，按算法输出字段映射提取结果；
5. **评估**：结果经 `_evaluate_result` → `evaluation_acl_repository.submit_evaluate_case` 提交 evaluation_service。

可选：`get_frame_results`（调试）、`delete_task`（清理被测侧远端任务）。

## 四、用例特殊处理（适用算法）

### 4.1 rounds 字段

API 测试用例由 `rounds`（轮次数组）驱动。单轮常见字段：

| 字段 | 说明 |
| --- | --- |
| `round_number` | 轮号（从 1 起） |
| `audio_id` / `audio_path` | 本轮输入音频（平台音频资产 ID 或存储引用） |
| `spl` | 目标 SPL（dB，经 `spl_to_gain` 换算增益） |
| `query` / `question` | 本轮文本问题（评估入参） |
| `correct_answer` | 参考答案（评估入参） |

### 4.2 特殊处理与适用算法

| 用例场景 | 配什么 | 适用算法 | 谁来处理 |
| --- | --- | --- | --- |
| 单轮一问一答 | 输入 query + 期望 answer | 全部 | 执行器通用 |
| 多轮会话 | rounds 列表（`execute_voice_llm_chat`） | 对话类（voice_llm 等） | 适配器 execute_voice_llm_chat |
| 拒识 / 打断 | `is_reject` / `timing` / `is_interruption` | **仅 voice_llm 等对话/拒识算法** | 评估侧计算器 / 执行器编排 |
| 评估字段名/映射 | param_mapping（source→target） | 按算法各自声明 | field_mapper（配置） |

> 打断 / 拒识仅 voice_llm 这类「对话/拒识算法」需要，其他算法（asr/der/wer 等）不需要，各自有自己的字段与评估计算器。

## 五、验证

1. **mock 冒烟**：`mock_dut_api.py` 跑通单轮/多轮
   - 未接入真实被测 API 前，用平台自带 HTTP 替身联调（端口注册于 `shared/config/service_ports.py` `MOCK_DUT_API_HTTP_PORT = 5096`）：
     ```bash
     python mock_services/mock_dut_api.py [--port 5096]
     ```
   - `mock_services/mock_dut_api.py` 提供：`/health`（GET）、`/api/create_task`（POST）、`/api/get_status/{task_id}`（GET）、`/api/get_final_result/{task_id}`（GET）、`/api/get_frame_results/{task_id}`（GET）、`/api/delete_task/{task_id}`（DELETE），另有 `/chat`（POST）做 voice_llm 多轮会话替身（MockDialogAdapter 行为）。把被测 API 的 `api_url` 指向 `http://127.0.0.1:5096` 即可跑通端到端。
2. **真机**：换 api_url，核对请求/响应结构与 field_mapper 输出字段提取
3. **回归**：API 测试集成用例不回归

## 六、FAQ

- **Q：流式响应（SSE）怎么接？** 在 `execute` 内消费流式响应，聚合为结构化结果返回。
- **Q：厂商鉴权特殊？** 走密钥链（case_config → meta → env），或适配器 `render_request_parts` 自定义头。
