# SPLMapping 接口实现文档

## 1. 模块概述
SPLMapping（声压级映射）模块是声学测试的核心组件。它负责建立设备“增益/音量”与实际输出“声压级 (dB SPL)”之间的对应关系。通过校准数据，系统可以在测试时精确控制播放响度。

## 2. 接口详细实现思路

### 1.1 映射配置管理 (CRUD)
**实现思路：**
- **GET /api/v1/spl**: 查询 `spl_mappings` 表，根据 `keyword` 和 `calibrationStatus`/`calibration_status` 过滤。返回字段包含 `name`, `distance`, `target_spl`, `digital_gain` 等，支持分页。
  - 支持驼峰式和下划线式参数格式
  - 按 `created_at` 降序排序
- **POST /api/v1/spl**: 创建映射记录。
  - 必须提供 `deviceId`/`device_id` 或 `deviceType`/`device_type` 之一
  - 支持直接传入 `calibrationData`，自动验证格式并设置校准状态
  - 若校准数据包含有效的 `points`，自动设置 `calibration_status` 为 `calibrated`
  - 支持从校准数据的第一个点自动提取 `target_spl` 和 `digital_gain`
- **PUT /api/v1/spl/:id**: 修改元数据（名称、距离、测试频率等）。
  - 支持驼峰式和下划线式参数格式
  - **关键逻辑**：若修改了 `distance` 或 `test_frequency`，由于物理环境参数变更，自动将 `calibration_status` 重置为 `uncalibrated`，并清空历史校准数据
  - 支持直接更新校准数据，自动验证格式并更新校准状态
- **DELETE /api/v1/spl/:id**: 删除映射配置。

### 2.1 执行校准 (POST /api/v1/spl/:id/calibrate)
**实现思路：**
1. **资源验证**：
   - 根据路径参数 `id` 查找映射记录，确保其存在
2. **自动扫描流程**：
   - 遍历关键测试点：增益 1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100
   - **模拟测量**：
     - 模拟在不同增益下的 SPL 测量值，基于线性增长模型
     - 模拟测量耗时
   - 记录所有 (Gain, SPL) 对
3. **数据处理与更新**：
   - 更新 `spl_mappings` 表：
     - 设置 `calibration_data = {"points": scan_points}`
     - 设置 `calibration_status = 'calibrated'`
     - 更新 `updated_at` 时间
   - 记录历史：在 `calibration_history` 表中插入新记录，保存当前的 `calibration_data`, `distance`, `test_frequency`
4. **事务处理**：使用数据库事务确保主记录更新和历史记录插入的原子性
5. **响应**：返回映射 ID 和校准状态

### 2.2 获取校准历史与数据
**实现思路：**
- **GET /api/v1/spl/:id/history**: 查询 `calibration_history` 表，按 `created_at` 降序排列，返回校准历史记录列表。
- **GET /api/v1/spl/:id/calibration-data**: 从 `spl_mappings` 表中提取 `calibration_data` 字段，用于前端绘制映射曲线图。

## 3. 核心算法逻辑
- **SPL-to-Gain 转换**：
  - **优先插值**：若存在多点 `calibration_data`，使用线性插值计算 `Target_SPL` 对应的 `Gain`。
  - **单点参考**：若无多点数据，基于记录的 `target_spl` 和 `digital_gain` 进行参考计算（假设 6dB 翻倍规律）。
- **距离属性**：每个映射记录绑定特定的播放距离（distance），确保在不同距离配置下的声压级控制准确。不再使用通用的反平方定律动态修正，而是建议为不同距离创建独立的映射记录。
