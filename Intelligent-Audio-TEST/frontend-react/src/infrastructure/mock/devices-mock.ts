/**
 * 设备管理页 mock 常量（infrastructure 层；红线④：数据一律 mock，不接真实后端）。
 * DTO 形态对照 api_gateway/schemas 实测（见 dto/ 各文件注释），经 adapters/ 转出
 * domain 模型——后续接线仅替换 infrastructure/api 桩实现，页面与 hook 不返工。
 * 数字口径与任务域/测试执行域 mock 保持同一世界观（任务 1042、设备 音箱-客厅位等同源）。
 * INT-487 待后端字段（lab_id/occupied）mock 先行，字段落地后接线不返工。
 */
import type { TestDeviceItemDto } from '@/infrastructure/dto/test-device.dto'
import type { PlaybackDeviceItemDto } from '@/infrastructure/dto/playback-device.dto'
import type { ApiItemDto } from '@/infrastructure/dto/apis.dto'
import type { LaboratoryDto } from '@/infrastructure/dto/laboratory.dto'
import type {
  AlarmDto,
  AlarmRuleDto,
  DeviceStatusHistoryDto,
} from '@/infrastructure/dto/alarm.dto'
import type { DeviceGroup } from '@/domain/models/deviceGroup'
import { testDeviceFromDto } from '@/infrastructure/adapters/testDeviceAdapter'
import { playbackDeviceFromDto } from '@/infrastructure/adapters/playbackDeviceAdapter'
import { apiDeviceFromDto } from '@/infrastructure/adapters/apiDeviceAdapter'
import { laboratoryFromDto } from '@/infrastructure/adapters/laboratoryAdapter'
import {
  alarmFromDto,
  alarmRuleFromDto,
  statusEventFromDto,
} from '@/infrastructure/adapters/alarmAdapter'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type { Laboratory } from '@/domain/models/laboratory'
import type { Alarm, AlarmRule, DeviceStatusEvent } from '@/domain/models/alarm'

/* ==================== 实验室（§6.26；INT-487 后端待立项，mock 先行） ==================== */

export const MOCK_LABORATORIES_DTO: LaboratoryDto[] = [
  {
    id: 1, code: 'LAB-A', name: '声学实验室 A', building: '研发中心东区', floor: '3 层',
    room_number: 'A301', description: '标准声学测试间，含消声室与远场 12 米位。', status: 'active',
    device_count: 5, playback_device_count: 2, test_case_count: 36,
    created_at: '2026-09-01T09:00:00', updated_at: '2026-10-12T10:00:00',
  },
  {
    id: 2, code: 'LAB-B', name: '多设备实验室 B', building: '研发中心东区', floor: '2 层',
    room_number: 'B205', description: '车载/多设备并行测试工位。', status: 'active',
    device_count: 3, playback_device_count: 1, test_case_count: 18,
    created_at: '2026-09-05T09:00:00', updated_at: '2026-10-10T10:00:00',
  },
  {
    id: 3, code: 'LAB-C', name: '噪声实验室 C', building: '研发中心西区', floor: '1 层',
    room_number: 'C101', description: '高噪声环境测试间，维护中。', status: 'maintenance',
    device_count: 1, playback_device_count: 0, test_case_count: 4,
    created_at: '2026-09-12T09:00:00', updated_at: '2026-10-14T10:00:00',
  },
]

export const MOCK_LABORATORIES: Laboratory[] = MOCK_LABORATORIES_DTO.map(laboratoryFromDto)

/* ==================== 测试设备（§3.4：DeviceItem 全字段 + INT-487 lab/occupied） ==================== */

