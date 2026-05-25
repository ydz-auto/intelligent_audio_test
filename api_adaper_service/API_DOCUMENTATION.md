# 音频处理服务 API 文档

## 1. 服务概述

该服务提供音频处理功能，支持语音转文字和翻译，通过WebSocket与第三方服务进行通信。

## 2. 基础信息

- 服务名称：audio-executor
- 基础URL：`http://localhost:{port}`
- 默认端口：8000
- 支持的请求格式：JSON
- 认证方式：无（开发环境）

## 3. API 接口

### 3.1 健康检查

#### 3.1.1 接口描述
用于检查服务是否正常运行。

#### 3.1.2 请求信息
- **请求方法**：GET
- **请求URL**：`/health`
- **请求参数**：无

#### 3.1.3 响应信息
- **状态码**：200（健康）/ 500（不健康）
- **响应格式**：JSON

#### 3.1.4 响应示例
```json
{
  "status": "healthy",
  "service": "audio-executor",
  "no_heartbeat": true,
  "frame_duration_ms": 80,
  "current_concurrency": 0,
  "max_concurrency": 100
}
```

### 3.2 创建音频处理任务

#### 3.2.1 接口描述
创建一个新的音频处理任务，返回任务ID和相关查询URL。

#### 3.2.2 请求信息
- **请求方法**：POST
- **请求URL**：`/api/create_task`
- **请求参数**：

| 参数名 | 类型 | 必填 | 描述 | 示例值 |
|--------|------|------|------|--------|
| audio_path | string | 是 | 音频文件路径 | `/path/to/audio.wav` |
| trans_direction | string | 是 | 翻译方向，格式为"源语言2目标语言" | `zh2en` |
| vendor | string | 否 | 服务供应商，默认值：`volc_ast` | `mock` |

#### 3.2.3 请求示例
```json
{
  "audio_path": "test_audio.wav",
  "trans_direction": "zh2en",
  "vendor": "mock"
}
```

#### 3.2.4 响应信息
- **状态码**：200（成功）/ 400（参数错误）/ 500（服务器错误）
- **响应格式**：JSON

#### 3.2.5 响应示例
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_1234567890",
    "status_url": "http://localhost:8000/api/get_status/task_1234567890",
    "frame_results_url": "http://localhost:8000/api/get_frame_results/task_1234567890",
    "final_result_url": "http://localhost:8000/api/get_final_result/task_1234567890",
    "msg": "任务已创建，处理完成后可分别查询中间帧结果和最终聚合结果"
  }
}
```

### 3.3 获取任务状态

#### 3.3.1 接口描述
获取指定任务的当前状态。

#### 3.3.2 请求信息
- **请求方法**：GET
- **请求URL**：`/api/get_status/{task_id}`
- **路径参数**：
  - `task_id`：任务ID

#### 3.3.3 响应信息
- **状态码**：200（成功）/ 404（任务不存在）/ 500（服务器错误）
- **响应格式**：JSON

#### 3.3.4 响应示例
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_1234567890",
    "status": "completed",
    "total_frames": 10,
    "error_msg": ""
  }
}
```

#### 3.3.5 状态说明
- `pending`：任务等待中
- `processing`：任务处理中
- `completed`：任务已完成
- `failed`：任务失败

### 3.4 获取帧中间结果

#### 3.4.1 接口描述
获取指定任务的帧中间结果，支持分页查询。

#### 3.4.2 请求信息
- **请求方法**：GET
- **请求URL**：`/api/get_frame_results/{task_id}`
- **路径参数**：
  - `task_id`：任务ID
- **查询参数**：

| 参数名 | 类型 | 必填 | 描述 | 默认值 |
|--------|------|------|------|--------|
| page | integer | 否 | 页码 | 1 |
| page_size | integer | 否 | 每页大小 | 1000 |
| all | boolean | 否 | 是否返回所有结果 | false |

#### 3.4.3 响应信息
- **状态码**：200（成功）/ 404（任务不存在）/ 500（服务器错误）
- **响应格式**：JSON

