# 设备参数和API参数绑定方案

> **实施状态**：本文档描述的 keywords/api_id 绑定方案为**设计提案，尚未实施**。经代码核对：`AlgorithmDeviceParam`、`AlgorithmApiParam`、`ParamMapping` 三个模型中均**不存在** keywords/api_id 字段。当前设备驱动的解析由 `backend/utils/device_driver/registry.py` 按 `(app_type, version, platform)` 三元组完成（AppType/DevicePlatform 枚举驱动），keywords 字符串匹配机制仍保留于 `driver_factory.py` 的专用驱动注册表（`_specialized_drivers`）。文中标注"现状核对"处为与代码库对齐的说明，其余保留原提案内容供后续实施参考。

> **C0 裁定（2026-10-24，INT-1745，方案一致性审计）**：§二/§三 的 `keywords` / `api_id` 字段方案仍为提案；与之相邻的另一条语义——**API 输出字段的声明与取值**——已裁定，见 **§九**：输出字段由 `algorithm_api_params(direction=output)` 声明（补 `field_path`），映射到评估维度参数在执行侧完成，`map_api_results` 废弃。

## 一、需求背景

设备参数需要和设备驱动绑定，API参数需要和API绑定。
通过驱动标识（keywords）和API标识（api_id），让驱动知道：
1. 哪些设备/API参数是他的
2. 用例参数要映射到哪些设备/API参数

## 二、数据模型变更

### 1. AlgorithmDeviceParam（设备参数表）

| 字段 | 说明 | 变更 |
|------|------|------|
| keywords | 驱动关键字 | 新增字段 |

> 说明：复用 Device 表中的 keywords 字段格式，用于匹配设备驱动
>
> 现状核对：AlgorithmDeviceParam 实际字段为 algorithm_type/param_code/param_name/label/param_type/direction/required/default_value/validation_rules/help_text/ui_order/hidden/deleted，暂无 keywords 字段（按 `(algorithm_type, param_code, direction)` 唯一索引）。

### 2. AlgorithmApiParam（API参数表）

| 字段 | 说明 | 变更 |
|------|------|------|
| api_id | 关联的API配置ID | 新增字段 |

```python
class AlgorithmApiParam(db.Model):
    # 现有字段...

    # 新增字段
    api_id = Column(Integer, ForeignKey('apis.id'), comment='关联的API配置ID')
```

> 现状核对：AlgorithmApiParam 实际字段为 algorithm_type/param_code/param_name/label/param_type/direction/required/default_value/validation_rules/help_text/ui_order/hidden/deleted，暂无 api_id 字段。API 参数在现有设计中直接归属算法配置（按 algorithm_type 关联），不绑定到具体 API 记录。

### 3. ParamMapping（参数映射表）

| 字段 | 说明 | 变更 |
|------|------|------|
| keywords | 设备驱动关键字 | 新增字段 |
| api_id | API配置ID | 新增字段 |

```python
class ParamMapping(db.Model):
    # 现有字段...

    # 新增字段
    keywords = Column(String(200), comment='设备驱动关键字（用于映射时识别来源驱动）')
    api_id = Column(Integer, ForeignKey('apis.id'), comment='API配置ID（用于映射时识别来源API）')
```

> 现状核对：ParamMapping 实际字段为 algorithm_type/source/source_param/source_direction/dimension_id/target_param/transform_type/deleted，暂无 keywords/api_id 字段。其中 source 支持 case/reference/device/api/case_config 五类来源，source_direction 区分输入/输出方向，映射按 algorithm_type 关联参数定义，无需 keywords/api_id 即可定位来源参数。

## 三、字段作用说明

### keywords 字段作用

- **参数定义时**：在 AlgorithmDeviceParam 中指定这个参数用哪个驱动处理
- **参数映射时**：在 ParamMapping 中继承自设备参数，用于标识这个映射的来源驱动

### api_id 字段作用

- **参数定义时**：在 AlgorithmApiParam 中指定这个参数属于哪个API
- **参数映射时**：在 ParamMapping 中继承自API参数，用于标识这个映射的来源API

## 四、执行流程

```
用例参数 (case)
       ↓ 根据 keywords/api_id 映射
设备参数 (device) - keywords='face2face,面对面'
API参数 (api) - api_id=1
       ↓ 驱动/API执行
设备输出 / API输出
       ↓ 根据 keywords/api_id 映射到评估维度
评估维度
```

