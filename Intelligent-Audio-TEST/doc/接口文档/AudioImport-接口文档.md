# 音频资源管理接口文档

## 1. 文档概述

### 1.1 文档目的
本文档描述音频资源管理模块的 API 接口，涵盖音频的上传、导入、编辑、格式转换、预览及批量管理功能。

### 1.2 术语定义
- **Dry Audio**: 核心测试音频（如唤醒词、命令词）。
- **Noise Audio**: 背景噪声音频。
- **SPL (Sound Pressure Level)**: 声压级，用于控制试听时的响度。

## 2. 音频管理 API

### 2.1 获取音频列表
- **URL**: `/api/v1/audios`
- **方法**: `GET`
- **参数**:
  | 参数名 | 类型 | 位置 | 必需 | 描述 |
  |--------|------|------|------|------|
  | page | INTEGER | query | 否 | 页码 (默认 1) |
  | perPage | INTEGER | query | 否 | 每页数量 (默认 10) |
  | per_page | INTEGER | query | 否 | 每页数量 (默认 10) |
  | keyword | STRING | query | 否 | 搜索关键词（文件名、原始文件名） |
  | format | STRING | query | 否 | 格式过滤 (wav, mp3, etc.) |
  | audioType | STRING | query | 否 | 类型过滤 (dry, noise) |
  | audio_type | STRING | query | 否 | 类型过滤 (dry, noise) |

- **响应示例**:
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "items": [
        {
          "id": 1,
          "name": "唤醒词测试",
          "originalFilename": "test.wav",
          "filePath": "/uploads/audios/xxx.wav",
          "duration": 1.5,
          "size": 1024000,
          "sampleRate": 16000,
          "channels": 1,
          "bitrate": 256000,
          "format": "wav",
          "audioType": "dry",
          "asrText": "你好小智",
          "description": "测试唤醒词",
          "createdAt": "2023-01-01T10:00:00",
          "updatedAt": "2023-01-01T10:00:00"
        }
      ],
      "total": 100,
      "page": 1,
      "perPage": 10,
      "pages": 10,
      "stats": {
        "totalFiles": 100,
        "totalSize": "50.25 MB",
        "totalDuration": "125:30",
        "todayUploads": 5
      }
    }
  }
  ```

### 2.2 获取单个音频详情
- **URL**: `/api/v1/audios/:id`
- **方法**: `GET`
- **参数**:
  | 参数名 | 类型 | 位置 | 必需 | 描述 |
  |--------|------|------|------|------|
  | id | INTEGER | path | 是 | 音频ID |

### 2.3 获取翻译语向列表
- **URL**: `/api/v1/audios/directions`
- **方法**: `GET`
- **功能**: 获取所有可用的翻译语向列表

- **响应示例**:
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "items": [
        {
          "id": 1,
          "sourceLanguage": "zh-CN",
          "targetLanguage": "en-US",
          "description": "中文到英文"
        }
      ],
      "total": 1
    }
  }
  ```

### 2.4 音频上传
- **URL**: `/api/v1/audios/upload`
- **方法**: `POST`
- **Content-Type**: `multipart/form-data`
- **功能**: 支持多文件上传，自动提取采样率、时长等元数据。

### 2.5 远程 URL 导入
- **URL**: `/api/v1/audios/url-import`
- **方法**: `POST`
- **Content-Type**: `application/json`
- **请求体**:
  ```json
  {
    "url": "https://example.com/test.wav"
  }
  ```
- **功能**: 下载远程音频文件并导入到系统

### 2.6 在线录制
- **URL**: `/api/v1/audios/record`
- **方法**: `POST`
- **功能**: 接收前端上传的录音数据，保存为音频文件

### 2.7 文件夹批量导入
- **URL**: `/api/v1/audios/folder-import`
- **方法**: `POST`
- **功能**: 递归扫描指定文件夹，导入所有音频文件，并自动根据文件夹路径生成标签

### 2.8 音频格式转换
- **URL**: `/api/v1/audios/:id/convert`
- **方法**: `POST`
- **请求体**:
  ```json
  {
    "format": "wav"
  }
  ```

### 2.9 更新元数据与翻译
- **URL**: `/api/v1/audios/:id/metadata`
- **方法**: `PUT`
- **请求体**:
  ```json
  {
    "name": "新名称",
    "audio_type": "dry",
    "asr_text": "你好小智",
    "description": "描述信息",
    "translations": [
      { "direction_id": 1, "text": "Hello Xiaozhi" }
    ]
  }
  ```