#### 3.4.4 响应示例
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_1234567890",
    "total_frames": 10,
    "page": 1,
    "page_size": 1000,
    "total_pages": 1,
    "frame_results": [
      {
        "frame_seq": 1,
        "asr_text": "你好",
        "trans_text": "Hello",
        "timestamp": "2026-01-07T10:00:00.000Z"
      },
      {
        "frame_seq": 2,
        "asr_text": "世界",
        "trans_text": "World",
        "timestamp": "2026-01-07T10:00:00.080Z"
      }
    ]
  }
}
```

### 3.5 获取最终聚合结果

#### 3.5.1 接口描述
获取指定任务的最终聚合结果。

#### 3.5.2 请求信息
- **请求方法**：GET
- **请求URL**：`/api/get_final_result/{task_id}`
- **路径参数**：
  - `task_id`：任务ID

#### 3.5.3 响应信息
- **状态码**：200（成功）/ 404（任务不存在）/ 500（服务器错误）
- **响应格式**：JSON

#### 3.5.4 响应示例
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_1234567890",
    "final_asr_result": "你好 世界",
    "final_trans_result": "Hello World",
    "total_frames": 10,
    "status": "completed",
    "start_time": "2026-01-07T10:00:00.000Z",
    "end_time": "2026-01-07T10:00:01.000Z"
  }
}
```

### 3.6 删除任务

#### 3.6.1 接口描述
删除指定任务及其相关数据。

#### 3.6.2 请求信息
- **请求方法**：DELETE
- **请求URL**：`/api/delete_task/{task_id}`
- **路径参数**：
  - `task_id`：任务ID

#### 3.6.3 响应信息
- **状态码**：200（成功）/ 404（任务不存在）/ 500（服务器错误）
- **响应格式**：JSON

#### 3.6.4 响应示例
```json
{
  "code": 0,
  "msg": "任务task_1234567890已成功删除",
  "data": {
    "task_id": "task_1234567890"
  }
}
```

## 4. 错误码说明

| 错误码 | 描述 |
|--------|------|
| 0 | 成功 |
| -1 | 失败 |

## 5. 数据格式说明

### 5.1 音频文件要求
- 格式：WAV
- 采样率：16000 Hz
- 声道数：1（单声道）
- 位深：16位

### 5.2 支持的翻译方向
- `zh2en`：中文到英文
- 其他方向可根据配置支持

### 5.3 支持的供应商
- `volc_ast`：火山引擎ASR服务
- `mock`：模拟服务（用于测试）

## 6. 调用流程示例

1. 调用 `POST /api/create_task` 创建任务，获取 `task_id`
2. 定期调用 `GET /api/get_status/{task_id}` 检查任务状态
3. 任务处理中可调用 `GET /api/get_frame_results/{task_id}` 获取中间结果
4. 任务完成后调用 `GET /api/get_final_result/{task_id}` 获取最终结果
5. 不再需要时调用 `DELETE /api/delete_task/{task_id}` 删除任务

## 7. 部署和运行

### 7.1 启动服务
```bash
# 单端口启动
python -m app.main --port 8000

# 多端口启动
python -m app.main --ports 8000,8001,8002
```

### 7.2 环境变量
服务支持通过环境变量配置，详见 `.env.example` 文件。

## 8. 测试

### 8.1 运行测试脚本
```bash
# 运行API测试
python test_api.py --ports 8000

# 运行高并发测试
python test_high_concurrency.py
```

## 9. 注意事项

1. 服务目前使用Flask开发服务器，生产环境建议使用Gunicorn或uWSGI
2. 服务默认配置为无心跳模式，可通过配置文件修改
3. 任务数据默认保存60分钟，可通过配置文件修改
4. 最大存储帧数为100000，可通过配置文件修改

## 10. 版本信息

- 版本：1.0.0
- 更新日期：2026-01-07
- 开发环境：Python 3.12, Flask 3.0+