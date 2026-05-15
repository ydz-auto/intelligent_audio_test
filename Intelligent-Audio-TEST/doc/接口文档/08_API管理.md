# API管理接口

## 8. API配置管理接口

### 8.1 获取API列表
#### 8.1.1 接口信息

- **URL**: `/api/v1/apis`
- **方法**: `GET`
- **功能**: 获取API配置列表，支持分页、搜索和筛选

#### 8.1.2 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| page | INTEGER | query | 否 | 页码，默认1 |
| per_page | INTEGER | query | 否 | 每页记录数，默认10 |
| keyword | STRING | query | 否 | 搜索关键字，支持名称和描述 |
| status | STRING | query | 否 | 状态筛选：online/offline |

#### 8.1.3 响应示例

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "name": "唤醒词检测API",
        "vendor": "Example Inc",
        "api_url": "https://api.example.com/wakeword/v1/",
        "description": "用于测试唤醒词检测功能的API",
        "status": "online",
        "meta": {
          "协议": "HTTPS",
          "环境": "生产环境",
          "版本": "v1"
        },
        "default_max_process": 10,
        "default_max_timeout": 30,
        "default_max_audio_duration": 10,
        "health_score": 98,
        "endpoints": [
          {
            "id": "1_0",
            "endpoint": "https://api.example.com/wakeword/v1/",
            "name": "主节点",
            "max_process": 10,
            "max_timeout": 30,
            "max_audio_duration": 10,
            "status": "online",
            "health_score": 98,
            "priority": 1,
            "description": "主服务节点"
          },
          {
            "id": "1_1",
            "endpoint": "https://api-backup.example.com/wakeword/v1/",
            "name": "备用节点",
            "max_process": 5,
            "max_timeout": 30,
            "max_audio_duration": 10,
            "status": "online",
            "health_score": 95,
            "priority": 2,
            "description": "备用服务节点"
          }
        ],
        "created_at": "2023-01-01T10:00:00",
        "updated_at": "2023-01-01T10:00:00"
      }
    ],
    "total": 10,
    "page": 1,
    "per_page": 10,
    "pages": 1
  }
}
```

### 8.2 获取单个API配置详情
#### 8.2.1 接口信息

- **URL**: `/api/v1/apis/:id`
- **方法**: `GET`
- **功能**: 获取单个API配置的详细信息

#### 8.2.2 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| id | INTEGER | path | 是 | API ID |

#### 8.2.3 响应示例

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "name": "唤醒词检测API",
    "vendor": "Example Inc",
    "api_url": "https://api.example.com/wakeword/v1/",
    "description": "用于测试唤醒词检测功能的API",
    "status": "online",
    "meta": {
      "协议": "HTTPS",
      "环境": "生产环境",
      "版本": "v1"
    },
    "default_max_process": 10,
    "default_max_timeout": 30,
    "default_max_audio_duration": 10,
    "health_score": 98,
    "endpoints": [
      {
        "id": "1_0",
        "endpoint": "https://api.example.com/wakeword/v1/",
        "name": "主节点",
        "max_process": 10,
        "max_timeout": 30,
        "max_audio_duration": 10,
        "status": "online",
        "health_score": 98,
        "priority": 1,
        "description": "主服务节点"
      },
      {
        "id": "1_1",
        "endpoint": "https://api-backup.example.com/wakeword/v1/",
        "name": "备用节点",
        "max_process": 5,
        "max_timeout": 30,
        "max_audio_duration": 10,
        "status": "online",
        "health_score": 95,
        "priority": 2,
        "description": "备用服务节点"
      }
    ],
    "created_at": "2023-01-01T10:00:00",
    "updated_at": "2023-01-01T10:00:00"
  }
}
```

### 8.3 新增API配置
#### 8.3.1 接口信息

- **URL**: `/api/v1/apis`
- **方法**: `POST`
- **功能**: 创建新的API配置

#### 8.3.2 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| name | STRING | body | 是 | API名称 |
| vendor | STRING | body | 否 | API提供商 |
| api_url | STRING | body | 否 | API基础URL |
| description | STRING | body | 否 | API描述 |
| meta | JSON | body | 是 | API元数据 |
| default_max_process | INTEGER | body | 否 | 默认最大进程数，默认5，范围1-100 |
| default_max_timeout | INTEGER | body | 否 | 默认最大超时时间（秒），默认30，范围1-300 |
| default_max_audio_duration | INTEGER | body | 否 | 默认最大音频时长（秒），默认60，范围1-3600 |
| status | STRING | body | 否 | 状态，默认online |
| endpoints | ARRAY | body | 否 | API端点列表，每个端点可配置独立的进程数等参数 |

##### endpoints 数组元素结构：
| 参数名 | 类型 | 必需 | 描述 |
|--------|------|------|------|
| endpoint | STRING | 是 | API端点URL |
| name | STRING | 否 | 端点名称 |
| max_process | INTEGER | 否 | 该端点的最大进程数，默认使用API的default_max_process |
| max_timeout | INTEGER | 否 | 该端点的最大超时时间（秒），默认使用API的default_max_timeout |
| max_audio_duration | INTEGER | 否 | 该端点的最大音频时长（秒），默认使用API的default_max_audio_duration |
| status | STRING | 否 | 端点状态，默认online |
| priority | INTEGER | 否 | 端点优先级（数值越大优先级越高），默认0 |
| description | STRING | 否 | 端点描述 |