## 五、前端改动

### 1. 算法配置弹窗 - 设备参数配置

增加**驱动选择**下拉框：
- 数据来源：`GET /api/v1/test-devices/driver-keywords`（返回 `[{name, keywords, system}]`）
- 存储到：AlgorithmDeviceParam.keywords

> 现状核对：该接口已实现（`backend/blueprints/device_bp.py` 注册于 url_prefix `/api/v1/test-devices`，由 `device_controller.get_driver_keywords()` 调用 `device_driver_factory.get_registered_keywords()`）。当前用例执行时的驱动解析实际机制是 `backend/utils/device_driver/registry.py` 按 `(app_type, version, platform)` 三元组装饰器注册与 resolve（AppType 枚举：ANDROID_BASE/HARMONY_BASE/PLAUD/DOUBAO_ASR/DOUBAO/CHATGPT/XIAOYI_SIMULTANEOUS/XIAOYI_HUIJI/XIAOYI_LIVECHAT/XIAOYI_INPUT_METHOD；DevicePlatform：ANDROID/HARMONYOS/IOS，AppVersion 支持 V1→LATEST 降级）；keywords 字符串匹配作为并存机制保留于 `driver_factory.py` 的 `_specialized_drivers`（`get_driver_name_by_keywords` 要求所有 keywords 均命中）。若实施本方案，驱动选择下拉框的数据应与 registry.py 的 AppType 枚举对齐。

### 2. 算法配置弹窗 - API参数配置

增加**API选择**下拉框：
- 数据来源：`GET /api/v1/apis`
- 存储到：AlgorithmApiParam.api_id

### 3. 参数映射配置

- 当 source=device 时，显示**驱动筛选**下拉框，筛选后源参数只显示该驱动的参数
- 当 source=api 时，显示**API筛选**下拉框，筛选后源参数只显示该API的参数

## 六、后端改动

### 1. 数据库模型

- AlgorithmApiParam：新增 api_id 字段
- ParamMapping：新增 keywords 和 api_id 字段

### 2. algorithm_config_loader.py

（提案）序列化时返回 keywords 和 api_id：

```python
def _serialize_params(self, params: List) -> List[Dict[str, Any]]:
    return [
        {
            # 现有字段...
            'keywords': getattr(p, 'keywords', None),
            'api_id': getattr(p, 'api_id', None),
        }
        for p in params
    ]
```

> 现状核对：由于模型中尚无 keywords/api_id 字段，当前 `_serialize_params` 并不返回这两个键，上述代码仅在方案实施后生效。

### 3. field_mapper.py（可选增强）

映射时可以根据 keywords/api_id 过滤参数：

```python
# 获取特定驱动的设备参数
device_params = [p for p in device_params if p.get('keywords') == target_keywords]

# 获取特定API的API参数
api_params = [p for p in api_params if p.get('api_id') == target_api_id]
```

## 七、改动清单

以下为方案实施时所需的改动清单（均未实施）：

| 序号 | 模块 | 文件 | 改动内容 |
|------|------|------|---------|
| 1 | 后端 | algorithm_models.py | AlgorithmApiParam 新增 api_id 字段 |
| 2 | 后端 | algorithm_models.py | ParamMapping 新增 keywords 和 api_id 字段 |
| 3 | 后端 | algorithm_config_loader.py | 序列化时返回 keywords 和 api_id |
| 4 | 后端 | 算法Controller | API接口支持 keywords 和 api_id 字段 |
| 5 | 前端 | AlgorithmConfigModal.vue | 设备参数增加驱动选择（复用 keywords） |
| 6 | 前端 | AlgorithmConfigModal.vue | API参数增加API选择（新增 api_id） |
| 7 | 前端 | AlgorithmConfigModal.vue | 映射配置增加驱动/API筛选功能 |

## 八、数据示例

> 以下示例为方案实施后的目标状态（含 keywords/api_id 列），与当前数据库实际表结构不符，仅供实施参考。

### AlgorithmDeviceParam 示例

| id | algorithm_type | param_code | param_name | keywords |
|----|---------------|------------|------------|----------|
| 1 | translation | asr_result | ASR结果 | face2face,面对面 |
| 2 | translation | translation | 翻译结果 | face2face,面对面 |

