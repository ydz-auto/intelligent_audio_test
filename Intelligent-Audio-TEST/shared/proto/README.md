# Proto 接口定义

本目录存放 gRPC proto 定义文件，用于跨服务调用接口定义。

## 文件说明

| 文件 | 提供方 | 调用方 | 说明 |
|------|--------|--------|------|
| `e2e_service.proto` | e2e_test_service / audio_service / device_service | task_service / api_gateway / 各服务 | E2E 执行、音频播放/编排/CRUD、设备驱动/播放设备/SPL（三个服务共用此 proto，待拆分为独立 proto） |
| `task_service.proto` | task_service | api_gateway / e2e_test_service / evaluation_service | 任务执行引擎 + 任务/用例/标签/算法配置 CRUD + 跨服务数据查询 |
| `api_test_service.proto` | api_test_service | api_gateway | API 测试服务接口 |
| `evaluation_service.proto` | evaluation_service | api_gateway / task_service | 评估服务 + 评估配置 + 评估数据查询 |
| `adapter_service.proto` | api_adapter_service | e2e_test_service / task_service | 多厂商 API 适配器服务 |
| `algorithm_service.proto` | algorithm_service | api_gateway / task_service | 算法分组/定义管理 |
| `report_service.proto` | report_service | api_gateway | 报告配置服务 |

## 待办

- `e2e_service.proto` 拆分为 `audio_service.proto` / `device_service.proto` / `e2e_test_service.proto`，消除三个服务共用一个 proto 的问题

## Message 设计约定

- 简单字段使用具体类型（`string`、`int32`、`bool`、`double`）
- 复杂对象使用 `string`（JSON 序列化），避免 proto 过于复杂
- 列表使用 `repeated`
- 所有 `Request`（如有任务上下文）均包含 `string task_id` 字段
- 所有 `Response` 均包含统一结构：
  - `bool success`
  - `string message`
  - `string data`（JSON 序列化的结果）

## 生成 Python 代码

在当前目录（`shared/proto`）下执行：

```bash
protoc --python_out=. --grpc_python_out=. -I. e2e_service.proto task_service.proto api_test_service.proto evaluation_service.proto adapter_service.proto algorithm_service.proto report_service.proto
```

生成后的文件（`*_pb2.py` 与 `*_pb2_grpc.py`）会位于本目录，作为 Python 包的一部分被各服务 import。

### 依赖

```bash
pip install grpcio grpcio-tools
```

## 重新生成

每次修改 `.proto` 文件后，需重新执行上述 `protoc` 命令以更新生成的 Python 代码。
