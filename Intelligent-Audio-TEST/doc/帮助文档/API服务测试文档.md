# API服务测试文档

## 1. 概述

API服务是系统中的核心组件，用于管理和测试第三方API配置，支持任务执行过程中的API调用。本文档详细描述API服务的接口要求、测试方法和最佳实践。

## 2. 接口要求

### 2.1 基础信息

- **基础URL**: `http://localhost:5000/api/v1`
- **请求方法**: GET, POST, PUT, DELETE
- **响应格式**: JSON
- **认证方式**: 无需认证（开发环境）
- **Python版本**: 3.12+

### 2.2 统一响应格式

所有API接口返回统一格式：

```json
{
  "code": 0, // 0 表示成功，非0表示失败
  "message": "操作成功", // 响应消息
  "data": {}, // 响应数据，根据接口不同而变化
  "detail": null // 错误详情，仅在失败时返回
}
```

### 2.3 错误码定义

| 错误码 | 描述 | 说明 |
|--------|------|------|
| 0 | 成功 | 操作成功 |
| 1001 | 参数错误 | 请求参数格式不正确或缺少必填参数 |
| 1002 | 资源不存在 | 请求的资源不存在 |
| 1003 | 业务错误 | 业务逻辑处理失败 |
| 1004 | 系统内部错误 | API服务内部出现错误 |
| 1005 | 请求频率过高 | 超过了API的请求频率限制 |
| 1006 | 认证失败 | API认证失败 |
| 2001 | 数据库错误 | 数据库操作失败 |
| 2002 | 文件操作错误 | 文件读写失败 |
| 3001 | 任务执行错误 | 任务执行过程中发生错误 |
| 3002 | 设备错误 | 设备操作失败 |

### 2.3 接口详细说明

#### 2.3.1 获取所有API配置

**URL**: `/apis`
**方法**: GET
**功能**: 获取所有API配置列表，支持分页和筛选

**请求参数**:
| 参数名 | 类型 | 必填 | 描述 | 示例值 |
|--------|------|------|------|--------|
| page | int | 否 | 页码，默认1 | 1 |
| perPage | int | 否 | 每页条数，默认10 | 20 |
| keyword | string | 否 | 搜索关键字，支持名称和描述 | "test" |
| status | string | 否 | 状态筛选 | "online" |

**响应数据**:
```json
{
  "items": [
    {
      "id": 1,
      "name": "测试API",
      "description": "用于测试的API",
      "status": "online",
      "meta": {},
      "defaultMaxProcess": 5,
      "defaultMaxTimeout": 30,
      "defaultMaxAudioDuration": 60,
      "healthScore": 100,
      "endpoints": [
        {
          "id": "1_0",
          "endpoint": "http://example.com/api",
          "name": "主节点",
          "maxProcess": 5,
          "maxTimeout": 30,
          "maxAudioDuration": 60,
          "status": "online",
          "healthScore": 100,
          "priority": 0,
          "description": "主节点描述"
        }
      ],
      "createdAt": "2026-01-09T10:00:00.000Z",
      "updatedAt": "2026-01-09T10:00:00.000Z"
    }
  ],
  "total": 1,
  "page": 1,
  "perPage": 20,
  "pages": 1
}
```

#### 2.3.2 获取单个API配置

**URL**: `/apis/{api_id}`
**方法**: GET
**功能**: 获取单个API配置的详细信息

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| api_id | int | 是 | API配置ID |

**响应数据**:
```json
{
  "id": 1,
  "name": "测试API",
  "description": "用于测试的API",
  "status": "online",
  "meta": {},
  "defaultMaxProcess": 5,
  "defaultMaxTimeout": 30,
  "defaultMaxAudioDuration": 60,
  "healthScore": 100,
  "endpoints": [
    {
      "id": "1_0",
      "endpoint": "http://example.com/api",
      "name": "主节点",
      "maxProcess": 5,
      "maxTimeout": 30,
      "maxAudioDuration": 60,
      "status": "online",
      "healthScore": 100,
      "priority": 0,
      "description": "主节点描述"
    }
  ],
  "createdAt": "2026-01-09T10:00:00.000Z",
  "updatedAt": "2026-01-09T10:00:00.000Z"
}
```

