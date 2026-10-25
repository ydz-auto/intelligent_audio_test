# 设备参数和API参数绑定方案

> **实施状态（2026-10-25 按实现更新，INT-1889 一致性审计回写）**：本文档 §一~§八 描述的 **keywords 驱动绑定方案为设计提案，尚未实施**（`AlgorithmDeviceParam`、`ParamMapping` 均无 `keywords` 列）；`api_id` 已全链路落地——**C6a（INT-1756）**（`AlgorithmApiParam.api_id`、`ParamMapping.api_id` 列存在，NULL = 算法类型级默认）与 **C6b（INT-1757，合入提交 `406b6a941`）**（执行 / 评估 / 报告消费域接线 + 输出声明缓存改键）均已实施；维度同步写路径按 `api_id` 收口的缺陷修复 **INT-1863（`2316a703b`）** 亦已合入。传 `api_id` 时声明与映射按「API 实例级覆盖算法类型级、未覆盖键回落」合并，不传仍是算法类型级默认（§10.1）。C0（INT-1745）裁定的 **API 输出字段声明与取值已实施**（C2 / INT-1747），见 §九。当前设备驱动的解析由 `backend/utils/device_driver/registry.py` 按 `(app_type, version, platform)` 三元组完成（AppType/DevicePlatform 枚举驱动），keywords 字符串匹配机制仍保留于 `driver_factory.py` 的专用驱动注册表（`_specialized_drivers`）。文中标注"现状核对"处为与代码库对齐的说明，其余保留原提案内容供后续实施参考。

> **C0 裁定（2026-10-24，INT-1745，方案一致性审计）**：§二/§三 的 `keywords` 驱动绑定方案仍为提案（`api_id` 已按 C6a / INT-1756 + C6b / INT-1757 全链路落地）；与之相邻的另一条语义——**API 输出字段的声明与取值**——已裁定并实施，见 **§九**：输出字段由 `algorithm_api_params(direction=output)` 声明（补 `field_path`），映射到评估维度参数在执行侧完成，`map_api_results` 废弃。

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
| api_id | 关联的API配置ID | 新增字段（已实施：C6a INT-1756） |
| field_path | 输出字段在厂商原始响应中的取值路径 | 新增字段（已实施：C2 INT-1747） |

```python
class AlgorithmApiParam(db.Model):
    # 现有字段...

    # 新增字段（均已落库，INT-1747 / INT-1756）
    api_id = Column(Integer, nullable=True, comment='API 实例ID（NULL=算法类型级默认）')
    field_path = Column(String(255), comment='输出字段取值路径（点号 + 数组下标，如 data.events[0].text；空 = 按 param_code 取顶层键）')
```

> **现状核对（2026-10-25 按实现重写）**：两列均已落库。真实模型见 `algorithm_service/infrastructure/persistence/models/algorithm_models.py:167-215`（`AlgorithmApiParam`，`to_dict` 见 `:198-215`）。
>
> - `api_id`（`:179`）：`Integer NULL`，NULL = 算法类型级默认。**不建 ForeignKey**——`apis` 归 `api_test_service`，跨服务 DB 约束违反架构红线；存在性与算法类型一致性由网关写路径校验。与上文代码块原提案的 `ForeignKey('apis.id')` 不同，以本条为准。
> - `field_path`（`:191`）：`VARCHAR(255) NULL`，无默认值、无索引。取值为点号 + 数组下标（`data.events[0].text`，`a.b.0.c` 与 `a.b[0].c` 等价），空 = 按 `param_code` 取顶层键；只有 `direction=output` 的 API 参数使用它，取值口径见 §九。迁移见 `scripts/migrations/202610/add_api_param_field_path_int1747.py`（`docker/db_bootstrap_entrypoint.py` 引导链 ㊺；列存在即 SKIP）。
> - 其余字段与 §二.1「现状核对」所列重复项一致，唯一性按 `(algorithm_type, param_code, direction)`、仅在 `deleted = false` 条件下生效。
> - `api_id` 的实施拆成两段，见 §9.5：C6a（模型 / 迁移 / 唯一索引 / 合并入口）与 C6b（执行 / 评估 / 报告消费域接线）**均已实施**（C6b 合入提交 `406b6a941`）。

### 3. ParamMapping（参数映射表）

| 字段 | 说明 | 变更 |
|------|------|------|
| keywords | 设备驱动关键字 | 新增字段（未实施） |
| api_id | API配置ID | 新增字段（已实施：C6a INT-1756） |

```python
class ParamMapping(db.Model):
    # 现有字段...

    # 新增字段
    keywords = Column(String(200), comment='设备驱动关键字（用于映射时识别来源驱动）')
    api_id = Column(Integer, nullable=True, comment='API 实例ID（NULL=算法类型级默认）')
```

