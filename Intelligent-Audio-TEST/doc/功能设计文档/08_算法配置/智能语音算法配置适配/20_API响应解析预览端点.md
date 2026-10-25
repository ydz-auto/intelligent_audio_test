# 20. API 响应解析预览端点（INT-1772）

> 来源：C5（INT-1750）「响应解析」页签原计划的「测试解析」子功能。方案一致性审计第 1 轮查实
> 全仓没有解析预览端点（gateway 路由无 parse/preview，`shared/utils/path_extractor.py`
> 当时只是纯函数），前端自写路径解析会与 C2（INT-1747）的 `a.b[0].c` 语义分叉，故该子功能
> 从 C5 砍出、改由本卡补后端端点。本卡只交付**后端端点 + 契约**，前端接线另卡。

## 一、定位

- **只读、无副作用**：纯函数计算，不发任何外部请求、不读 OSS、不写库、不落缓存，
  也不需要 `api_id`（不查 API 配置，全部解析配置由请求体传入）。
- **路径语义与执行期同一份实现**：所有取值都调
  `shared/utils/path_extractor.py:extract_by_path`，本端点不引入第二套路径解析。
  支持的写法与执行期一致（`09_API协议面与执行道契约.md` §路径语法）：

  | 写法 | 示例 | 说明 |
  |------|------|------|
  | 点分键 | `data.result.text` | 逐层取 dict 键 |
  | 数字下标（点号） | `data.events.0.text` | list 元素（亦可用于 dict 的数字字符串键） |
  | 数字下标（方括号） | `data.events[0].text`、`m[1][0]` | 与点号等价（C2 / INT-1747） |

  非法写法（`a[x]` / `a[-1]` / `a..b` / `a[0]b`）由 `is_valid_path` 拦成 **400**，
  不与执行期「静默返回默认值」混为一谈。

## 二、接口契约

```
POST /api/v1/apis/parse-preview
权限：api_config:read（缺失 → 403）
Content-Type: application/json
```

### 2.1 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sample_response` | object / array / string | 是 | 样例响应。对象/数组直接用于提取；字符串先按 JSON 试解析（解析成对象/数组即用解析结果），解析不了按厂商原始文本处理（此时没有可提取结构，全部路径进 `unresolved`）。数字/布尔/null → 400 |
| `result_parser` | object \| null | 否 | 与 `apis.meta.result_parser` 同形：`asr_text_path` / `trans_text_path` / `session_id_path`，值为路径字符串。非对象 → 400 |
| `asr_mapping` | string \| null | 否 | 路径字符串（与 `meta.asr_mapping` 同形，执行期直接当路径用） |
| `trans_mapping` | string \| null | 否 | 同上 |
| `sentence_end_mapping` | string \| null | 否 | 同上 |
| `session_end_mapping` | string \| null | 否 | 同上 |
| `error_code_mapping` | string \| null | 否 | 同上 |
| `error_msg_mapping` | string \| null | 否 | 同上 |

- 空串 / `null` 路径 = **未配置**：不提取、也不进 `unresolved`。
- 非字符串路径（含对象）→ 400。
- 未列出的键（如 `append_mode`）一律忽略：本端点只做路径提取预览。

> 与卡面草案的差异说明：草案里 `asr_mapping` 等写作 `{...}`，但执行期这些 meta 值是
> **路径字符串**（`api_test_service/infrastructure/adapters/api_driver_adapter.py:514`
> 直接喂给 `extract_by_path`），所以端点按执行期同形接收字符串——否则预览会与执行期分叉。

### 2.2 响应

```json
{
  "success": true,
  "code": 200,
  "message": "Success",
  "data": {
    "extracted": {"<配置字段名>": "<值>"},
    "unresolved": ["<路径>", "..."]
  }
}
```

- `extracted` 的键 = 请求里的配置字段名（`result_parser` 取其内部键，如 `asr_text_path`），
  前端可把每项值贴回对应输入项旁。
- 取到的值是 `None`（路径不存在 / 下标越界 / 中间层类型不符）→ 该路径进 `unresolved`
  （去重、按配置顺序），**不静默丢**，接口仍 200。
- 取到空串 `""` 属于**命中**（执行期空串不是 `None`），进 `extracted`。
- 无命中项时 `extracted` 为 `{}`。

### 2.3 错误

| HTTP | 场景 | message 示例 |
|------|------|--------------|
| 400 | 空请求体 / 非法 JSON / 请求体不是 JSON 对象 | `请求体不能为空或不是合法 JSON 对象` |
| 400 | 缺 `sample_response` | `缺少 sample_response（样例响应）` |
| 400 | `sample_response` 非对象、非数组、非字符串 | `sample_response 必须是 JSON 对象/数组或原始字符串` |
| 400 | `result_parser` 不是对象 | `result_parser 必须是对象（与 meta.result_parser 同形…）` |
| 400 | 路径不是字符串 / 写法非法 | `asr_mapping 路径写法非法: 'a[x]'（只支持点号 + 数字下标…）` |
| 403 | 当前账号缺 `api_config:read` | `缺少权限: api_config:read` |

## 三、提取口径（与执行期逐条对齐）

实现：`api_gateway/application/services/api/parse_preview.py:build_preview`（纯函数）。

| 配置 | 取值对象 | 执行期对照 |
|------|----------|-----------|
| `result_parser.*` | **完整**样例响应 | `api_driver_adapter.py:451-493`（`_parse_voice_llm_response`：`response_data` 直接取） |
| `asr_mapping` / `trans_mapping` / `sentence_end_mapping` / `session_end_mapping` | `sample.get('data', sample)`（标准信封解包） | `api_driver_adapter.py:506-546`（`_parse_response`：`data = resp_json.get('data', resp_json)`，:537） |
| `error_code_mapping` / `error_msg_mapping` | **完整**样例响应 | 同上（`:529-530` 用 `resp_json`，不做 `data` 解包） |

即：`{"code":0,"msg":"ok","data":{"asr_result":"hi"}}` 配 `asr_mapping=asr_result` 命中
`hi`；配 `error_code_mapping=code` 命中 `0`。这条非对称是执行期既有行为，预览照搬，
避免「预览能取到、执行取不到」。

## 四、不做

- 不做真实 API 调用预览（那是连接测试 `POST /apis/{id}/health`）。
- 不做前端接线（前端卡另开）。
- 不引入第二套路径解析实现；不改 `path_extractor` 的既有语义
  （只新增 `is_valid_path` 语法校验，复用同一份分段规则）。
- 不读 `apis` 配置：想让端点「按某个 API 的 meta 预览」的接线由前端把 meta 原样带进请求体。

## 五、测试

`tests/unit/test_int1772_api_parse_preview.py`：

1. `result_parser` 指向 `a.b[0].c` / `a.b.1.c`、嵌套数组 → 正确值；点号与 `[n]` 等价；
2. 越界下标 / 缺失键 → 进 `unresolved`，接口 200；去重保序；空串/None 视为未配置；
3. 空请求体 / 非对象请求体 / 缺 `sample_response` / 数字样例 / 非对象 `result_parser` /
   非字符串 mapping / 非法路径 → 400 且 message 可读；
4. 缺 `api_config:read` → 403（TestClient 走真实路由）；
5. 执行期口径：`data` 解包、错误码取全量、空串算命中。
