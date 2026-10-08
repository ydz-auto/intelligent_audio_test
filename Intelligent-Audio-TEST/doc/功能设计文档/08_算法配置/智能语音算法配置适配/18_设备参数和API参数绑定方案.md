# 设备参数和API参数绑定方案

> **实施状态**：本文档描述的 keywords/api_id 绑定方案为**设计提案，尚未实施**。经代码核对：`AlgorithmDeviceParam`、`AlgorithmApiParam`、`ParamMapping` 三个模型中均**不存在** keywords/api_id 字段。当前设备驱动的解析由 `backend/utils/device_driver/registry.py` 按 `(app_type, version, platform)` 三元组完成（AppType/DevicePlatform 枚举驱动），keywords 字符串匹配机制仍保留于 `driver_factory.py` 的专用驱动注册表（`_specialized_drivers`）。文中标注"现状核对"处为与代码库对齐的说明，其余保留原提案内容供后续实施参考。

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
