# 接入指南 · 实体设备 E2E 测试（physical）

> 受众：接入新物理设备（Android / HarmonyOS 等）的开发者。
> 核心原则：**执行器（rounds_loop）通用，特殊处理全在 driver**。

## 一、接入总览（3 件事）

| 你要做的事 | 放哪 | 写代码？ |
| --- | --- | --- |
| ① 设备驱动（连接/放音/采集/操作） | `device_service/infrastructure/drivers/你的设备.py` | ✅ |
| ② 注册（@register_driver） | 同文件装饰器 | ✅（几行） |
| ③ 配置（设备记录/驱动参数/用例） | Devices 表 + 设备配置 + 用例 | ❌ 纯配置 |

## 二、写驱动（继承 BaseDeviceDriver）

```python
# drivers/my_device_driver.py
from device_service.infrastructure.drivers.base_driver import BaseDeviceDriver
from device_service.infrastructure.drivers.registry import register_driver
from device_service.infrastructure.drivers.driver_types import DevicePlatform

@register_driver
class MyDeviceDriver(BaseDeviceDriver):
    app_type = 'my_device'                        # 自定义开放字符串
    version = 'v1'
    platform = DevicePlatform.ANDROID             # 封闭枚举: android / harmonyos / ios
    dependencies = []                             # 可选: SDK 依赖（缺失自动标记）

    def initialize(self, device_sn, task_id=None, test_case_id=None, **kw): ...
    def pre_process(self, device_sn, **kw): ...   # 每轮前（音量/App 状态/噪声环境设置）
    def post_process(self, device_sn, **kw): ...  # 每轮后（采集结果/回采检测）
    def get_results(self, device_sn, **kw): ...   # 本轮输出（音频/文本/SPL）
    def teardown(self, device_sn, **kw): ...      # 关 App/清理
```

**白拿**（BaseDeviceDriver）：
- Redis 分布式停止/暂停（多实例一致，降级进程内注册表）
- UI 抓取降级标记、teardown 自动关 App
- 播放时间戳提取（`_extract_playback_timestamps`）
- `_wait_for_condition`（超时 + 停止检查）、统一日志

## 三、注册（Key 三元组）

```python
# Key = (app_type, version, platform)
# driver_registry.resolve(app_type, version, platform)  版本可降级 v1
# @register_driver 装饰即注册；依赖缺失自动标记 MISSING_DEPENDENCY（仍展示）
```

- `app_type` / `version`：**自定义开放字符串**（每个新 App 驱动自声明，不需改枚举）
- `platform`：**封闭枚举**（DevicePlatform：android / harmonyos / ios）

## 四、用例特殊处理（适用算法）

| 用例场景 | 配什么 | 适用算法 | 谁来处理 |
| --- | --- | --- | --- |
| 正常轮 | 每轮输入音频 | 全部 | rounds_loop 通用编排 |
| **打断轮（插话）** | `is_interruption: true`（+`ai_start_timeout`） | **仅 voice_llm 等对话类** | 执行器透传 → **驱动 post_process 回采 PCM 检测 AI 开口**（参照 harmony_xiaoyichat `_wait_ai_reply_start_via_pcm`） |
| **拒识** | `is_reject: true` + `timing` | **仅 voice_llm（reject_judge）** | 评估侧计算器；驱动如实采集 |
| 设备输出字段 | field_mapper `get_mapped_device_output_fields` | 按算法各自声明 | 配置 |

> **打断检测是驱动能力**（只有驱动能回采设备声学）——对应 Realtime 适配器的 `wait_ai_speaking`。打断/拒识仅 voice_llm 这类对话/拒识算法需要，其他算法不需要。

## 五、配置 + 建任务

- **Devices 表**：设备类型 / 序列号 / 驱动参数（app_type 关联驱动）
- **建任务**：case_devices `device_type=physical` + device_id（设备侧），可与 API 目标混跑（同一用例设备侧 + API 侧分别执行）

## 六、验证

1. **扫描/初始化冒烟**：`driver_registry.list_drivers()` 可见、依赖无缺失、设备可初始化
2. **单用例跑通**：正常轮 → 打断轮（验证回采检测）
3. **回归**：E2E 集成测试不回归

## 七、FAQ

- **Q：设备版本差异大？** `resolve(app_type, version, platform)` 支持版本降级 v1，同 app_type+platform 下任意可用版本兜底。
- **Q：驱动依赖 SDK 缺失？** 注册时自动标记 MISSING_DEPENDENCY，管理界面可见，不影响其他驱动。
- **Q：打断检测必须回采 PCM？** 是——只有驱动能访问设备声学数据；Realtime 侧对应的是协议事件 `wait_ai_speaking`。