> **现状核对（2026-10-25 按实现更新）**：ParamMapping 实际字段为 algorithm_type/**api_id**/source/source_param/source_direction/dimension_id/target_param/transform_type/deleted（`algorithm_service/infrastructure/persistence/models/algorithm_models.py:307-329`，`api_id` 见 `:317`）。
>
> - `api_id Integer NULL`（C6a / INT-1756）：API 实例级作用域，NULL = 算法类型级默认；**不建跨服务 ForeignKey**（与上文代码块原提案不同，以本条为准）；合并读取时 API 级行覆盖同键算法级行。消费域接线（C6b / INT-1757）**已实施**（合入提交 `406b6a941`），读取按 §10.1 的合并口径。
> - `keywords`：**仍不存在**，驱动绑定方案未实施。
> - `source` 支持 case/reference/device/api/case_config 五类来源，`source_direction` 区分输入/输出方向；映射按 algorithm_type（叠加 `api_id` 后按 API 实例）关联参数定义，不依赖 keywords。

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

> **现状核对（2026-10-25 按实现更新）**：序列化实现已迁到 `algorithm_service/infrastructure/persistence/config_cache.py` 的 `_serialize_params`（`:650-681`），按「键存在才带」的方式输出：`keywords` 不返回（列不存在）；`api_id` 由 `:678-679` 的 `if 'api_id' in p` 输出（仅 `algorithm_api_params` / `param_mappings` 的 PO 带该字段）；`field_path` 由 `:674-675` 的 `if p.get('field_path') is not None` 输出（C2 / INT-1747）。上述 `algorithm_config_loader.py` 代码块仅为原提案示意，实际实现以上述位置为准。

### 3. field_mapper.py（可选增强）

映射时可以根据 keywords/api_id 过滤参数：

```python
# 获取特定驱动的设备参数
device_params = [p for p in device_params if p.get('keywords') == target_keywords]

# 获取特定API的API参数
api_params = [p for p in api_params if p.get('api_id') == target_api_id]
```

## 七、改动清单

以下为方案实施时所需的改动清单（除标注「已实施」外均未实施）：

| 序号 | 模块 | 文件 | 改动内容 |
|------|------|------|---------|
| 1 | 后端 | algorithm_models.py | AlgorithmApiParam 新增 api_id 字段（**已实施 C6a INT-1756**；同表另有 C2 的 field_path） |
| 2 | 后端 | algorithm_models.py | ParamMapping 新增 keywords 和 api_id 字段（api_id **已实施 C6a INT-1756**，keywords 未实施） |
| 3 | 后端 | algorithm_config_loader.py | 序列化时返回 keywords 和 api_id（api_id **已实施**，实现位置 `config_cache._serialize_params`；keywords 未实施） |
| 4 | 后端 | 算法Controller | API接口支持 keywords 和 api_id 字段 |
| 5 | 前端 | AlgorithmConfigModal.vue | 设备参数增加驱动选择（复用 keywords） |
| 6 | 前端 | AlgorithmConfigModal.vue | API参数增加API选择（新增 api_id） |
| 7 | 前端 | AlgorithmConfigModal.vue | 映射配置增加驱动/API筛选功能 |

## 八、数据示例

> 以下示例为方案实施后的目标状态（含 keywords / api_id 列），与当前数据库实际表结构**部分**不符：`api_id` 列已存在（C6a / INT-1756）且消费域已接线（C6b / INT-1757），`keywords` 列尚未实施——带 keywords 值的行今天仍不可落库。

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

## 九、API 输出字段声明与取值口径（C0 裁定 2026-10-24；C1~C4 / C6a / C6b 已实施）

> **状态：C2 已实施（2026-10-24，交付提交 `ccf482002`，集成合并 `abeba6d80`）**。本节由方案一致性审计员在 INT-1745（C0）出具，配套实施卡 C1（INT-1746）/ C2（INT-1747）/ C3（INT-1748）/ C4（INT-1749）/ C6a（INT-1756）均已 done，**C6b（INT-1757，消费域接线）已实施并合入 V9.7.31（`406b6a941`，见 §9.5）**。
>
> C2 的落地落点（本节所有「已实施」判断以此为准）：
>
> | 落点 | 位置 |
> |------|------|
> | 列 | `algorithm_api_params.field_path VARCHAR(255) NULL`——`algorithm_service/infrastructure/persistence/models/algorithm_models.py:191` |
> | 迁移 | `scripts/migrations/202610/add_api_param_field_path_int1747.py`，进 `docker/db_bootstrap_entrypoint.py` 引导链 ㊺（幂等，列存在即 SKIP，全新库为全 SKIP） |
> | 三链统一入口 | `shared/utils/api_output_extractor.py`——单轮 `api_task_runner.extract_final_result`、多轮 `api_session_executor._attach_api_output_fields`、Realtime `realtime_session_executor` 共用 `extract_api_output_fields` |
> | 评估侧字段键并集 | `evaluation_service/infrastructure/evaluation_api/endpoint_worker.py:232-237`（`device ∪ api`，口径见 §9.7） |
> | 落库通路 | 网关 `api_gateway/schemas/_algorithm_api_param_schemas.py:35-37`（create）/`:58`（update）→ `algorithm_service/infrastructure/persistence/_algorithm_full_save.py:144-145`（create）/`:164-165`（update） |

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

