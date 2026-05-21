# 代码量与API数量统计文档

## 1. 项目概述

本项目是一个**语音测试自动化系统**，采用前后端分离架构：
- **后端**：Python Flask + PostgreSql
- **前端**：Vue.js 3 + TypeScript + Vite
- **桌面端**：Electron

---

## 2. 代码量统计

### 2.1 后端代码量 (Python)

| 模块 | 文件数 | 代码行数 | 主要功能 |
|------|--------|----------|----------|
| blueprints | 13 | ~3,000 | API路由定义 |
| controllers | 21 | ~8,000 | 业务逻辑控制器 |
| models | 3 | ~2,500 | 数据模型 |
| schemas | 16 | ~4,000 | 请求/响应schema |
| utils | 27 | ~8,500 | 工具类 |
| device_driver | 9 | ~4,500 | 设备驱动 |
| algorithm | 6 | ~3,000 | 算法配置 |
| migrations | 15 | ~2,000 | 数据库迁移脚本 |
| scripts | 24 | ~2,000 | 运维脚本 |
| tests | 8 | ~800 | 单元测试 |
| config | 2 | ~500 | 配置文件 |
| **总计** | **150** | **~38,354** | |

### 2.2 前端代码量 (Vue/JS/TS)

| 类型 | 文件数 | 代码行数 | 主要功能 |
|------|--------|----------|----------|
| Vue组件 | ~100 | ~45,000 | 页面和UI组件 |
| TypeScript/JS | ~42 | ~20,000 | 业务逻辑和工具函数 |
| **总计** | **142** | **~65,000** | |

---

## 3. API数量统计

### 3.1 后端API路由汇总

| Blueprint | 模块名称 | API数量 |
|-----------|----------|---------|
| audio_bp | 音频管理 | 24 |
| algorithm_bp | 算法配置 | 46 |
| api_bp | API管理 | 8 |
| device_bp | 设备管理 | 12 |
| evaluation_bp | 评估维度 | 18 |
| execution_bp | 用例执行 | 2 |
| group_bp | 用例分组 | 5 |
| log_bp | 日志管理 | 6 |
| playback_bp | 播放设备 | 10 |
| report_bp | 报告管理 | 14 |
| spl_bp | 声压级映射 | 11 |
| sse_bp | SSE推送 | 1 |
| task_bp | 任务管理 | 14 |
| testcase_bp | 测试用例 | 16 |
| **总计** | | **177** |

### 3.2 API详细分类

#### 音频管理 API (24个)
- `GET/POST /audios` - 获取/创建音频
- `GET /audios/ids` - 获取音频ID列表
- `GET /audios/<id>` - 获取单个音频
- `GET /audios/directions` - 获取方向列表
- `GET /audios/tags` - 获取标签列表
- `POST /audios/upload` - 上传音频
- `POST /audios/url-import` - URL导入
- `POST /audios/record` - 录音
- `POST /audios/<id>/convert` - 转换音频
- `PUT /audios/<id>/metadata` - 更新元数据
- `POST /audios/batch-action` - 批量操作
- `GET /audios/<id>/stream` - 流式播放
- `POST /audios/<id>/preview` - 预览
- `POST /audios/<id>/stop-preview` - 停止预览
- `GET /audios/stream-by-path` - 按路径流播放
- `POST /audios/folder-import` - 文件夹导入
- `DELETE /audios/<id>` - 删除音频
- `POST /audios/upload/init` - 分片上传初始化
- `POST /audios/upload/register` - 注册上传文件
- `POST /audios/upload/chunk` - 上传分片
- `POST /audios/upload/merge` - 合并分片
- `GET /audios/upload/progress` - 获取上传进度