export const MOCK_TEST_DEVICES_DTO: TestDeviceItemDto[] = [
  {
    id: 1, name: '音箱-客厅位', model: '旗舰 S1', description: '客厅远场位，12 米半径',
    type: 'physical', system: 'harmony', system_version: '3.2.1',
    app_name: '音乐播放器', app_version: '2.4.0',
    location: '实验室A·客厅工位', max_audio_duration: 300, needs_prompt_audio: true,
    connection_type: 'usb', keywords: '旗舰, 智能音箱, harmony', serial_number: 'SN-A001-8821',
    ip: '192.168.1.21', status: 'online', last_online_at: '2026-10-17T08:40:00',
    created_at: '2026-09-01T09:00:00', updated_at: '2026-10-17T08:40:00',
    driver_name: 'HDC 驱动 3.1', supported_algorithms: ['asr_streaming', 'wakeword_detect'],
    lab_id: 1, lab_name: '声学实验室 A', occupied: true,
  },
  {
    id: 2, name: '音箱-卧室位', model: '旗舰 S1', description: '卧室近场位',
    type: 'physical', system: 'android', system_version: '12',
    app_name: '音乐播放器', app_version: '2.4.0',
    location: '实验室A·卧室工位', max_audio_duration: 300, needs_prompt_audio: false,
    connection_type: 'usb', keywords: '旗舰, 智能音箱, android', serial_number: 'SN-A001-8832',
    ip: '192.168.1.22', status: 'online', last_online_at: '2026-10-17T08:42:00',
    created_at: '2026-09-01T09:00:00', updated_at: '2026-10-16T20:10:00',
    driver_name: 'ADB 驱动 2.0', supported_algorithms: ['asr_streaming', 'wakeword_detect'],
    lab_id: 1, lab_name: '声学实验室 A', occupied: false,
  },
  {
    id: 3, name: '音箱-入门-03', model: '入门 L2', description: '入门机型，低配算力',
    type: 'physical', system: 'android', system_version: '11',
    app_name: '音乐播放器', app_version: '1.9.0',
    location: null, max_audio_duration: 180, needs_prompt_audio: false,
    connection_type: 'remote', keywords: '入门, 智能音箱', serial_number: 'SN-B002-7715',
    ip: '192.168.1.23', status: 'offline', last_online_at: '2026-10-14T19:10:00',
    created_at: '2026-09-02T10:00:00', updated_at: '2026-10-14T19:10:00',
    driver_name: null, supported_algorithms: ['asr_streaming'],
    lab_id: null, lab_name: null, occupied: false,
  },
  {
    id: 4, name: '音箱-实验室B主控', model: '旗舰 S1 Pro', description: '车载远场验证主控位',
    type: 'physical', system: 'harmony', system_version: '4.0.0',
    app_name: '音乐播放器', app_version: '2.5.0',
    location: '实验室B·车载工位', max_audio_duration: 300, needs_prompt_audio: true,
    connection_type: 'usb', keywords: '旗舰, 车载, harmony', serial_number: 'SN-C004-2201',
    ip: '192.168.2.11', status: 'online', last_online_at: '2026-10-17T08:35:00',
    created_at: '2026-09-03T09:00:00', updated_at: '2026-10-17T08:35:00',
    driver_name: 'HDC 驱动 4.0', supported_algorithms: ['asr_streaming', 'wakeword_detect'],
    lab_id: 2, lab_name: '多设备实验室 B', occupied: false,
  },
  {
    id: 5, name: '手机-小米12', model: 'Xiaomi 12', description: 'Android 近场手机测试位',
    type: 'physical', system: 'android', system_version: '13',
    app_name: '语音助手', app_version: '5.1.0',
    location: '实验室A·手机工位', max_audio_duration: 120, needs_prompt_audio: true,
    connection_type: 'usb', keywords: '手机, android', serial_number: 'SN-D001-3344',
    ip: '192.168.1.31', status: 'connecting', last_online_at: '2026-10-17T08:50:00',
    created_at: '2026-09-04T09:00:00', updated_at: '2026-10-17T08:50:00',
    driver_name: 'ADB 驱动 2.0', supported_algorithms: ['wakeword_detect'],
    lab_id: 1, lab_name: '声学实验室 A', occupied: false,
  },
  {
    id: 6, name: '手机-华为P60', model: 'HUAWEI P60', description: 'HarmonyOS 手机测试位',
    type: 'physical', system: 'harmony', system_version: '4.2.0',
    app_name: '语音助手', app_version: '5.0.1',
    location: null, max_audio_duration: 120, needs_prompt_audio: false,
    connection_type: 'usb', keywords: '手机, harmony', serial_number: 'SN-D002-4477',
    ip: '192.168.1.32', status: 'disconnecting', last_online_at: '2026-10-17T08:20:00',
    created_at: '2026-09-04T09:00:00', updated_at: '2026-10-17T08:20:00',
    driver_name: 'HDC 驱动 3.1', supported_algorithms: ['wakeword_detect'],
    lab_id: null, lab_name: null, occupied: false,
  },
  {
    id: 7, name: '音柱-会议室', model: 'Bar S2', description: '会议室拾音音柱，回声场景',
    type: 'physical', system: 'android', system_version: '12',
    app_name: '会议助手', app_version: '3.2.0',
    location: '实验室B·会议室工位', max_audio_duration: 240, needs_prompt_audio: false,
    connection_type: 'remote', keywords: '音柱, 会议', serial_number: 'SN-E003-9901',
    ip: '192.168.2.21', status: 'online', last_online_at: '2026-10-17T08:30:00',
    created_at: '2026-09-05T09:00:00', updated_at: '2026-10-17T08:30:00',
    driver_name: 'ADB 驱动 2.0', supported_algorithms: ['asr_streaming'],
    lab_id: 2, lab_name: '多设备实验室 B', occupied: true,
  },
  {
    id: 8, name: '设备-异常节点', model: 'Dev Kit D3', description: '调试异常位，模拟错误态',
    type: 'physical', system: 'android', system_version: '10',
    app_name: null, app_version: null,
    location: '实验室B·调试工位', max_audio_duration: 60, needs_prompt_audio: false,
    connection_type: 'usb', keywords: '调试, 异常', serial_number: 'SN-F001-1212',
    ip: '192.168.2.41', status: 'error', last_online_at: '2026-10-16T22:00:00',
    created_at: '2026-09-06T09:00:00', updated_at: '2026-10-17T07:00:00',
    driver_name: null, supported_algorithms: [],
    lab_id: 2, lab_name: '多设备实验室 B', occupied: false,
  },
  {
    id: 9, name: 'ASR HTTP 网关', model: 'HTTP API', description: 'HTTP 协议转写网关',
    type: 'http_api', system: null, system_version: null,
    app_name: null, app_version: null,
    location: '机柜·东区', max_audio_duration: 120, needs_prompt_audio: false,
    connection_type: 'remote', keywords: null, serial_number: null,
    ip: '10.0.8.5', status: 'online', last_online_at: '2026-10-17T08:39:00',
    created_at: '2026-09-01T09:00:00', updated_at: '2026-10-17T08:39:00',
    driver_name: null, supported_algorithms: ['asr_streaming', 'wakeword_detect'],
    lab_id: null, lab_name: null, occupied: false,
  },
]