- **字段全集**：`rounds[i].output` 覆盖该算法类型**全部** `direction=output` 的 api 参数，而不只是被映射过的参数——与设备链 `get_mapped_device_output_fields` 的「未映射恒等保留」语义对齐（恒等保留在 `algorithm_service/application/queries/field_mapping_queries.py:97-112` 的 `mapped` 构造里，`get_mapped_device_output_fields` 本身在 `:150-152`）。
- **方向过滤**：只取 `source_direction='output'`。`algorithm_service/infrastructure/persistence/config_cache.py:939-1001` 的 `_get_evaluation_mappings` 目前把 `direction` 硬编码为 `output`，实施时不得据此把 input 映射混进输出。

### 9.3 声明优先级与零声明兜底（已实施：C2）

| 优先级 | 来源 | 触发条件 | 行为 |
|-------|------|---------|------|
| 1 | `algorithm_api_params(direction=output).field_path` | 该键已声明且 `field_path` 非空 | 在**厂商原始响应**上按路径提取；语法为点号 + 数字下标，`a.b.0.c` 与 `a.b[0].c` 等价（`shared/utils/path_extractor.py:9-57`） |
| 2 | `algorithm_api_params(direction=output).param_code` | 已声明、`field_path` 为空 | 按 `param_code` 在「响应顶层」取值（= 存量行为，存量零改动；「顶层」按链路落点不同，见下） |
| 3 | `apis.meta.result_parser`（voice_llm）/ `asr_mapping` + `trans_mapping`（translation） | **该算法类型一条 output 声明都没有**（零声明） | 走既有解析器，其产出的 `asr` / `trans` / `output` 键进入第 ② 跳；单轮 / 多轮链必须打 WARNING 列出兜底键（Realtime 不兜底，见下） |
| — | 无 | 键既未声明、兜底也没有 | 不写入 `output`，不报错 |

- **不做逐键合并**：声明表与 `meta` 解析器是**互斥**的两条路——该算法类型只要有任意一条 `direction=output` 声明（`defs` 非空），就只按声明提取，`meta` 完全不参与；只有零声明才整体走 `meta` 兜底。不存在「声明补 meta 未覆盖的键」这种混合，也没有合并冲突裁决可做（`shared/utils/api_output_extractor.py:69-86`，判据在 `:78`）。
- **「响应顶层」按链路落点不同**（存量行为，C1 / C2 均未改变）：
  - 单轮（HTTP）：业务数据包在 `json.data` 里，第 2 级取 **`json.data` 的顶层键**——`api_test_service/core/api_task_runner.py:452-455,471-500`（`extract_final_result` 的 `flat_source=final_data`）。
  - 多轮 / Realtime：厂商响应没有这层包装，第 2 级取**整份厂商响应的顶层键**——`api_test_service/core/api_session_executor.py:592-608`、`api_test_service/core/realtime_session_executor.py:797`。
  - 第 1 级（`field_path` 非空）三链一律作用于**厂商原始响应**（单轮是 `json`；多轮适配器路径是 `execute` 结果的 `json`；Realtime 是 WS 聚合输出），不受上述包装差异影响。
- **Realtime 零声明不兜底、也不打 WARNING**：`api_test_service/core/realtime_session_executor.py:790-797` 调 `extract_api_output_fields` 时不传 `fallback_values`，零声明即 `SOURCE_NONE`（返回空，与改前一致）。上表第 3 行的 WARNING **只适用于单轮与多轮**两条链——`api_task_runner.py:501-504`、`api_session_executor.py:598-603`。Realtime 这一段产出的是评估**入参**字段，入参口径见 §9.6。
- **`meta` 兜底分支保留**：零声明的算法类型仍要走它，不是「补齐声明后即删除」的死代码；C3（INT-1748）只做 `VoiceLlmStrategy` 去硬编码，未删除该分支。
- 提取函数复用 `shared/utils/path_extractor.py:extract_by_path`，C2 只扩展该函数兼容 `[n]` 写法（`shared/utils/path_extractor.py:9-57`），**没有新增第二个提取器**。

### 9.4 存量兼容（不回归路径）

| 存量形态 | 落地后行为 |
|---------|-----------|
| 历史 `rounds[].output` 为字符串 | 只读兼容：`shared/utils/round_data_utils.py:21-32` 的 `normalize_round_output` 继续归一为 `{'text': ...}`；新数据不再产生字符串 output |
| 未配 `source='api'` 映射、也未声明 output 字段的老 API | 走 §9.3 兜底解析，轮次 output 只含 `asr`/`trans`/`output` 键；评估侧按 `target_param` 取不到值时沿用现有「无值不覆盖维度默认值」语义（`round_data_builder.py:206-207`）并留 ERROR 日志，不报错、不阻断执行 |
| E2E 设备链 | 不动：仍由 `convert_device_output` + `_map_round_output` 产出 `{target_param: value}`（`device_service/infrastructure/acl/algorithm_query_acl_repository.py:185-199`、`e2e_calculation_service.py:216-244`） |
| 主库现状（2026-10-24 实测） | `param_mappings` 无 `source='api'` 行（仅有 case / case_config / device / evaluation / reference）；`algorithm_api_params` 中 voice_llm 仅 `response_audio` 一条 output 声明 → **今天 API 用例没有任何路径能出评估值**，须补声明与种子数据（数据梳理，不在 C1~C6 实施范围内） |