#### 算法配置 API (46个)
- `GET /algorithm/definitions` - 获取算法定义列表
- `GET /algorithm/definitions/<type>` - 获取单个算法定义
- `POST /algorithm/definitions` - 创建算法定义
- `PUT /algorithm/definitions/<type>` - 更新算法定义
- `DELETE /algorithm/definitions/<type>` - 删除算法定义
- `GET /algorithm/groups` - 获取算法分组
- `GET /algorithm/groups/<id>` - 获取单个分组
- `POST /algorithm/groups` - 创建分组
- `PUT /algorithm/groups/<id>` - 更新分组
- `DELETE /algorithm/groups/<id>` - 删除分组
- `GET /algorithm/params` - 获取参数列表
- `GET /algorithm/params/<id>` - 获取单个参数
- `POST /algorithm/params` - 创建参数
- `PUT /algorithm/params/<id>` - 更新参数
- `DELETE /algorithm/params/<id>` - 删除参数
- `GET /algorithm/case-params` - 获取用例参数
- `POST /algorithm/case-params` - 创建用例参数
- `PUT /algorithm/case-params/<id>` - 更新用例参数
- `DELETE /algorithm/case-params/<id>` - 删除用例参数
- `GET /algorithm/reference-params` - 获取参考参数
- `POST /algorithm/reference-params` - 创建参考参数
- `PUT /algorithm/reference-params/<id>` - 更新参考参数
- `DELETE /algorithm/reference-params/<id>` - 删除参考参数
- `GET /algorithm/mappings` - 获取映射列表
- `POST /algorithm/mappings` - 创建映射
- `PUT /algorithm/mappings/<id>` - 更新映射
- `DELETE /algorithm/mappings/<id>` - 删除映射
- `GET /algorithm/options` - 获取算法选项
- `GET /algorithm/options-sources` - 获取选项来源
- `GET /algorithm/params/<type>/options` - 获取参数选项
- `GET /algorithm/form-schema/<type>` - 获取表单Schema
- `GET /algorithm/dimensions/<type>` - 获取维度
- `POST /algorithm/dimensions/<type>` - 关联维度
- `POST /algorithm/dimension-relations` - 创建维度关系
- `PUT /algorithm/dimension-relations/<id>` - 更新维度关系
- `DELETE /algorithm/dimension-relations/<id>` - 删除维度关系
- `POST /algorithm/reload` - 重新加载配置
- `POST /algorithm/import` - 导入算法
- `POST /algorithm/bulk-delete` - 批量删除
- `POST /algorithm/extract-params` - 提取参数
- `GET /algorithm/dimension-params/<id>` - 获取维度参数

#### API管理 API (8个)
- `GET /apis` - 获取API列表
- `GET /apis/<id>` - 获取单个API
- `POST /apis` - 创建API
- `PUT /apis/<id>` - 更新API
- `DELETE /apis/<id>` - 删除API
- `POST /apis/<id>/health` - 健康检查
- `POST/GET /apis/<id>/test` - 测试连接
- `POST /apis/<id>/stop-test` - 停止测试

#### 设备管理 API (12个)
- `GET /devices` - 获取设备列表
- `GET /devices/status` - 获取设备状态
- `GET /devices/<id>` - 获取单个设备
- `POST /devices` - 创建设备
- `PUT /devices/<id>` - 更新设备
- `DELETE /devices/<id>` - 删除设备
- `POST /devices/health-check` - 健康检查
- `POST /devices/scan` - 扫描设备
- `POST /devices/<id>/test` - 测试设备
- `POST /devices/<id>/stop-test` - 停止测试
- `GET /devices/driver-keywords` - 获取驱动关键字
- `GET /devices/serials` - 获取设备序列号

#### 评估维度 API (18个)
- `POST /evaluation/task/reevaluate` - 重新评估任务
- `GET /evaluation/dimensions/options` - 获取维度选项
- `GET /evaluation/dimensions` - 获取维度列表
- `POST /evaluation/dimensions` - 创建维度
- `PUT /evaluation/dimensions/<id>` - 更新维度
- `DELETE /evaluation/dimensions/<id>` - 删除维度
- `GET/POST /evaluation/dimensions/<id>/health` - 维度健康检查
- `POST /evaluation/dimensions/<id>/calculate` - 计算分数
- `POST /evaluation/dimensions/batch` - 批量操作
- `GET /evaluation/dimensions/export` - 导出维度
- `POST /evaluation/dimensions/import` - 导入维度
- `GET /evaluation/categories` - 获取分类
- `POST /evaluation/categories` - 创建分类
- `PUT /evaluation/categories/<id>` - 更新分类
- `DELETE /evaluation/categories/<id>` - 删除分类

#### 任务管理 API (14个)
- `GET /tasks` - 获取任务列表
- `GET /tasks/<id>` - 获取单个任务
- `GET /tasks/<id>/cases/<case_id>/detail` - 获取用例详情
- `GET /tasks/<id>/progress` - 获取任务进度
- `POST /tasks` - 创建任务
- `POST /tasks/<id>/start` - 启动任务
- `POST /tasks/<id>/retry` - 重试任务
- `POST /tasks/<id>/control` - 控制任务
- `PATCH /tasks/<id>/cases` - 更新用例
- `GET /tasks/<id>/stats` - 获取统计
- `POST /tasks/batch-action` - 批量操作
- `POST /tasks/merge` - 合并任务
- `POST /tasks/<id>/stop` - 停止任务
- `DELETE /tasks/<id>` - 删除任务