export const MOCK_TEST_DEVICES: TestDevice[] = MOCK_TEST_DEVICES_DTO.map(testDeviceFromDto)

/* ==================== 播放设备（§3.5：PlaybackDeviceItem + INT-381/487 补口） ==================== */

export const MOCK_PLAYBACK_DEVICES_DTO: PlaybackDeviceItemDto[] = [
  {
    id: 101, name: '参考音源-01', model: 'Audio Gen Pro',
    device_type: 'dry', sample_rate: 48000, channel_index: 0,
    device_unique_id: 'PLAY-REF-0001', description: '标准参考音源，48k 采样',
    status: 'online', current_spl_mapping_id: 1,
    created_at: '2026-09-01T09:00:00', updated_at: '2026-10-16T10:00:00',
    lab_id: 1, lab_name: '声学实验室 A', occupied: false,
    supported_formats: ['WAV', 'FLAC'], supported_channels: 2,
  },
  {
    id: 102, name: '参考音源-02', model: 'Audio Gen Pro',
    device_type: 'dry', sample_rate: 44100, channel_index: 1,
    device_unique_id: 'PLAY-REF-0002', description: '车载工位参考音源',
    status: 'online', current_spl_mapping_id: null,
    created_at: '2026-09-02T09:00:00', updated_at: '2026-10-15T10:00:00',
    lab_id: 2, lab_name: '多设备实验室 B', occupied: false,
    supported_formats: ['WAV', 'MP3', 'FLAC'], supported_channels: 2,
  },
  {
    id: 103, name: '噪声发生-01', model: 'Noise Gen S1',
    device_type: 'noise', sample_rate: 48000, channel_index: 0,
    device_unique_id: 'PLAY-NSE-0001', description: '粉红/白噪声发生设备',
    status: 'online', current_spl_mapping_id: 2,
    created_at: '2026-09-03T09:00:00', updated_at: '2026-10-17T08:00:00',
    lab_id: 1, lab_name: '声学实验室 A', occupied: true,
    supported_formats: ['WAV', 'OGG'], supported_channels: 4,
  },
  {
    id: 104, name: '噪声发生-02', model: 'Noise Gen S1',
    device_type: 'noise', sample_rate: 44100, channel_index: 2,
    device_unique_id: 'PLAY-NSE-0002', description: '高噪声环境发生设备',
    status: 'offline', current_spl_mapping_id: null,
    created_at: '2026-09-04T09:00:00', updated_at: '2026-10-14T10:00:00',
    lab_id: null, lab_name: null, occupied: false,
    supported_formats: ['WAV', 'AAC'], supported_channels: 4,
  },
  {
    id: 105, name: '参考音源-03', model: 'Audio Gen Lite',
    device_type: 'dry', sample_rate: 192000, channel_index: 0,
    device_unique_id: 'PLAY-REF-0003', description: '高采样率参考音源',
    status: 'error', current_spl_mapping_id: 3,
    created_at: '2026-09-05T09:00:00', updated_at: '2026-10-17T06:00:00',
    lab_id: null, lab_name: null, occupied: false,
    supported_formats: ['WAV', 'FLAC'], supported_channels: 2,
  },
]