### 9.5 实施边界与实际状态（C1~C4 / C6a / C6b 已实施）

| 项 | 卡 | 状态 | 边界 |
|---|----|------|------|
| 执行侧映射 + `rounds[i].output` 子字典 | C1 INT-1746 | 已实施 | 三条 API 链产出 `target_param` 视图；HTTP 轮次补 `answer_text`（与 Realtime 对齐），`algorithm_result.text_output` 由其拼接，不再对 `output` 做字符串拼接（`api_session_executor.py:568`）；**不动** `evaluation_service` 的取值代码 |
| `field_path` 列 + 声明驱动提取 | C2 INT-1747 | 已实施 | `algorithm_api_params` 加 `field_path VARCHAR(255) NULL`（空 = 按 `param_code`）、DTO / RPC 透传；单轮（`api_task_runner.py:408-472`）、多轮（`api_session_executor.py:592-608`）、Realtime（`realtime_session_executor.py:797`）三条链共用一个提取入口 `shared/utils/api_output_extractor.py` |
| 去硬编码 | C3 INT-1748 | 已实施 | `VoiceLlmStrategy.get_output_fields` / `process_algorithm_result` 改读配置；**删除** `map_api_results` 实现而非配置化它（`meta` 兜底分支按 §9.3 保留） |
| `transform_type` 生效 | C4 INT-1749 | 已实施 | 在 §9.2 第 ② 跳（执行侧映射处）应用一次，评估侧不重复应用；批量取变换而非逐字段 RPC |
| `api_id` 作用域·模型侧（同类型多厂商） | C6a INT-1756 | 已实施 | `algorithm_api_params` / `param_mappings` 补 `api_id`（NULL = 算法类型级默认）、模型 + 迁移（引导链 ㊻ `add_api_id_scope_int1751.py`）+ 唯一索引 + proto / DTO + `algorithm_service` 合并入口；**不建 ForeignKey**（跨服务 DB 约束违反架构红线，存在性由网关写路径校验） |
| `api_id` 作用域·消费域接线 | C6b INT-1757 | 已实施（合入 `406b6a941`） | **执行侧**：单轮 `api_task_runner.extract_final_result(..., api_id=api_config.id)`（`:415-425` 输出声明、`:429` API 参数、`:453-455` 参数映射；入口 `api_executor.py:379-380`）、建任务时的入参声明（`api_task_runner.py:175-177`）、多轮 `api_session_executor._run_rounds`（`:197-200`）、Realtime `_collect_eval_fields(..., api_id=)`（调用点 `:404-407` / `:500-503`，定义 `:769-799`）；**评估侧** `case_evaluation._resolve_evaluation_api_id`（`:96-132`，显式 `eval_params.api_id` → `test_results.api_id`）把 `api_id` 带进字段定义与映射（`:13-21`、`round_data_builder.py:56-59`），并经 `task_data` 透传到 `endpoint_worker`（`:223-228`）/ `payload_builder.build_payload(..., api_id=)`（`:67-83`）的 `GetOutputFields`；**报告侧** `report_data_builder_case_mixin` 按 `result.api_id` 取输出声明（`:94-109`）、`_result_group_mixin._load_output_fields` 按 `test_result.api_id` 取（`:192`、`:216`、`:317-330`；该快照路径上游 `algorithm_type` 恒为空串、当前不可达，见 §10.6 追加观察）；**缓存**：`result_field_mapping_queries._output_field_cache` 键改 `(algorithm_type, api_id)`（`:28`、`:71-73`、`:133`），切换 API 不再命中上一家；`GetOutputFieldsRequest` 加 `optional int32 api_id = 3`（`shared/proto/algorithm_service.proto:551-556`，`pb2` 已重生成）。**不改**：设备链 / E2E 链（`api_id` 恒为 None，行为不变，见 §9.4）；任务详情与 AI 复检的展示侧仍按算法级（§10.6 P3 跟踪） |

> **C6 与 C0 的边界（`param_mappings` 一并纳入）**：C0（本节）裁定的作用域只有「API 输出字段声明」（`algorithm_api_params(direction=output)`）；C6 把 **`param_mappings` 的 `api_id` 作用域一并纳入**，两张表用**同一套优先级**——API 实例级 > 算法类型级，且是**合并而非二选一**（同键覆盖、未覆盖键回落算法级，口径见 §10.1）。因此 C6b 的接线点不止「取输出声明」的地方：凡读 `algorithm_api_params` / `param_mappings` 的执行 / 评估 / 报告调用点都要带 `api_id`，上表 C6b 行已逐点列出；`param_mappings` 的合并键是唯一键 `(source, source_param, dimension_id)`（`target_param` 不是合并键，API 级换 target 属同键覆盖）。
>
> §一~§八 描述的 `keywords` 驱动绑定提案本身仍为提案（§二.1 的 `keywords` 未实施）；`api_id` 已按 C6a 落库、消费域 C6b 已接线（`406b6a941`）。本节只覆盖 **API 输出字段声明与取值** 这一条已实施的语义。§9.2 两跳取值链路与 §9.4 存量兼容两张表已按实现逐条核对（INT-1889 复核，行号按合入后基线更新），无需改写。

