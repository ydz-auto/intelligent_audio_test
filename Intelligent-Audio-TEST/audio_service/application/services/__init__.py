# -*- coding: utf-8 -*-
"""audio_service 应用服务子包。

存放复杂的应用服务（非 CQRS handler），由 handler 委托调用：
- audio_upload_service: 上传逻辑（分片合并/转码/OSS）
- audio_convert_service: 格式转换
- audio_preview_service: 试听预览
- audio_annotation_service: 标注持久化
- audio_testcase_creation_service: 跨域测试用例创建（编排主类）
  ├─ _creation_round_config_mixin: 轮次配置解析与 config 构建
  ├─ _creation_annotation_mixin: 标注数据注入与用例参数提取
  ├─ _creation_id_resolution_mixin: 文件名/设备名 → ID 解析
  └─ _creation_refresh_mixin: 音频变更后关联用例刷新
- audio_file_utils: 纯函数工具
"""
