# SPLMapping接口文档

## 1. 映射管理API

### 1.1 获取所有映射配置

- **API路径**：`/api/v1/spl`
- **方法**：GET
- **请求参数**：
  | 参数名 | 类型 | 必填 | 说明 |
  |--------|------|------|------|
  | keyword | string | 否 | 搜索关键词 |
  | calibrationStatus | string | 否 | 校准状态过滤 (calibrated/uncalibrated) |
  | page | integer | 否 | 页码，默认1 |
  | perPage | integer | 否 | 每页数量，默认10 |
- **响应示例**：
  ```json
  {
    "code": 200,
    "data": {
      "items": [
        {
          "id": 1,
          "name": "智能音箱A增益映射",
          "description": "智能音箱A的增益映射配置",
          "deviceId": 1,
          "deviceName": "测试播放设备A",
          "deviceType": "smart_speaker",
          "distance": 1.0,
          "targetSpl": 85.0,
          "digitalGain": 50.0,
          "calibrationStatus": "calibrated",
          "testFrequency": 1000,
          "calibrationData": {
            "points": [
              {"gain": 1, "spl": 65.5},
              {"gain": 50, "spl": 85.2},
              {"gain": 100, "spl": 95.8}
            ]
          },
          "createdAt": "2024-01-01T12:00:00",
          "updatedAt": "2024-01-01T13:00:00"
        }
      ],
      "total": 1,
      "page": 1,
      "perPage": 10,
      "pages": 1
    },
    "message": "success"
  }
  ```

### 1.2 创建新映射配置

- **API路径**：`/api/v1/spl`
- **方法**：POST
- **请求体**：
  | 参数名 | 类型 | 必填 | 说明 |
  |--------|------|------|------|
  | name | string | 是 | 映射名称 |
  | description | string | 否 | 描述 |
  | deviceId / device_id | integer | 否 | 关联设备ID |
  | deviceType / device_type | string | 否 | 设备类型 |
  | distance | number | 否 | 测量距离，默认1.0 |
  | targetSpl / target_spl | number | 否 | 目标声压级 |
  | digitalGain / digital_gain | number | 否 | 数字增益 |
  | testFrequency / test_frequency | integer | 否 | 测试频率，默认1000 |
- **响应示例**：
  ```json
  {
    "code": 200,
    "data": {
      "id": 2
    },
    "message": "SPL 映射记录创建成功"
  }
  ```

### 1.3 获取映射详情

- **API路径**：`/api/v1/spl/{mapping_id}`
- **方法**：GET
- **响应示例**：
  ```json
  {
    "code": 200,
    "data": {
      "id": 1,
      "name": "智能音箱A增益映射",
      "description": "智能音箱A的增益映射配置",
      "device": {
        "id": 1,
        "name": "测试播放设备A"
      },
      "deviceType": "smart_speaker",
      "distance": 1.0,
      "targetSpl": 85.0,
      "digitalGain": 50.0,
      "calibrationStatus": "calibrated",
      "testFrequency": 1000,
      "calibrationData": {
        "points": [
          {"gain": 1, "spl": 65.5},
          {"gain": 50, "spl": 85.2},
          {"gain": 100, "spl": 95.8}
        ]
      },
      "createdAt": "2024-01-01T12:00:00",
      "updatedAt": "2024-01-01T13:00:00"
    },
    "message": "success"
  }
  ```

### 1.4 更新映射配置

- **API路径**：`/api/v1/spl/{mapping_id}`
- **方法**：PUT
- **约束说明**：若修改了 `distance` 或 `testFrequency`，由于物理环境参数变更，系统将自动将 `calibration_status` 重置为 `uncalibrated`，并清空历史校准值。
- **请求体**：
  | 参数名 | 类型 | 必填 | 说明 |
  |--------|------|------|------|
  | name | string | 否 | 映射名称 |
  | description | string | 否 | 描述 |
  | deviceId / device_id | integer | 否 | 关联设备ID |
  | deviceType / device_type | string | 否 | 设备类型 |
  | distance | number | 否 | 测量距离 |
  | targetSpl / target_spl | number | 否 | 目标声压级 |
  | digitalGain / digital_gain | number | 否 | 数字增益 |
  | testFrequency / test_frequency | integer | 否 | 测试频率 |
- **响应示例**：
  ```json
  {
    "code": 200,
    "message": "SPL 映射记录更新成功"
  }
  ```

### 1.5 删除映射配置

- **API路径**：`/api/v1/spl/{mapping_id}`
- **方法**：DELETE
- **响应示例**：
  ```json
  {
    "code": 200,
    "message": "SPL 映射记录已删除"
  }
  ```

## 2. 校准管理与核心逻辑

### 2.1 执行校准
- **功能**: 执行自动扫描流程，控制硬件在不同增益下播放并记录声压级。
- **API路径**：`/api/v1/spl/{mapping_id}/calibrate`
- **方法**：POST
- **响应示例**：
  ```json
  {
    "code": 200,
    "data": {
      "id": 1,
      "status": "calibrated"
    },
    "message": "校准成功"
  }
  ```

### 2.2 核心算法说明
- **增益转换**: 在任务执行时，引擎根据校准数据（单点 digital_gain 或多点 calibration_data）计算目标输出增益。
- **计算逻辑**: 优先使用多点校准数据的线性插值；若只有单点数据，则基于 target_spl 和 digital_gain 进行参考计算。
- **距离属性**: 每个映射记录对应特定的播放距离（distance），用于区分不同环境下的校准。

### 2.3 获取校准历史

- **API路径**：`/api/v1/spl/{mapping_id}/history`
- **方法**：GET
- **响应示例**：
  ```json
  {
    "code": 200,
    "data": {
      "items": [
        {
          "id": 1,
          "calibrationData": {
            "points": [
              {"gain": 1, "spl": 65.5},
              {"gain": 50, "spl": 85.2},
              {"gain": 100, "spl": 95.8}
            ]
          },
          "distance": 1.0,
          "testFrequency": 1000,
          "createdAt": "2024-01-01T15:00:00"
        }
      ],
      "total": 1
    },
    "message": "success"
  }
  ```

### 2.4 获取校准数据

- **API路径**：`/api/v1/spl/{mapping_id}/calibration-data`
- **方法**：GET
- **响应示例**：
  ```json
  {
    "code": 200,
    "data": {
      "points": [
        {"gain": 1, "spl": 65.5},
        {"gain": 50, "spl": 85.2},
        {"gain": 100, "spl": 95.8}
      ]
    },
    "message": "success"
  }
  ```
