# -*- coding: utf-8 -*-
"""device_service 设备管理 PO 定义

归属：device_service（e2e 测试上下文，物理设备所有权）
表：devices / playback_devices / device_tags
INT-80 新增表：device_groups / device_group_members / device_status_events /
               device_alarm_rules / device_alarms

P5 改造：从 shared/models/models/device_models.py 真正下沉到本服务。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index, text,
)


class Device(Base):
    """被测设备模型 (DUT - Device Under Test Model)
    存储待测终端设备（如手机、平板）的硬件信息、系统版本及应用配置。
    """
    __tablename__ = 'devices'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='设备唯一ID')
    name = Column(String(100), nullable=False, index=True, comment='设备名称')
    model = Column(String(100), nullable=False, comment='设备型号')
    description = Column(Text, comment='设备详细描述')
    type = Column(String(50), nullable=False, comment='设备类型 (phone/tablet)')
    system = Column(String(50), nullable=False, comment='操作系统 (Android/iOS/HarmonyOS)')
    system_version = Column(String(20), nullable=False, comment='操作系统版本')
    app_name = Column(String(100), nullable=False, comment='待测应用名称')
    app_version = Column(String(20), nullable=False, comment='待测应用版本')
    location = Column(String(100), comment='设备物理存放位置')
    max_audio_duration = Column(Float, comment='设备支持的最大音频播放时长 (秒)')
    needs_prompt_audio = Column(Boolean, default=False, comment='是否需要播放提示词音频')
    prompt_config = Column(JSON, comment='提示词音频配置 (语言方向ID: 音频ID)')
    connection_type = Column(String(20), comment='连接方式 (remote: 远程连接 / usb: USB连接)')
    keywords = Column(String(100), comment='驱动匹配关键字')
    serial_number = Column(String(100), comment='设备序列号 (通过 ADB/HDC 获取)')
    ip = Column(String(50), comment='设备IP地址')
    status = Column(String(20), nullable=False, default='offline', index=True, comment='在线状态 (online/offline)')
    last_online_at = Column(DateTime, comment='最后一次在线时间')
    supported_algorithms = Column(JSON, default=list, comment='支持的算法类型列表')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')


class PlaybackDevice(Base):
    """播放设备模型 (Playback Device Model)
    存储用于播放测试音频的音频外设（如声卡通道、音箱）信息。
    """
    __tablename__ = 'playback_devices'
    __table_args__ = (
        Index('uq_device_channel', 'device_unique_id', 'channel_index',
              unique=True, postgresql_where=text('is_deleted = 0')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    name = Column(String(100), nullable=False, comment='播放设备名称')
    model = Column(String(100), nullable=False, comment='播放设备型号')
    device_type = Column(String(20), nullable=False, comment='播放设备类型 (noise: 噪音设备 / dry: 信号设备)')
    sample_rate = Column(Integer, nullable=False, comment='支持的采样率 (Hz)')
    channel_index = Column(Integer, default=0, comment='声卡通道索引 (从0开始)')
    device_unique_id = Column(String(100), nullable=False, comment='设备硬件唯一标识符')
    description = Column(Text, comment='详细描述')
    status = Column(String(10), nullable=False, default='online', comment='运行状态 (online: 在线 / offline: 离线)')
    is_deleted = Column(Integer, nullable=False, default=0, comment='逻辑删除标志 (0: 否 / 1: 是)')
    current_spl_mapping_id = Column(Integer, comment='当前生效的声压级映射ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
    created_by = Column(String(50), comment='创建者姓名/账号')


class DeviceTag(Base):
    """设备标签关联模型 (Device-Tag Relation)
    维护被测设备与标签之间的多对多映射关系。
    """
    __tablename__ = 'device_tags'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    device_id = Column(Integer, nullable=True, comment='关联被测设备ID')
    tag_id = Column(Integer, comment='关联标签ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')


class DeviceGroup(Base):
    """设备分组模型（INT-80，区别于 task_service 的用例分组 test_case_groups）

    对设备进行逻辑分组，方便管理和批量操作。
    """
    __tablename__ = 'device_groups'
    __table_args__ = (
        # 并发重名兜底（应用层重名检查存在 TOCTOU）：仅约束未删除分组
        Index('uq_device_group_name_active', 'name', unique=True,
              postgresql_where=text('deleted = false')),
    )
    id = Column(String(50), primary_key=True, comment='分组唯一标识符 (UUID)')
    name = Column(String(100), nullable=False, index=True, comment='分组名称')
    description = Column(Text, comment='分组描述')
    group_type = Column(String(20), nullable=False, default='test', comment='分组类型 (test: 测试设备组 / playback: 播放设备组)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间')


class DeviceGroupMember(Base):
    """设备分组成员关联模型（INT-80）

    维护设备分组与被测设备之间的多对多映射关系。
    """
    __tablename__ = 'device_group_members'
    __table_args__ = (
        Index('uq_device_group_member', 'group_id', 'device_id', unique=True),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    group_id = Column(String(50), nullable=False, index=True, comment='所属分组ID')
    device_id = Column(Integer, nullable=False, index=True, comment='关联被测设备ID')
    created_by_user_id = Column(BigInteger, nullable=True, comment='创建者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='加入时间')


class DeviceStatusEvent(Base):
    """设备状态历史事件模型（INT-80 监控告警：在线/离线/健康事件落库）"""
    __tablename__ = 'device_status_events'
    __table_args__ = (
        Index('ix_status_event_device_time', 'device_id', 'created_at'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    device_id = Column(Integer, nullable=False, index=True, comment='设备ID')
    event_type = Column(String(20), nullable=False, comment='事件类型 (online/offline/health_check/operation)')
    from_status = Column(String(20), comment='变更前状态')
    to_status = Column(String(20), comment='变更后状态')
    source = Column(String(50), default='monitor', comment='事件来源 (health_check/monitor/manual/operation)')
    success = Column(Boolean, default=True, comment='检查/操作是否成功')
    detail = Column(JSON, comment='事件详情 (操作结果/健康数据等)')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, index=True, comment='事件时间')


class DeviceAlarmRule(Base):
    """设备告警规则模型（INT-80：离线时长/健康检查失败次数/CPU/内存/电池阈值）"""
    __tablename__ = 'device_alarm_rules'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    name = Column(String(100), nullable=False, comment='规则名称')
    metric_type = Column(String(30), nullable=False, index=True, comment='告警指标 (offline_duration/health_check_failures/cpu/memory/battery)')
    threshold_value = Column(Float, nullable=False, comment='阈值')
    severity = Column(String(20), nullable=False, default='warning', comment='告警级别 (info/warning/critical)')
    notify_email = Column(Boolean, nullable=False, default=True, comment='触发时是否发送邮件通知')
    enabled = Column(Boolean, nullable=False, default=True, comment='规则是否启用')
    created_by_user_id = Column(BigInteger, nullable=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')


class DeviceAlarm(Base):
    """设备告警记录模型（INT-80 告警落库与确认流）"""
    __tablename__ = 'device_alarms'
    __table_args__ = (
        Index('ix_alarm_status_time', 'status', 'triggered_at'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    rule_id = Column(Integer, comment='触发的告警规则ID')
    rule_name = Column(String(100), comment='规则名称快照（规则删除后仍可读）')
    device_id = Column(Integer, nullable=False, index=True, comment='设备ID')
    device_name = Column(String(100), comment='设备名称快照')
    metric_type = Column(String(30), nullable=False, comment='告警指标')
    severity = Column(String(20), nullable=False, default='warning', comment='告警级别 (info/warning/critical)')
    status = Column(String(20), nullable=False, default='active', index=True, comment='告警状态 (active/acknowledged/resolved)')
    trigger_value = Column(Float, comment='触发时的指标值')
    threshold_value = Column(Float, comment='触发时的阈值')
    content = Column(Text, comment='告警内容描述')
    email_sent = Column(Boolean, nullable=False, default=False, comment='是否已发送邮件通知')
    email_error = Column(Text, comment='邮件发送失败原因')
    triggered_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='触发时间')
    acknowledged_at = Column(DateTime, nullable=True, comment='确认时间')
    acknowledged_by = Column(String(100), nullable=True, comment='确认人')
    resolved_at = Column(DateTime, nullable=True, comment='恢复时间')
