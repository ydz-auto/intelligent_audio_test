# 设备与 SPL 域评测（INT-2459）

M1 设备 / SPL 域只读卡提供的工具契约、Skill 触发与实测三组评测。

## 文件

| 文件 | 说明 |
|---|---|
| `fixtures.py` | 网关实测形状的样例数据、10 条域任务（设备 6 + SPL 4）、Skill 触发正负例 |
| `skill_support.py` | 3 个 Skill 的装载、触发词解析与确定性路由（词面匹配） |
| `test_device_query_tool.py` | `device_query` 注册口径、动作 → 目标映射、参数白名单、权限收窄、10 条任务 |
| `test_device_skill.py` | `device-operations` / `spl-calibration` / `driver-proposal` 的 L1/L2、只读 allowed-tools、触发准确率 ≥ 90% |
| `test_device_live_contract.py` | 真实 docker 网关实测（默认跳过，见下） |

## 动作口径

- 设备只读动作直接复用共享 MCP 注册表的 `device_*` GET 工具（外部 MCP 205 项不变）；
- SPL 只读**没有独立意图工具**（§6.1 只有写工具 `spl_calibrate`），也没有对外
  MCP 工具：物理域 `/api/v1/spl` 与数字域 `/api/v1/digital-spl` 的只读端点都是
  `device_query` 的动作，目标定义在 `shared/agent_tools/device_tools.py`；
- 工具级权限是 `device:read` / `spl:read` / `digital_spl:read` 的并集（只决定
  可见性），调用时按 `action` 收窄，避免跨域读；
- `ids` / `device_ids` 按服务端契约转逗号串（网关 `request.args` 只保留重复参数的
  最后一个值）；动作不支持的参数在工具层直接拒绝（网关 `extra=ignore` 会静默忽略）。

## 触发评测

确定性代理：用 L1 description 的「触发词」+ 本域核心词做词面匹配，验证描述能让
本域问题稳定命中、域外问题不误命中。真实模型级触发评测归统一评测器。

## 实测

```bash
AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
    tests/agent_eval/domains/device/test_device_live_contract.py -s
```

前置：docker 栈已起（网关 15000），`dev_user` / `dev_password` 可登录，
device_service 固定跑宿主机 gRPC 50053。