export const MOCK_PLAYBACK_DEVICES: PlaybackDevice[] = MOCK_PLAYBACK_DEVICES_DTO.map(
  playbackDeviceFromDto
)

/* ==================== 测试 API（§3.6：ApiItem 全字段，API 不挂实验室） ==================== */

export const MOCK_API_DEVICES_DTO: ApiItemDto[] = [
  {
    id: 11, name: 'ASR HTTP API', vendor: '内部 ASR 组',
    api_url: 'https://api.audio.test/v1/asr', description: 'HTTP 流式转写服务',
    status: 'online',
    meta: { protocol: 'https', environment: 'testing', version: '1.4.2' },
    algorithm_type: 'asr_streaming', default_max_process: 32, default_max_timeout: 60,
    default_max_audio_duration: 120, health_score: 92,
    output_types: ['text'], device_type: 'http_api', adapter_class: null, audio_config: null,
    rms_spl_mapping_id: 1,
    created_at: '2026-09-01T10:00:00', updated_at: '2026-10-10T10:00:00',
    endpoints: [
      { id: 'ep-11-1', endpoint: '/v1/asr/stream', name: '流式转写', max_process: 32, max_timeout: 60, max_audio_duration: 120, status: 'online', health_score: 92, priority: 1, description: null },
      { id: 'ep-11-2', endpoint: '/v1/asr/recognize', name: '一句话识别', max_process: 16, max_timeout: 30, max_audio_duration: 60, status: 'online', health_score: 90, priority: 2, description: null },
    ],
  },
  {
    id: 12, name: 'Wakeword HTTP API', vendor: '内部唤醒组',
    api_url: 'https://api.audio.test/v1/wakeword', description: '唤醒词检测服务',
    status: 'offline',
    meta: { protocol: 'https', environment: 'production', version: '2.1.0' },
    algorithm_type: 'asr_streaming', default_max_process: 16, default_max_timeout: 30,
    default_max_audio_duration: 60, health_score: 0,
    output_types: ['text'], device_type: 'http_api', adapter_class: null, audio_config: null,
    rms_spl_mapping_id: null,
    created_at: '2026-09-05T09:00:00', updated_at: '2026-10-08T09:00:00',
    endpoints: [
      { id: 'ep-12-1', endpoint: '/v1/wakeword/detect', name: '唤醒检测', max_process: 16, max_timeout: 30, max_audio_duration: 60, status: 'offline', health_score: null, priority: 1, description: null },
    ],
  },
  {
    id: 13, name: 'TTS HTTP API', vendor: 'TTS 组',
    api_url: 'https://api.audio.test/v1/tts', description: '文本转语音合成服务',
    status: 'online',
    meta: { protocol: 'https', environment: 'testing', version: '3.0.0' },
    algorithm_type: 'tts_eval', default_max_process: 8, default_max_timeout: 60,
    default_max_audio_duration: 300, health_score: 95,
    output_types: ['audio'], device_type: 'http_api', adapter_class: null, audio_config: null,
    rms_spl_mapping_id: null,
    created_at: '2026-09-10T08:00:00', updated_at: '2026-10-09T08:00:00',
    endpoints: [
      { id: 'ep-13-1', endpoint: '/v1/tts/synthesize', name: '合成', max_process: 8, max_timeout: 60, max_audio_duration: 300, status: 'online', health_score: 95, priority: 1, description: null },
    ],
  },
  {
    id: 14, name: 'Realtime WS 网关', vendor: '内部实时组',
    api_url: 'wss://api.audio.test/v1/ws', description: '实时流式 WS 通道',
    status: 'online',
    meta: { protocol: 'wss', environment: 'development', version: '0.9.0' },
    algorithm_type: 'asr_streaming', default_max_process: 16, default_max_timeout: 120,
    default_max_audio_duration: 300, health_score: 94,
    output_types: ['text', 'audio'], device_type: 'websocket_api', adapter_class: null,
    audio_config: null, rms_spl_mapping_id: 2,
    created_at: '2026-09-12T08:00:00', updated_at: '2026-10-11T08:00:00',
    endpoints: [
      { id: 'ep-14-1', endpoint: '/v1/ws/stream', name: '实时流式', max_process: 16, max_timeout: 120, max_audio_duration: 300, status: 'online', health_score: 94, priority: 1, description: null },
    ],
  },
]

