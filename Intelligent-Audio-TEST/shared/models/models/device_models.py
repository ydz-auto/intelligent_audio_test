"""
设备管理模型 (Device Management)

包含被测设备 (DUT)、播放设备及设备-标签关联模型。
"""
from ._base import (
    db, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    utc8now,
)


# 4. 设备管理 (Device Management)

class Device(db.Model):
    """
    被测设备模型 (DUT - Device Under Test Model)
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
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

class PlaybackDevice(db.Model):
    """
    播放设备模型 (Playback Device Model)
    存储用于播放测试音频的音频外设（如声卡通道、音箱）信息。
    """
    __tablename__ = 'playback_devices'
    __table_args__ = (
        db.UniqueConstraint('device_unique_id', 'channel_index', name='uq_device_channel'),
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
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    created_by = Column(String(50), comment='创建者姓名/账号')

class DeviceTag(db.Model):
    """
    设备标签关联模型 (Device-Tag Relation)
    维护被测设备与标签之间的多对多映射关系。
    """
    __tablename__ = 'device_tags'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    device_id = Column(Integer, nullable=True, comment='关联被测设备ID')
    tag_id = Column(Integer, comment='关联标签ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