### 9.6 展示侧口径与降级行为（C3 落地，INT-1851 回写）

> 本节由方案一致性审计员在 INT-1851（INT-1748 一致性审计）出具，记录上述各卡落地后 `GetOutputFields` / 结果展示链路的**实际**代码口径，作为「实现演进裁定」。代码基线 `agent/d/int-1748` @ `1535ec52d`。

**一、字段清单来源（API 声明唯一）**

- 字段清单与类型 = `algorithm_api_params(direction=output)`，按 `(ui_order, id)` 排序；映射目标键取 `param_mappings(source='api', source_direction='output')`，无映射按恒等。
  实现：`algorithm_service/application/queries/result_field_mapping_queries.py:36-117`。
- `rounds` 轮内子键的类型/展示名取 `algorithm_device_params(direction=output)`（经既有 `GetDeviceParamsList` RPC 的 ACL 封装 `shared/clients/_grpc_algo_audio.py::algo_get_device_output_fields`，不新增 RPC），API 声明覆盖设备声明；**未声明的轮内键不输出**。设备声明不进入展示字段清单（本节裁定 3 优先且唯一）。
  实现：`shared/domain/algorithm_result_strategy.py:70-153`、`shared/domain/algorithm_result_builder.py:196-205`。
- 轮内展示名 = `{声明展示名} (第N轮)`（需求规划师 2026-10-24 裁定 E）。
- `VoiceLlmStrategy` 不再持有任何算法类型字段表；`AlgorithmStrategyFactory` 只登记 `voice_llm` 的结构语义（`rounds` 按轮展开、跳过 `evaluation` 子字典），其余算法类型落 `DefaultStrategy`。

**二、降级行为（明确但不抛错）**

| 场景 | 行为 |
|---|---|
| 该算法类型一条 output 声明都没有 | 返回 `[]` + `WARNING`（含 `algorithm_type`）；**该结果不缓存**，补齐声明后无需重启 |
| 有 output 声明但缺 `rounds`（仅对含 rounds 结构语义的类型） | `WARNING` 提示轮次展开缺失，其余字段照常返回 |
| 读取声明/映射异常 | `ERROR` 日志 + 返回 `[]` |

**三、种子与引导链**

- 设备侧声明种子 `scripts/migrations/202610/seed_voice_llm_device_output_int1748.py`（幂等、默认 dry-run；C3 分支引导链 ㊸，须排在 INT-1741 `ANALYZE` 之前，随本卡合入生效）。
- API 声明与 `source='api'` 映射种子 `scripts/migrations/202610/seed_api_eval_mapping_int1746.py`（C1 交付，同一张表不设第二份种子；其引导链步骤在 INT-1746 集成合入 V9.7.31 时丢失，待补）。
- 两份种子都未落地时，voice_llm 的展示字段只剩主库既有的 `response_audio`（`rounds` 缺失告警），属 §9.4「主库现状」的预期降级，不是静默错值。

**四、`map_api_results`**

全链路已删除（策略基类与三个实现、`ResultFieldMappingQueryHandler.map_api_results`、`algo_map_api_results` 客户端封装与 `grpc_clients` 导出）；RPC 定义与 `pb2` 保留不重生成，服务端 `MapApiResults` 改为桩，固定返回 `success=False` + 「已废弃」。

### 9.7 评估侧输出字段键 = device ∪ api（已实施：C2）

评估服务构建评估上下文时，输出字段键集合取**设备侧与 API 侧映射后输出字段的并集**：

- 实现：`evaluation_service/infrastructure/evaluation_api/endpoint_worker.py:232-237`——`output_field_keys = list(dict.fromkeys(device_keys + api_keys))`。
- 两侧键来源：
  - 设备侧 `get_mapped_device_output_field_keys`——`shared/utils/field_mapper_wrapper.py:36-41`（`mapped.device` 的键，即 `target_param`）。
  - API 侧 `get_mapped_api_output_field_keys`——`shared/utils/field_mapper_wrapper.py:43-53`（`mapped.api` 的键，`target_param`；与设备侧同构）。
- **顺序与冲突裁决**：`device` 先、`api` 追加，`dict.fromkeys` 保序去重——同键保留**先出现（device 位）**。两侧同为 `target_param` 视图，同键即同一评估维度参数，取值一致，不产生二义。
- **适用范围只有输出字段的展示 / 提取**（评估 API 请求上下文里的 `output` / `algo_results` 键集合）。**不扩到评估入参映射**——入参仍只认 `param_mappings`（`eval_input_fields` 走 `get_evaluation_input_fields`，与 `output_field_keys` 是两套口径）。

### 9.8 未配置 / 未落库显示「—」的约定

前端只读展示 `field_path` 的列（例如 React API 编辑弹窗「输出字段」页签，见 C5 / INT-1750）遵循：

