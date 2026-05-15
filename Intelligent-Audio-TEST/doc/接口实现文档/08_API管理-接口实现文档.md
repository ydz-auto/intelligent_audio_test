# API配置管理接口实现文档

## 1. 模块概述
API配置管理模块负责管理外部语音服务（如 ASR, TTS, NLP）的接入参数。它维护了端到端测试或 API 测试中调用的后端接口信息，并监控其健康状态。该模块支持一个API配置多个链接（endpoints），每个链接可独立配置进程数、超时时间等参数，实现了API集群的灵活管理。

## 2. 接口详细实现思路

### 8.1 获取API列表 (GET /api/v1/apis)
**实现思路：**
1. **参数解析**：提取 `page`, `per_page`, `keyword`, `status`。
2. **构建查询**：针对 `apis` 表，过滤 `deleted == False`。
3. **搜索逻辑**：在 `name`, `description` 上执行模糊匹配。
4. **分页与返回**：执行分页查询，返回 API 配置的基本信息及当前健康得分 (`health_score`)。
5. **关联数据加载**：加载关联的 `api_endpoints` 数据（存储在 JSON 字段中）。
6. **字段处理**：
   - 保持使用蛇形命名（default_max_process, default_max_timeout, default_max_audio_duration, health_score, created_at, updated_at）
   - 为每个 endpoint 生成虚拟 ID（格式：api_id_index）
7. **返回结构**：返回包含 items、total、page、per_page、pages 的分页结构。

### 8.2 获取单个API配置详情 (GET /api/v1/apis/:id)
**实现思路：**
1. **资源查找**：通过 ID 查找 API，确保 `deleted == False`。
2. **关联数据加载**：加载关联的 `api_endpoints` 数据（存储在 JSON 字段中）。
3. **字段处理**：
   - 保持使用蛇形命名
   - 为每个 endpoint 生成虚拟 ID（格式：api_id_index）
4. **返回完整信息**：返回 API 的所有配置信息，包括元数据、健康得分和所有关联的 endpoints 信息。

### 8.3 新增API配置 (POST /api/v1/apis)
**实现思路：**
1. **参数验证**：
   - 验证必需字段 `name` 和 `meta` 是否存在
   - 验证 `meta` 是否为合法的 JSON 对象
   - 校验默认数值字段范围（default_max_process: 1-100, default_max_timeout: 1-300, default_max_audio_duration: 1-3600）
   - 验证 `endpoints` 数组中的每个元素
   - 验证每个 endpoint 的 `endpoint` 是否为合法的 URL
   - 校验每个 endpoint 的数值字段范围

2. **数据持久化**：
   - 创建 API 主记录，设置默认值（状态: online, 健康得分: 100）
   - 若提供了 `endpoints`，则构建 `api_endpoints` JSON 数组
   - endpoint 继承 API 的默认参数（如未指定则使用 API 的 default_max_process 等）
   - 使用事务确保数据一致性

3. **返回结果**：返回新创建的 API ID

### 8.3.1 APIEndpoint 数据结构设计
- **存储方式**: 存储在 `apis` 表的 `api_endpoints` JSON 字段中
- **核心字段**:
  - `endpoint`: API 端点 URL (必填)
  - `name`: 端点名称 (可选)
  - `max_process`: 最大并发进程数
  - `max_timeout`: 最大超时时间（秒）
  - `max_audio_duration`: 最大音频时长（秒）
  - `status`: 端点状态（online/offline）
  - `health_score`: 端点健康得分
  - `priority`: 端点优先级（数值越大优先级越高）
  - `description`: 端点描述
- **虚拟 ID**: 前端展示用的虚拟 ID，格式为 `api_id_index`

### 8.4 更新API配置 (PUT /api/v1/apis/:id)
**实现思路：**
1. **资源查找**：确认 API 存在且未删除。
2. **参数验证**：对更新的字段进行与创建时相同的验证。
3. **属性更新**：更新 API 的基本信息（name, description, meta, default_max_process 等）。
4. **端点管理**：
   - 支持直接更新 endpoints 数组
   - 验证每个 endpoint 的数据
   - 构建新的 api_endpoints JSON 数组
5. **更新时间**：设置 `updated_at` 为当前 UTC 时间。

### 8.5 删除API配置 (DELETE /api/v1/apis/:id)
**实现思路：**
1. **资源查找**：确认 API 存在且未删除。
2. **影响面检查**：检查是否有正在运行的任务引用此 API。如果有，返回 400 错误并提示任务名称。
3. **级联处理**：
   - 逻辑删除 API 主记录（设置 `deleted = True`）
   - 由于配置了 `cascade="all, delete-orphan"`，关联的 endpoints 会被自动删除
4. **更新时间**：设置 `updated_at` 为当前 UTC 时间。

### 8.6 健康检查 (POST /api/v1/apis/:id/health-check)
**实现思路：**
1. **别名接口**：调用 `test_connection` 方法，保持向后兼容。

### 8.7 测试API连接 (POST /api/v1/apis/:id/test-connection)
**实现思路：**
1. **资源查找**：获取指定 API，确保 `deleted == False`。
2. **测试逻辑**：
   - 测试 API 的 `api_url` 和 `api_endpoints` 中的端点
   - 支持 HTTP/HTTPS 和 WebSocket 协议
3. **发起请求**：
   - 使用 `requests` 库发起探测请求（GET）或 `websocket` 库测试 WebSocket 连接。
   - 设置 `timeout` 为配置中的 `default_max_timeout`。
   - 设置 User-Agent 为 "Task-Manager-Health-Checker/1.0"。
4. **指标测量**：
   - 记录请求开始和结束时间，计算响应时间。
   - 获取 HTTP 状态码或 WebSocket 连接状态。
5. **结果分析**：
   - 若主 URL 在线，API 状态设为 `online`
   - 若主 URL 离线，API 状态设为 `offline`
   - 记录每个端点的测试结果
6. **健康度更新**：将测试结果写入日志，并更新 `apis` 表中的 `status`。
7. **日志记录**：调用 `LogController.log_and_emit` 记录健康检查日志，并支持实时推送。
8. **返回结果**：返回详细的健康检查结果，包括每个端点的状态、响应时间等。

### 8.8 停止测试 (POST /api/v1/apis/:id/stop-test)
**实现思路：**
1. **资源查找**：确认 API 存在且未删除。
2. **状态重置**：将 API 状态设为 `online`。
3. **端点处理**：
   - 该接口主要重置 API 主状态
   - 若需要重置特定 endpoint 状态，应使用专门的 endpoint 接口
4. **返回结果**：返回 API ID 和当前状态。