#### 2.3.3 创建API配置

**URL**: `/apis`
**方法**: POST
**功能**: 创建新的API配置

**请求体**:
```json
{
  "name": "新API",
  "description": "新创建的API",
  "status": "online",
  "meta": {
    "version": "v1",
    "type": "rest"
  },
  "defaultMaxProcess": 5,
  "defaultMaxTimeout": 30,
  "defaultMaxAudioDuration": 60,
  "endpoints": [
    {
      "endpoint": "http://example.com/api/v1",
      "name": "主节点",
      "maxProcess": 5,
      "maxTimeout": 30,
      "maxAudioDuration": 60,
      "priority": 0,
      "description": "主节点描述"
    }
  ]
}
```

**参数验证规则**:
- `name` 和 `meta` 为必填字段
- `defaultMaxProcess`: 1-100之间的整数
- `defaultMaxTimeout`: 1-300之间的整数
- `defaultMaxAudioDuration`: 1-3600之间的整数
- `endpoints`: 至少包含一个端点，每个端点的 `endpoint` 为必填，`name` 为选填
- `endpoint`: 必须是有效的URL，支持http, https, ws, wss协议

**响应数据**:
```json
{
  "id": 2
}
```

#### 2.3.4 更新API配置

**URL**: `/apis/{api_id}`
**方法**: PUT
**功能**: 更新指定API配置的信息

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| api_id | int | 是 | API配置ID |

**请求体**:
```json
{
  "name": "更新后的API",
  "description": "更新后的描述",
  "status": "online",
  "meta": {
    "version": "v1",
    "type": "rest"
  },
  "defaultMaxProcess": 10,
  "defaultMaxTimeout": 60,
  "defaultMaxAudioDuration": 120,
  "endpoints": [
    {
      "endpoint": "http://example.com/api/v1",
      "name": "主节点 (可选)",
      "maxProcess": 10,
      "maxTimeout": 60,
      "maxAudioDuration": 120,
      "priority": 0,
      "description": "更新后的主节点描述"
    }
  ]
}
```

**参数验证规则**: 同创建API配置

**响应数据**:
```json
null
```

#### 2.3.5 删除API配置

**URL**: `/apis/{api_id}`
**方法**: DELETE
**功能**: 删除指定的API配置（逻辑删除）

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| api_id | int | 是 | API配置ID |

**响应数据**:
```json
null
```

**注意事项**:
- 如果该API配置正在被运行中的任务使用，将返回错误
- 删除后该API配置将不再显示在列表中

#### 2.3.6 测试API连接

**URL**: `/apis/{api_id}/test`
**方法**: POST | GET
**功能**: 测试API连接状态，检查API是否可用

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| api_id | int | 是 | API配置ID |

**响应数据**:
```json
{
  "id": 1,
  "status": "online",
  "error": null, // 错误信息，仅在测试失败时返回
  "healthScore": 100
}
```

#### 2.3.7 健康检查

**URL**: `/apis/{api_id}/health`
**方法**: POST
**功能**: 检查API健康状态（与test接口功能相同，为兼容旧版本）

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| api_id | int | 是 | API配置ID |

**响应数据**:
```json
{
  "id": 1,
  "status": "online",
  "error": null,
  "healthScore": 100
}
```

#### 2.3.8 停止测试

**URL**: `/apis/{api_id}/stop-test`
**方法**: POST
**功能**: 停止正在进行的API测试

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| api_id | int | 是 | API配置ID |

**响应数据**:
```json
{
  "id": 1,
  "status": "online"
}
```

## 3. 测试要求

### 3.1 测试环境

- **操作系统**: Windows 10/11 或 Linux
- **Python版本**: 3.13+
- **依赖库**: Flask, Requests 等（详见requirements.txt）
- **数据库**: SQLite

### 3.2 测试用例设计

#### 3.2.1 功能测试

| 测试场景 | 预期结果 |
|----------|----------|
| 获取API列表 | 返回正确的API列表，支持分页和筛选 |
| 创建API配置 | 成功创建API配置，返回正确的ID |
| 更新API配置 | 成功更新API配置，返回正确结果 |
| 删除API配置 | 成功删除API配置，不再显示在列表中 |
| 测试API连接 | 成功测试API连接状态，返回正确的健康分数 |
| 健康检查 | 成功检查API健康状态，返回正确结果 |