### 2.10 删除音频
- **URL**: `/api/v1/audios/:id`
- **方法**: `DELETE`
- **功能**: 逻辑删除音频文件

### 2.11 预览与试听
#### 2.11.1 流式播放 (浏览器)
- **URL**: `/api/v1/audios/:id/stream`
- **方法**: `GET`
- **功能**: 支持 Range 请求，用于前端播放器试听。

#### 2.11.2 硬件试听 (设备)
- **URL**: `/api/v1/audios/:id/preview`
- **方法**: `POST`
- **请求体**:
  ```json
  {
    "playback_device_id": 1,
    "spl": 65.0
  }
  ```
- **功能**: 控制指定硬件设备以特定声压级播放该音频。

## 5. 分片上传 API

### 5.1 初始化上传任务
- **URL**: `/api/v1/audios/upload/init`
- **方法**: `POST`
- **Content-Type**: `application/json`
- **功能**: 创建一个新的分片上传任务
- **请求体**:
  ```json
  {
    "totalFiles": 2
  }
  ```
- **响应示例**:
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "taskId": "uuid-123456",
      "expiredAt": "2025-12-31T12:00:00Z"
    }
  }
  ```

### 5.2 注册上传文件
- **URL**: `/api/v1/audios/upload/register`
- **方法**: `POST`
- **Content-Type**: `application/json`
- **功能**: 注册要上传的文件信息
- **请求体**:
  ```json
  {
    "taskId": "uuid-123456",
    "files": [
      {
        "name": "test.wav",
        "size": 1024000,
        "md5": "md5-hash-value",
        "chunks": 5
      }
    ]
  }
  ```
- **响应示例**:
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "files": [
        {
          "fileId": "file-uuid-123",
          "name": "test.wav",
          "uploadUrl": "/api/v1/audios/upload/chunk"
        }
      ]
    }
  }
  ```

### 5.3 上传分片
- **URL**: `/api/v1/audios/upload/chunk`
- **方法**: `POST`
- **Content-Type**: `multipart/form-data`
- **功能**: 上传单个文件分片
- **请求参数**:
  | 参数名 | 类型 | 位置 | 必需 | 描述 |
  |--------|------|------|------|------|
  | fileId | STRING | form-data | 是 | 文件ID |
  | chunkIndex | INTEGER | form-data | 是 | 分片索引 |
  | totalChunks | INTEGER | form-data | 是 | 总分片数 |
  | taskId | STRING | form-data | 是 | 任务ID |
  | chunk | FILE | form-data | 是 | 分片文件 |
- **响应示例**:
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "chunkIndex": 0,
      "totalChunks": 5,
      "uploadedSize": 204800,
      "progress": 20
    }
  }
  ```

### 5.4 合并分片
- **URL**: `/api/v1/audios/upload/merge`
- **方法**: `POST`
- **Content-Type**: `application/json`
- **功能**: 合并所有分片，完成文件上传
- **请求体**:
  ```json
  {
    "taskId": "uuid-123456",
    "fileId": "file-uuid-123",
    "createTestCase": false,
    "testType": "api",
    "defaultPlaybackDeviceId": 1,
    "defaultSpl": 65.0,
    "testCaseGroupName": "测试分组"
  }
  ```
- **响应示例**:
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "audioId": 1,
      "fileName": "test.wav",
      "size": 1024000,
      "duration": 10.5
    }
  }
  ```

### 5.5 获取上传进度
- **URL**: `/api/v1/audios/upload/progress`
- **方法**: `GET`
- **功能**: 获取上传任务的进度
- **请求参数**:
  | 参数名 | 类型 | 位置 | 必需 | 描述 |
  |--------|------|------|------|------|
  | taskId | STRING | query | 是 | 任务ID |
- **响应示例**:
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "taskId": "uuid-123456",
      "status": "uploading",
      "totalFiles": 2,
      "completedFiles": 1,
      "totalSize": 2048000,
      "uploadedSize": 1024000,
      "progress": 50
    }
  }
  ```

## 4. 批量操作 API

### 4.1 批量执行
- **URL**: `/api/v1/audios/batch-action`
- **方法**: `POST`
- **请求体**:
  ```json
  {
    "action": "delete | export | tags",
    "audio_ids": [1, 2, 3],
    "tags": ["tag1", "tag2"]
  }
  ```

## 4. 全局错误码

| 错误码 | 描述 |
|--------|------|
| 0 | 成功 |
| 102 | 不支持的音频格式 |
| 103 | 文件读取/写入失败 |
| 204 | 转换引擎异常 |
| 205 | 远程下载失败 |