- `field_path` 为空（NULL 或空串）→ 该列显示 **「—」**，不显示空白、不隐藏该行。
- **空串与 NULL 在提取侧同义**：提取器用 `if field_path:` 判真值（`shared/utils/api_output_extractor.py:62-65`），空串与 NULL 都走「按 `param_code` 取顶层键」。
- **序列化侧只有非 `None` 才带键**：`algorithm_service/infrastructure/persistence/config_cache.py:674-675` 的判据是 `is not None`，所以空串会以 `field_path: ''` 出现在字段定义里（NULL 则完全不带该键）。前端两种形态都要按「未配置」处理，不要用 `!== undefined` 之类别扭判据区分。
- 该约定只影响展示，不改变任何提取与映射行为。

## 十、`api_id` 作用域实现契约（C6a / INT-1756）

> **实现演进裁定（2026-10-25，INT-1849 方案一致性审计）**：本节按已合入 V9.7.31 的实现（交付分支 `agent/d/int-1756` @ `766d1a9af`，合入提交 `cb0b73e5d` / 返工 `b30965cf2`）回写。与 §二/§三 提案的差异以本节为准：**不建外键**；`api_id` 语义为「作用域」而不是「来源识别」。

### 10.1 语义与优先级

- `algorithm_api_params.api_id`、`param_mappings.api_id`：`NULL` = **算法类型级默认**（同类型各 API 共享），非空 = **API 实例级**，指向 `api_test_service` 的 `apis.id`（跨服务不建 DB 外键）。
- 读取优先级：**API 实例级 > 算法类型级**，且是**合并**而非二选一——同键的 API 级行覆盖算法级行，未被覆盖的键继续用算法级行；其它 `api_id` 的行不参与。
- 不传 `api_id`（存量路径）：只返回算法级行，行为与 C6a 之前一致；行里多一个 `api_id: null` 键。

### 10.2 唯一索引（算法级 / API 级各一条，统一 `NULLS NOT DISTINCT`）

| 索引 | 定义（均含 `WHERE deleted = false`） |
|---|---|
| `uq_algorithm_api_param_algo_level` | UNIQUE `(algorithm_type, param_code, direction)` `NULLS NOT DISTINCT` … `AND api_id IS NULL` |
| `uq_algorithm_api_param_api_level` | UNIQUE `(algorithm_type, api_id, param_code, direction)` `NULLS NOT DISTINCT` … `AND api_id IS NOT NULL` |
| `uq_param_mapping_algo_level` | UNIQUE `(algorithm_type, source, source_param, dimension_id)` `NULLS NOT DISTINCT` … `AND api_id IS NULL` |
| `uq_param_mapping_api_level` | UNIQUE `(algorithm_type, api_id, source, source_param, dimension_id)` `NULLS NOT DISTINCT` … `AND api_id IS NOT NULL` |
| `idx_algorithm_api_params_api_id` / `idx_param_mappings_api_id` | 普通部分索引 `(api_id) WHERE deleted = false` |

- 旧索引 `uq_algorithm_api_param_direction`、`uq_algorithm_source_to_dimension` 由迁移 **DROP**（不保留）。
- `NULLS NOT DISTINCT` 是必需的：PG 默认 `NULLS DISTINCT` 下 `api_id IS NULL` 的行不参与唯一约束；`param_mappings.dimension_id` 本身可空，不加会把 `(…, NULL)` 的重复插入放过去。
- 模型 `__table_args__` 仍声明上述两条旧索引（C2 并行期「不改既有索引定义」的约定），**全新库须靠引导链本步纠正**；在只跑 `create_all` 未跑引导链的库上，旧唯一键会拦住 API 级覆盖行。

### 10.3 读侧合并入口

- 合并键 = 唯一键：`algorithm_api_params` 为 `(direction, param_code)`；`param_mappings` 为 `(source, source_param, dimension_id)`——**`target_param` 不是合并键**（API 级换 target 时是同键覆盖，不是两行并存）。
- 入口：`algorithm_service/infrastructure/persistence/config_cache.py:906` `get_api_params(algorithm_type, api_id=None)`、`:923` `get_param_mapping(algorithm_type, component_type, api_id=None)`、`algorithm_service/application/queries/field_mapping_queries.py:22` `get_field_definitions(algorithm_type, api_id=None)`；`algorithm_config_queries.py:37,55` 为同名透传。
- 缓存分桶键**不变**，行携带 `api_id`（`_serialize_params` / `_serialize_mappings`）；`evaluation` 桶的四元组去重放在合并**之后**（`_get_evaluation_mappings`，`:939-1001`）。合并统一走 `config_cache._merge_level_rows(rows, api_id, key_fn)`（`:146-180`）：`api_id=None` 只留 `api_id IS NULL` 的行，传值时 API 级行按同键覆盖并占据算法级行位置、API 独有行追加。
  - **注意两种 dict 形状**：缓存行由 `_serialize_params` 产出，键名是 `code` —— `_api_param_merge_key`（`:132-134`）取 `(direction, code)` 只适用于缓存行；仓储 `list_by_algorithm` 返回的 dict 键名是 `param_code`，`result_field_mapping_queries._output_declarations`（`:154-174`）另用局部键函数 `(direction, param_code)`。把 `_api_param_merge_key` 套到仓储行会让所有行同键（`(direction, None)`）互相顶掉。