#### 3.2.2 边界测试

| 测试场景 | 预期结果 |
|----------|----------|
| 创建API时缺少必填字段 | 返回错误信息，提示缺少必填字段 |
| 使用无效URL创建API | 返回错误信息，提示URL格式无效 |
| 设置超出范围的并发数 | 返回错误信息，提示参数超出范围 |
| 删除正在使用的API | 返回错误信息，提示该API正在被使用 |

#### 3.2.3 性能测试

| 测试场景 | 预期结果 |
|----------|----------|
| 同时创建10个API配置 | 所有API配置都能成功创建 |
| 同时测试5个API连接 | 所有测试都能在超时时间内完成 |
| 获取大量API配置（100+） | 响应时间不超过2秒 |

### 3.3 测试执行

#### 3.3.1 手动测试

1. 使用Postman或类似工具发送请求
2. 检查响应状态码和响应内容
3. 验证数据是否正确写入数据库
4. 检查日志记录

#### 3.3.2 自动化测试

使用Python编写自动化测试脚本，示例代码：

```python
import requests
import json

BASE_URL = "http://localhost:5000/api/v1"

def test_get_apis():
    """测试获取API列表"""
    response = requests.get(f"{BASE_URL}/apis")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "items" in data["data"]

if __name__ == "__main__":
    test_get_apis()
    print("All tests passed!")
```

### 3.4 测试报告

测试完成后，生成测试报告，包括：

1. 测试概述
2. 测试环境
3. 测试用例执行结果
4. 问题列表
5. 优化建议

## 4. 最佳实践

### 4.1 API配置管理

1. **合理设置并发数**: 根据API服务的实际承载能力设置最大并发数
2. **配置多个端点**: 为重要API配置多个端点，提高可用性
3. **定期健康检查**: 定期执行健康检查，及时发现不可用的API
4. **详细描述信息**: 为API配置添加详细的描述，便于其他用户理解和使用

### 4.2 性能优化

1. **适当设置超时时间**: 根据API的实际响应时间设置合理的超时时间
2. **优化端点优先级**: 为不同端点设置合理的优先级，实现负载均衡
3. **监控API使用情况**: 监控API的调用频率和响应时间，及时发现性能问题

### 4.3 安全性建议

1. **使用HTTPS**: 生产环境中使用HTTPS协议，确保数据传输安全
2. **添加认证机制**: 生产环境中添加适当的认证机制，防止未授权访问
3. **限制访问IP**: 限制API的访问IP，只允许指定的IP地址访问
4. **定期更新API密钥**: 如果使用API密钥认证，定期更新密钥，提高安全性

## 5. 故障排查

### 5.1 常见问题

| 问题现象 | 可能原因 | 解决方法 |
|----------|----------|----------|
| API连接测试失败 | URL格式错误 | 检查URL格式是否正确 |
| API连接测试失败 | 网络问题 | 检查网络连接是否正常 |
| API连接测试失败 | 服务端问题 | 检查API服务是否正常运行 |
| 创建API失败 | 参数验证失败 | 检查请求参数是否符合要求 |
| 删除API失败 | API正在被使用 | 停止使用该API的任务后再删除 |

### 5.2 日志查看

API服务的日志记录在后端日志文件中，位置：
- 开发环境：`backend/logs/app.log`
- 生产环境：根据配置而定

通过查看日志，可以了解API服务的运行状态和错误信息，便于故障排查。

## 6. 版本历史

| 版本 | 日期 | 描述 |
|------|------|------|
| v1.0 | 2026-01-09 | 初始版本，包含基本的API管理功能 |
| v1.1 | 2026-02-15 | 新增API端点管理功能 |
| v1.2 | 2026-03-20 | 优化健康检查机制，添加健康分数 |

## 7. 联系方式

如有问题或建议，请联系开发团队：
- 邮箱：dev@example.com
- 电话：123-456-7890
- 微信：example_dev

---

**文档更新时间**: 2026-01-09
**文档作者**: 开发团队
**版权所有**: © 2026 测试系统