#### 8.3.3 请求示例

```json
{
  "name": "语音识别API",
  "vendor": "Example Inc",
  "api_url": "https://api.example.com/asr/v1/",
  "description": "用于测试语音识别功能的API",
  "meta": {
    "协议": "HTTPS",
    "环境": "生产环境",
    "版本": "v2",
    "api_key": "your-api-key"
  },
  "default_max_process": 10,
  "default_max_timeout": 30,
  "default_max_audio_duration": 10,
  "endpoints": [
    {
      "endpoint": "https://api.example.com/asr/v1/",
      "name": "主节点",
      "max_process": 20,
      "max_timeout": 25,
      "priority": 1,
      "description": "主服务节点"
    },
    {
      "endpoint": "https://api-backup.example.com/asr/v1/",
      "name": "备用节点",
      "max_process": 10,
      "priority": 2,
      "description": "备用服务节点"
    }
  ]
}
```

#### 8.3.4 响应示例

```json
{
  "code": 0,
  "message": "API配置创建成功",
  "data": {
    "id": 2
  }
}
```

### 8.4 更新API配置
#### 8.4.1 接口信息

- **URL**: `/api/v1/apis/:id`
- **方法**: `PUT`
- **功能**: 更新现有API配置

#### 8.4.2 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| id | INTEGER | path | 是 | API ID |
| name | STRING | body | 否 | API名称 |
| vendor | STRING | body | 否 | API提供商 |
| api_url | STRING | body | 否 | API基础URL |
| description | STRING | body | 否 | API描述 |
| meta | JSON | body | 否 | API元数据 |
| default_max_process | INTEGER | body | 否 | 默认最大进程数，范围1-100 |
| default_max_timeout | INTEGER | body | 否 | 默认最大超时时间（秒），范围1-300 |
| default_max_audio_duration | INTEGER | body | 否 | 默认最大音频时长（秒），范围1-3600 |
| status | STRING | body | 否 | 状态：online/offline |
| endpoints | ARRAY | body | 否 | API端点列表，每个端点可配置独立的进程数等参数 |

#### 8.4.3 请求示例

```json
{
  "name": "更新API名称",
  "maxTimeout": 60
}
```

#### 8.4.4 响应示例

```json
{
  "code": 0,
  "message": "API配置更新成功"
}
```

### 8.5 删除API配置
#### 8.5.1 接口信息

- **URL**: `/api/v1/apis/:id`
- **方法**: `DELETE`
- **功能**: 删除API配置（逻辑删除）

#### 8.5.2 约束说明
- **引用检查**: 若有正在运行的任务引用此 API，将返回 400 错误，提示先将任务停止。

#### 8.5.3 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| id | INTEGER | path | 是 | API ID |

#### 8.5.4 响应示例

```json
{
  "code": 0,
  "message": "API配置已删除"
}
```

### 8.6 测试API连接
#### 8.6.1 接口信息

- **URL**: `/api/v1/apis/:id/test-connection`
- **方法**: `POST`
- **功能**: 测试API连接状态并更新健康得分

#### 8.6.2 实现逻辑
1. 发起探测请求（GET），记录响应时间和状态码。
2. 根据探测结果自动更新 API 的 `status` (online/offline) 和 `health_score`。
3. 会写入健康检查日志。

#### 8.6.3 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| id | INTEGER | path | 是 | API ID |

#### 8.6.4 响应示例

```json
{
  "code": 0,
  "message": "连接测试完成",
  "data": {
    "id": 1,
    "status": "online",
    "health_score": 95,
    "api_url_status": "true",
    "endpoints_status": "true",
    "status_code": 200,
    "response_time": "120.50ms",
    "error": null,
    "warning": null
  }
}
```

### 8.7 健康检查（兼容接口）
#### 8.7.1 接口信息

- **URL**: `/api/v1/apis/:id/health-check`
- **方法**: `POST`
- **功能**: 对API进行健康检查，测试连接状态并更新健康得分（与测试连接接口功能相同，兼容旧版本）

#### 8.7.2 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| id | INTEGER | path | 是 | API ID |

#### 8.7.3 响应示例

```json
{
  "code": 0,
  "message": "连接测试完成",
  "data": {
    "id": 1,
    "status": "online",
    "statusCode": 200,
    "responseTime": "120.50ms",
    "healthScore": 95
  }
}
```

### 8.8 停止测试
#### 8.8.1 接口信息

- **URL**: `/api/v1/apis/:id/stop-test`
- **方法**: `POST`
- **功能**: 停止正在进行的API测试

#### 8.8.2 请求参数

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| id | INTEGER | path | 是 | API ID |

#### 8.8.3 响应示例

```json
{
  "code": 0,
  "message": "测试已停止",
  "data": {
    "id": 1,
    "status": "online"
  }
}
```