- `get_algorithm_config` / `get_algorithm_params` 按算法级（`api_id=None`）返回，不把某个 API 的行当作算法级配置透出。

### 10.4 写入路径

- proto：`GetApiParamsListRequest.api_id = 2`、`GetParamMappingForComponentRequest.api_id = 3`、`GetFieldMappingsRequest.api_id = 3`，均为 `optional int32`（presence 区分「未传」与「显式传值」；`api_id=0` 与未传可区分）；响应 message 不变（仍是 JSON 字符串，行带 `api_id`）。见 `shared/proto/algorithm_service.proto:503-533`。C6b 另把 `GetOutputFieldsRequest.api_id = 3` 加上（`:551-556`），本条不改变响应结构。
- 网关 DTO：`_algorithm_api_param_schemas.py:20,43`、`_algorithm_dimension_schemas.py:133,144,179,190` 的创建 / 更新 schema 加可选 `api_id`（`ge=1`，snake/camel 均可入参，沿用 `APIModel` 既有约定）。
- 作用域校验：`api_gateway/application/services/algorithm/algorithm_command_service.py:47` `_validate_api_scope` —— `api_id` 必须为正整数、对应 api 必须存在、其 `algorithm_type` 必须与参数行一致，否则 **400**（DB 无 FK，只能在网关保证）。更新载荷不带 `algorithm_type` 时只校验存在性。
- `create_param` 必须显式回写 `param_type_source`（`algorithm_command_service.py:225-228`）：schema 是 `extra="ignore"`，否则带 `api_id` 的 API 参数会被建进 `algorithm_device_params`（该表无 `api_id` 列，静默忽略）。
- 算法定义「整份保存」的 upsert 只管理 `api_id IS NULL` 的行（`_algorithm_full_save.py:105-111,296-300`），API 实例级配置不会被「提交集外软删」误删。

### 10.5 迁移、引导链与部署顺序

- 脚本 `scripts/migrations/202610/add_api_id_scope_int1751.py`：默认 dry-run、`--apply` 执行、`--rollback [--apply]` 回滚；幂等（列/索引存在即 SKIP）；`SET lock_timeout='10s'`，等锁超时抛 `55P03` 原样上抛不吞；执行前统计两个层级的重复组，有重复直接 `[FAIL]` 退出（码 2）。
- 已接入引导链 `docker/db_bootstrap_entrypoint.py:206`（㊻，带 `--apply`），排在 ㊽ `analyze_stale_statistics_int1741.py` **之前**（ANALYZE 必须保持末位，`tests/unit/test_int1741_analyze_stale_statistics.py` 钉死）。
- 部署：`db_bootstrap` 是 compose 门控服务（`service_completed_successfully`），重建 db_bootstrap 镜像后随 `docker compose up` 对目标库执行本步；**未跑本步的库上新镜像读参数表会 `UndefinedColumn`**，因此 `db_bootstrap` 必须先于各服务完成。
- 存量安全（2026-10-25 主库只读实测）：`param_mappings` 未删除 959 行（其中 `dimension_id IS NULL` 1 行）、`algorithm_api_params` 未删除 7 行；按两条新算法级唯一键统计**重复组均为 0**，加索引不会产生重复键失败。主库当前仍是迁移前形态（无 `api_id` 列、旧两条唯一索引），迁移随部署执行。
- 与相邻卡：INT-1784（冗余索引下线）只 DROP「名字 + 定义双匹配且非 UNIQUE」的 22 条 btree，不涉及本节四条唯一索引与两条 `idx_*_api_id`；其脚本尚未合入 V9.7.31，合入时其引导链步同样须排在 ㊽ 之前（两步互不依赖，无次序要求）。INT-1794 结论为「不需要整体重新设计」，不改这两张表的关系模型，与本迁移不冲突。

### 10.6 未收口事项（跟踪，不是 C6a 的实现偏差）

- **C6b（INT-1757）已实施**：合入提交 `406b6a941`（按补丁 `int1757_c6b_rebased_on_v9731.patch` 在含 INT-1748 返工的基线上重解）。`api_id` 已接到执行 / 评估 / 报告调用点，`result_field_mapping_queries._output_field_cache` 键为 `(algorithm_type, api_id)`；逐点接线清单与边界见 §9.5。
- **INT-1863 已收口**：合入提交 `2316a703b`。`algorithm_service/infrastructure/persistence/_algorithm_dimension_repositories.py:265-284` 的 `list_for_dimension` 与 `:286-346` 的 `sync_for_dimension` 显式带 `api_id` 形参并按作用域过滤（默认 `api_id IS NULL`），新建行显式落 `api_id`——**维度同步只管理算法级（`api_id IS NULL`）行，API 实例级维度映射由 API 作用域自己的写路径负责**，同一 `(source_param, dimension_id)` 的算法级与 API 级行并存时，一轮同步后 API 级行的 `target_param` / `source_direction` / `deleted` 均不变。两个调用方（`interfaces/grpc/mixins/dimension_mixin.py:241` 同步、`param_query_mixin.py:210` 维度读取）走默认算法级口径。
- 前端 C5（INT-1750）映射页签读路径 `GET /algorithm/mappings?algorithm_type=X&source_type=api` 与写路径**仍不带 `api_id`**，界面只能看/改算法级配置；API 实例级配置目前只能经接口写（事实未变，仍为待办）。