#### 测试用例 API (16个)
- `GET /testcases` - 获取用例列表
- `GET /testcases/<id>` - 获取单个用例
- `POST /testcases` - 创建用例
- `PUT /testcases/<id>` - 更新用例
- `DELETE /testcases/<id>` - 删除用例
- `POST /testcases/<id>/copy` - 复制用例
- `POST /testcases/<id>/preview` - 预览用例
- `POST /testcases/<id>/stop_preview` - 停止预览
- `POST /testcases/<id>/stop-preview` - 停止预览(别名)
- `POST /testcases/batch` - 批量操作
- `GET /testcases/stats` - 获取统计
- `GET /testcases/tags` - 获取标签
- `POST /testcases/export` - 导出用例
- `POST /testcases/import` - 导入用例
- `GET /testcases/template/download` - 下载模板
- `POST /testcases/import/preview` - 导入预览

#### 报告管理 API (14个)
- `GET /reports` - 获取报告列表
- `GET /reports/<id>` - 获取单个报告
- `DELETE /reports/<id>` - 删除报告
- `PUT /reports/<id>` - 更新报告
- `POST /reports/<id>/publish` - 发布报告
- `POST /reports/batch-delete` - 批量删除
- `GET /reports/<id>/progress` - 获取进度
- `POST /reports/compare` - 对比报告
- `POST /reports/secondary-compare` - 二次对比
- `POST /reports/generate-task` - 生成任务报告
- `POST /reports/export` - 导出报告
- `GET /reports/trend` - 趋势数据
- `POST /reports/case-averages` - 用例平均分
- `GET /reports/<id>/cases` - 获取报告用例
- `POST /reports/<id>/cases/search` - 搜索报告用例

#### 用例执行 API (2个)
- `POST /execution/<task_id>/start` - 启动执行
- `POST /execution/<task_id>/control` - 控制执行

#### 用例分组 API (5个)
- `GET /groups` - 获取分组列表
- `POST /groups` - 创建分组
- `PUT /groups/<id>` - 更新分组
- `DELETE /groups/<id>` - 删除分组
- `POST /groups/move-cases` - 移动用例

#### 日志管理 API (6个)
- `GET /logs` - 获取日志
- `GET /logs/stats` - 获取统计
- `PUT /logs/mark` - 标记日志
- `GET/POST /logs/export` - 导出日志
- `POST /logs/refresh` - 刷新日志
- `POST /logs/clear` - 清除日志

#### 播放设备 API (10个)
- `GET /playback-devices` - 获取播放设备
- `GET /playback-devices/<id>` - 获取单个设备
- `POST /playback-devices` - 创建设备
- `PUT /playback-devices/<id>` - 更新设备
- `DELETE /playback-devices/<id>` - 删除设备
- `POST /playback-devices/scan` - 扫描设备
- `POST /playback-devices/<id>/associate-spl` - 关联SPL
- `POST /playback-devices/<id>/test` - 测试设备
- `POST /playback-devices/<id>/stop-test` - 停止测试
- `GET /playback-devices/check-status` - 检查状态

#### 声压级映射 API (11个)
- `GET /spl` - 获取映射列表
- `GET /spl/<id>` - 获取单个映射
- `POST /spl` - 创建映射
- `PUT /spl/<id>` - 更新映射
- `DELETE /spl/<id>` - 删除映射
- `POST /spl/<id>/calibrate` - 校准
- `GET /spl/<id>/history` - 获取校准历史
- `GET /spl/<id>/calibration-data` - 获取校准数据
- `GET /spl/stats` - 获取统计
- `GET /spl/by-device/<id>` - 按设备获取
- `POST /spl/test-tone` - 播放测试音
- `POST /spl/test-tone/stop` - 停止测试音

#### SSE推送 API (1个)
- `GET /sse` - Server-Sent Events推送端点

---

## 4. 统计汇总

| 指标 | 数量 |
|------|------|
| 后端Python文件数 | 150 |
| 后端Python代码行数 | 38,354 |
| 前端Vue/JS/TS文件数 | 142 |
| 前端代码行数 | 65,073 |
| **总代码行数** | **103,427** |
| 后端API路由总数 | 177 |
| Blueprint模块数 | 14 |

---

*文档生成时间：2026-03-28*