export const MOCK_API_DEVICES: ApiDevice[] = MOCK_API_DEVICES_DTO.map(apiDeviceFromDto)

/** RMS-SPL 默认映射名 refs（rms_spl_mapping_id → 名；§3.6「RMS-SPL 默认映射」列） */
export const MOCK_SPL_MAPPING_REFS = [
  { id: 1, name: 'ASR-65dB-标准校准' },
  { id: 2, name: 'WS-70dB-高增益校准' },
  { id: 3, name: 'REF-192k-高采样校准' },
]

/* ==================== 设备分组（§6.3：INT-80 分组 + 嵌套） ==================== */

export const MOCK_DEVICE_GROUPS: DeviceGroup[] = [
  {
    id: 1, name: '客厅组', description: '客厅场景设备', groupType: 'test',
    members: [1, 2], children: [], createdAt: '2026-09-01T09:00:00', updatedAt: '2026-10-10T10:00:00',
  },
  {
    id: 2, name: '回归验证组', description: '旗舰回归验证设备集', groupType: 'test',
    members: [1, 2, 3, 4], children: [], createdAt: '2026-09-05T09:00:00', updatedAt: '2026-10-12T10:00:00',
  },
  {
    id: 3, name: '车载场景组', description: '车载远场验证', groupType: 'test',
    members: [4, 7], children: [{
      id: 31, name: '车载近场子组', description: '近场补充验证', groupType: 'test',
      members: [4], children: [], createdAt: '2026-09-08T09:00:00', updatedAt: '2026-10-08T10:00:00',
    }], createdAt: '2026-09-08T09:00:00', updatedAt: '2026-10-08T10:00:00',
  },
  {
    id: 4, name: '播放设备组', description: '播放设备专用组（未实装）', groupType: 'playback',
    members: [], children: [], createdAt: '2026-09-09T09:00:00', updatedAt: '2026-10-09T10:00:00',
  },
]

/* ==================== 监控告警（§3.7：GET /alarms + stats；已恢复态恒 0 见 §11-3） ==================== */

export const MOCK_ALARM_STATS = { active: 2, acknowledged: 1, resolved: 0, total: 3 }