**代码审计遗留 P3（INT-1889 复核结论，本卡不修）**

| # | 审计项 | 复核结论 | 是否写进跟踪 |
|---|---|---|---|
| 1 | `result_field_mapping_queries._api_param_merge_key` 已无调用的 import | 成立：`algorithm_service/application/queries/result_field_mapping_queries.py:11` 仍在 import，但该文件实际用局部键函数（`param_code` 口径），`_api_param_merge_key` 只出现在 docstring（`:60`、`:163`）。属清理项，不改行为 | 记于此，不单开卡 |
| 2 | `task_service/application/task/task_query_service.py:397`、`evaluation_service/application/handlers/ai_review_checker.py:277` 仍按算法级取输出声明 | 成立：前者任务详情取 `algo_get_output_fields(algorithm_type)`（透传层 `task_service/infrastructure/acl/algorithm_acl_dimension_query_tx_mixin.py:136-143` 亦无 `api_id` 形参）；后者 `build_payload(...)`（`:277-283`）不传 `api_id`。主库当前无 API 级行（`api_id` 全 NULL），今天无可见差异；一旦某 API 实例配了自己的输出声明，「任务详情 / AI 复检」仍显示算法级声明 | **是**，列为跟踪项（需另开卡补接线） |
| 3 | `voice_llm` 走策略硬编码声明、短路在 `api_id` 分支之前 | **不成立**：`shared/domain/algorithm_result_strategy.py` 的 `VoiceLlmStrategy` 已无硬编码字段表（C3 / INT-1748 删除，见 §9.6），字段清单完全由入参 `output_fields` 驱动；仓内唯一固定字段表 `shared/constants/device_fields.py` 只服务设备侧（默认策略）。零声明时走的 `apis.meta.result_parser` 兜底本就按算法类型口径（§9.3 优先级 3），不属于「短路」 | 不写 |
| 4 | `_output_field_cache` 只在 `clear_cache()` 清、仓库内无调用方 | 成立：`result_field_mapping_queries.py:332` 定义 `clear_cache`，全仓无调用方（仅单测）。声明被写入后进程内缓存不会自动失效，需重载 / 重启算法服务——**C6b 之前同样如此**，不是本次引入；键改 `(algorithm_type, api_id)` 只增加分桶数，未改变失效语义 | 记于此 |

**本轮追加观察**：`report_service/application/services/report_task_generator.py:546-569` 的 `field_mappings` 快照按 `algorithm_type` 聚合（报告 meta 的 `field_mappings` 列 schema 即 `{algorithm_type: …}`，`report_models.py:104`），C6b 未改它；`ExtractAllResultFields` / `GetTimelineFields` / `GetFieldMapping`（`result_field_mapping_queries.py:239`、`:256`、`:269`）与 `BuildApiRequestData`（`field_mapping_queries.py:183`）仍按算法级取，**仓内无调用方**，不影响现有行为。

- **预存缺陷（与 C6b 无关，建议另开卡）**：`evaluation_service/infrastructure/persistence/_result_group_mixin.py:184` 的 `algorithm_type = ''` 自 P8 拆分后从未赋值，使同方法内的 `_load_output_fields` / `_load_device_output_fields` 恒返回空清单（两者都是 `if algorithm_type:` 短路，`:317-333`），于是该处按 `test_result.api_id` 的接线（`:216`）实际取不到任何声明，预提取进 `result_data['algorithm_results']` 的快照只含 aux 维度参数、不含 API 输出声明；报告侧 `report_data_builder_case_mixin.py:80-87` 命中快照即直接使用，不再走带 `api_id` 的实时回退分支（`:89-109`）。修法：按 `test_result` 关联的用例补 `algorithm_type`（`TestResultDTO` 现无该字段，需从 task/test_case 推断）。

> **C4 实施核对（2026-10-25，一致性审计 INT-1869）**：三条 API 执行链（HTTP 多轮 / HTTP 单轮 / Realtime）在写 `rounds[i].output` 前经 `api_test_service/domain/services/eval_output_transform_service.py` 批量变换一次，变换实现仍是 algorithm_service 的 `FieldTransformService`，一次 RPC `ConvertFieldValues`（`algorithm_service.proto:154-160`）；评估侧只按 `target_param` 取值，无第二处变换。仅 `source ∈ {api, device}` 的映射由执行侧变换；`case` / `reference` 来源仍在评估入参提取路径应用一次（与执行侧互斥）。E2E 设备链（`convert_device_output`）未接线 `transform_type`，主库该来源映射当前全为 `none`。详见 [14_Evaluation适配方案.md](./14_Evaluation适配方案.md) §6.5 第 4 条。