### AlgorithmApiParam 示例

| id | algorithm_type | param_code | param_name | api_id |
|----|---------------|------------|------------|--------|
| 1 | translation | vendor | 供应商 | 1 |
| 2 | translation | task_id | 任务ID | 1 |

### ParamMapping 示例

| id | algorithm_type | source | source_param | target_param | keywords | api_id |
|----|---------------|--------|--------------|--------------|----------|--------|
| 1 | translation | device | asr_result | asr_ref | face2face,面对面 | NULL |
| 2 | translation | device | translation | candidate | face2face,面对面 | NULL |
| 3 | translation | api | result | candidate | NULL | 1 |

## 九、API 输出字段声明与取值口径（C0 裁定，2026-10-24）

> **状态：已裁定，未实施。** 本节由方案一致性审计员在 INT-1745（C0）出具，配套实施卡 C1（INT-1746）/ C2（INT-1747）/ C3（INT-1748）/ C4（INT-1749）。落地前代码行为仍以 §一~§八 各段「现状核对」为准。

### 9.1 四条裁定

| # | 待裁问题 | 裁定 | 依据 |
|---|---------|------|------|
| 1 | 映射责任归属 | **执行侧映射**：三条 API 执行链在产出轮次结果时即生成 `{target_param: value}`，评估侧只按 `target_param` 取 | E2E 早已在设备侧映射（`device_service/infrastructure/acl/algorithm_query_acl_repository.py:148-196` 的 `convert_device_output` → `e2e_test_service/domain/services/e2e_calculation_service.py:216-244`），评估侧 `evaluation_service/domain/services/evaluation_service/round_data_builder.py:171` 只认 `target_param`；改执行侧不动唯一已通的 E2E 链 |
| 2 | `rounds[]` 结构 | **强制 `rounds[i].output` 子字典**，执行侧不再把评估字段平铺到轮次顶层 | 三处消费者都按 `rounds[i].output` 取值：`round_data_builder.py:150,171`、`evaluation_service/infrastructure/evaluation_api/endpoint_worker.py:291`、`report_service/application/services/report_aggregation/stats_mixin.py:627`；今天只有 Realtime 链平铺（`api_test_service/core/realtime_session_executor.py:395,487`），且没有任何消费者读平铺键 |
| 3 | 输出字段声明归属 | **`algorithm_api_params(direction=output)` 优先且唯一**；`apis.meta.result_parser` / `asr_mapping` / `trans_mapping` 仅在「该算法类型零输出声明」时兜底 | 声明表可维护、带 `param_type`、可参与映射与报告；`meta` 解析器是厂商方言私货，承载不了嵌套路径（`api_test_service/infrastructure/adapters/api_driver_adapter.py:451-493,506-546`） |
| 4 | `map_api_results` 去留 | **废弃**：删 `shared` 客户端封装 + `ResultFieldMappingQueryHandler.map_api_results` + 策略实现，RPC 桩返回明确失败 | 全仓无调用方（`shared/clients/_grpc_algo_audio.py:310` 的 `algo_map_api_results` 无人调）；且 servicer 传参已坏——`algorithm_service/interfaces/grpc/algorithm_query_servicer.py:337` 只传 `raw_results`，而 `algorithm_service/application/queries/result_field_mapping_queries.py:207` 需要 `(algorithm_type, raw_results)`，该 RPC 今天必然 TypeError |

### 9.2 两跳取值链路（目标态）

```
厂商原始响应
   │ ① 声明驱动提取：algorithm_api_params(direction=output) 的 field_path（空 = 按 param_code 取顶层键）
   ▼
{api_param_code: value}
   │ ② 参数映射：param_mappings(source='api', source_direction='output')，source_param = param_code
   │    有映射 → target_param；无映射 → 恒等（target = param_code）
   │    transform_type 在这一跳应用
   ▼
rounds[i].output = {target_param: value}      ← 评估侧唯一读取的口径
```

- **字段全集**：`rounds[i].output` 覆盖该算法类型**全部** `direction=output` 的 api 参数，而不只是被映射过的参数——与设备链 `get_mapped_device_output_fields` 的「未映射恒等保留」语义对齐（`algorithm_service/application/queries/field_mapping_queries.py:88-103`）。
- **方向过滤**：只取 `source_direction='output'`。`algorithm_service/infrastructure/persistence/config_cache.py:843-907` 的 `_get_evaluation_mappings` 目前把 `direction` 硬编码为 `output`，实施时不得据此把 input 映射混进输出。