export const MOCK_ALARMS_DTO: AlarmDto[] = [
  {
    id: 5001, device_id: 8, device_name: '设备-异常节点', rule_id: 901,
    rule_name: '离线超时告警', metric_type: 'offline_duration',
    content: '设备连续离线超过 30 分钟，请检查连接。',
    trigger_value: 33, threshold_value: 30, email_sent: true, email_error: null,
    status: 'active', severity: 'warning', acknowledged_by: null,
    created_at: '2026-10-17T07:05:00',
  },
  {
    id: 5002, device_id: 5, device_name: '手机-小米12', rule_id: 902,
    rule_name: '连接状态告警', metric_type: 'health_check_failures',
    content: '连续 5 次健康检查失败，设备可能失联。',
    trigger_value: 5, threshold_value: 5, email_sent: false, email_error: null,
    status: 'active', severity: 'critical', acknowledged_by: null,
    created_at: '2026-10-17T08:55:00',
  },
  {
    id: 5003, device_id: 3, device_name: '音箱-入门-03', rule_id: 903,
    rule_name: 'CPU 高负载告警', metric_type: 'cpu',
    content: 'CPU 使用率持续超过 90%。',
    trigger_value: 92, threshold_value: 90, email_sent: true, email_error: null,
    status: 'acknowledged', severity: 'info', acknowledged_by: 'yy.dd',
    created_at: '2026-10-16T18:20:00',
  },
]

export const MOCK_ALARMS: Alarm[] = MOCK_ALARMS_DTO.map(alarmFromDto)

export const MOCK_ALARM_RULES_DTO: AlarmRuleDto[] = [
  {
    id: 901, name: '离线超时告警', metric_type: 'offline_duration',
    threshold_value: 30, severity: 'warning', notify_email: true, enabled: true,
    created_at: '2026-09-01T09:00:00', updated_at: '2026-09-01T09:00:00',
  },
  {
    id: 902, name: '连续健康检查失败', metric_type: 'health_check_failures',
    threshold_value: 5, severity: 'critical', notify_email: true, enabled: true,
    created_at: '2026-09-01T09:00:00', updated_at: '2026-09-01T09:00:00',
  },
  {
    id: 903, name: 'CPU 高负载告警', metric_type: 'cpu',
    threshold_value: 90, severity: 'info', notify_email: false, enabled: true,
    created_at: '2026-09-02T09:00:00', updated_at: '2026-09-02T09:00:00',
  },
]

export const MOCK_ALARM_RULES: AlarmRule[] = MOCK_ALARM_RULES_DTO.map(alarmRuleFromDto)

/* ==================== 状态历史（§3.7：GET /status-history；INT-80 + §3.7 扩口） ==================== */

export const MOCK_STATUS_HISTORY_DTO: DeviceStatusHistoryDto[] = [
  {
    id: 8001, device_id: 5, device_name: '手机-小米12', event_type: 'connecting',
    from_status: 'offline', to_status: 'connecting', source: 'monitor', result: 'success',
    detail: 'adb connect 192.168.1.31:5555', created_at: '2026-10-17T08:50:00',
  },
  {
    id: 8002, device_id: 6, device_name: '手机-华为P60', event_type: 'disconnecting',
    from_status: 'online', to_status: 'disconnecting', source: 'manual', result: 'success',
    detail: '用户手动断开', created_at: '2026-10-17T08:20:00',
  },
  {
    id: 8003, device_id: 8, device_name: '设备-异常节点', event_type: 'error',
    from_status: 'online', to_status: 'error', source: 'monitor', result: 'failed',
    detail: '健康检查超时', created_at: '2026-10-17T07:00:00',
  },
  {
    id: 8004, device_id: 1, device_name: '音箱-客厅位', event_type: 'health_check',
    from_status: 'online', to_status: 'online', source: 'health_check', result: 'success',
    detail: '常规健康检查通过', created_at: '2026-10-17T08:40:00',
  },
  {
    id: 8005, device_id: 1, device_name: '音箱-客厅位', event_type: 'operation',
    from_status: 'online', to_status: 'online', source: 'operation', result: 'success',
    detail: '执行「停止测试」：任务 1042 已停止', created_at: '2026-10-17T09:02:00',
  },
]

export const MOCK_STATUS_HISTORY: DeviceStatusEvent[] = MOCK_STATUS_HISTORY_DTO.map(
  statusEventFromDto
)
