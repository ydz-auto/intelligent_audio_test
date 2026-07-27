# Proto 接口定义

本目录存放 gRPC proto 定义文件，用于跨服务调用接口定义。

## 文件说明

| 文件 | 提供方 | 调用方 | 说明 |
|------|--------|--------|------|
| `e2e_service.proto` | e2e_test_service | task_service / api_gateway | E2E 测试服务接口（音频、设备驱动、播放编排、设备结果采集、环境设备） |
| `task_service.proto` | task_service | api_gateway / e2e_test_service | 任务执行引擎服务接口 |
| `api_test_service.proto` | api_test_service | api_gateway 等 | API 测试服务接口 |

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
protoc --python_out=. --grpc_python_out=. -I. e2e_service.proto task_service.proto api_test_service.proto
```

生成后的文件（`*_pb2.py` 与 `*_pb2_grpc.py`）会位于本目录，作为 Python 包的一部分被各服务 import。

### 依赖

```bash
pip install grpcio grpcio-tools
```

## 重新生成

每次修改 `.proto` 文件后，需重新执行上述 `protoc` 命令以更新生成的 Python 代码。