### 9.3 声明优先级与兜底（逐键）

| 优先级 | 来源 | 触发条件 | 行为 |
|-------|------|---------|------|
| 1 | `algorithm_api_params(direction=output).field_path` | 该键已声明且 `field_path` 非空 | 按路径从原始响应提取；语法为点号 + 数字下标，`a.b.0.c` 与 `a.b[0].c` 等价 |
| 2 | `algorithm_api_params(direction=output).param_code` | 已声明、`field_path` 为空 | 按 `param_code` 在响应顶层取值（= 现状行为，存量零改动） |
| 3 | `apis.meta.result_parser`（voice_llm）/ `asr_mapping` + `trans_mapping`（translation） | **该算法类型一条 output 声明都没有** | 走既有解析器，其产出的 `asr` / `trans` / `output` 键进入第 ② 跳；必须打 WARNING 列出兜底键 |
| — | 无 | 键既未声明、兜底也没有 | 不写入 `output`，不报错 |

- 优先级是**逐键**的：声明优先，`meta` 只补未声明的键，不做合并冲突裁决。
- 同一算法类型下不允许「声明一套 + meta 再覆盖一次」并存；补齐声明后兜底分支即为死代码，应在 C3 / 清理卡删除。
- 提取函数复用 `shared/utils/path_extractor.py:extract_by_path`（现支持 `a.b.0.c`），**只扩展该函数兼容 `[n]` 写法，不新增第二个提取器**。

### 9.4 存量兼容（不回归路径）

| 存量形态 | 落地后行为 |
|---------|-----------|
| 历史 `rounds[].output` 为字符串 | 只读兼容：`shared/utils/round_data_utils.py:17-28` 的 `normalize_round_output` 继续归一为 `{'text': ...}`；新数据不再产生字符串 output |
| 未配 `source='api'` 映射、也未声明 output 字段的老 API | 走 §9.3 兜底解析，轮次 output 只含 `asr`/`trans`/`output` 键；评估侧按 `target_param` 取不到值时沿用现有「无值不覆盖维度默认值」语义（`round_data_builder.py:204-205`）并留 ERROR 日志，不报错、不阻断执行 |
| E2E 设备链 | 不动：仍由 `convert_device_output` + `_map_round_output` 产出 `{target_param: value}`（`device_service/infrastructure/acl/algorithm_query_acl_repository.py:187-196`、`e2e_calculation_service.py:216-244`） |
| 主库现状（2026-10-24 实测） | `param_mappings` 无 `source='api'` 行（仅有 case / case_config / device / evaluation / reference）；`algorithm_api_params` 中 voice_llm 仅 `response_audio` 一条 output 声明 → **今天 API 用例没有任何路径能出评估值**，须按 §9.5 补声明与种子 |

### 9.5 实施边界（未实施）

| 项 | 卡 | 边界 |
|---|----|------|
| 执行侧映射 + `rounds[i].output` 子字典 | C1 INT-1746 | 三条 API 链产出 `target_param` 视图；HTTP 轮次补 `answer_text`（与 Realtime 对齐），`algorithm_result.text_output` 由其拼接，不再对 `output` 做字符串拼接（`api_session_executor.py:568`）；**不动** `evaluation_service` 的取值代码 |
| `field_path` 列 + 声明驱动提取 | C2 INT-1747 | `algorithm_api_params` 加 `field_path VARCHAR(255) NULL`（空 = 按 `param_code`）、DTO / RPC 透传；单轮（`api_task_runner.py:401-472`）、多轮、Realtime 三条链共用一个提取入口 |
| 去硬编码 | C3 INT-1748 | `VoiceLlmStrategy.get_output_fields` / `process_algorithm_result` 改读配置；**删除** `map_api_results` 实现而非配置化它 |
| `transform_type` 生效 | C4 INT-1749 | 在 §9.2 第 ② 跳（执行侧映射处）应用一次，评估侧不重复应用；批量取变换而非逐字段 RPC |
| `api_id` 作用域（同类型多厂商） | C6 INT-1751 | 声明表补 api_id 维度；本轮不做，声明按算法类型作用域 |

