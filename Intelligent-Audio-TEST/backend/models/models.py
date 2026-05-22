"""
数据模型定义模块 (Data Models Definition)

本模块定义了系统的所有核心实体模型，基于 SQLAlchemy ORM 构建。
涵盖了用户管理、测试用例、设备、音频、API 配置、测试任务及结果等核心业务领域。

架构层次: Flask Model Layer (MVC - Model)
统一规范:
- 时间戳统一使用东八区时间 (datetime.now(timezone(timedelta(hours=8))))
- 逻辑删除使用 deleted 或 is_deleted 标志
- 所有模型继承自 db.Model
"""
from datetime import datetime, timezone, timedelta
from enum import Enum
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, Boolean, Float, JSON, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import db


class ReportStatus(str, Enum):
    """报告状态枚举"""
    DRAFT = 'draft'
    PUBLISHED = 'published'


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    MERGED = 'merged'


class ReportType(str, Enum):
    """报告类型枚举"""
    TASK = 'task'
    COMPARISON = 'comparison'
    SECONDARY_COMPARISON = 'secondary_comparison'


# 东八区时间辅助函数
def utc8now():
    return datetime.now(timezone(timedelta(hours=8)))

# 1. 用户与权限管理 (User & Permission Management)

class User(db.Model):
    """
    用户模型 (User Model)
    存储系统登录用户信息及基本权限角色。
    """
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='用户唯一ID')
    username = Column(String(50), unique=True, nullable=False, comment='用户名')
    password_hash = Column(String(255), nullable=False, comment='密码哈希值')
    email = Column(String(100), unique=True, nullable=False, comment='电子邮箱')
    role = Column(String(20), nullable=False, comment='用户角色 (admin/editor/viewer)')
    status = Column(String(20), nullable=False, default='active', comment='账户状态 (active/inactive)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

class Permission(db.Model):
    """
    权限模型 (Permission Model)
    定义系统支持的具体操作权限项。
    """
    __tablename__ = 'permissions'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='权限唯一ID')
    name = Column(String(50), unique=True, nullable=False, comment='权限名称')
    description = Column(Text, comment='权限详细描述')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

class UserPermission(db.Model):
    """
    用户权限关联模型 (User-Permission Relation)
    维护用户与权限之间的多对多映射关系。
    """
    __tablename__ = 'user_permissions'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(BigInteger, ForeignKey('users.id'), comment='关联用户ID')
    permission_id = Column(BigInteger, ForeignKey('permissions.id'), comment='关联权限ID')

# 2. 标签管理 (Tag Management)

class TagCategory(db.Model):
    """
    标签分类模型 (Tag Category Model)
    用于对标签进行分类管理，如人数、场景、语种等。
    """
    __tablename__ = 'tag_categories'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='分类唯一ID')
    name = Column(String(50), unique=True, nullable=False, comment='分类名称')
    description = Column(Text, comment='分类描述')
    color = Column(String(20), comment='分类颜色标识 (Hex或名称)')
    sort_order = Column(Integer, default=0, comment='排序顺序 (数值越小越靠前)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    
    tags = relationship('Tag', backref='category', lazy=True)

class Tag(db.Model):
    """
    通用标签模型 (Tag Model)
    可被应用于测试用例、设备、音频、任务等实体的通用标签。
    """
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='标签唯一ID')
    name = Column(String(50), unique=True, nullable=False, comment='标签名称')
    description = Column(Text, comment='标签描述')
    color = Column(String(20), comment='标签颜色标识 (Hex或名称)')
    category_id = Column(Integer, ForeignKey('tag_categories.id'), comment='所属分类ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

# 3. 测试用例管理 (Test Case Management)

class TestCaseGroup(db.Model):
    """
    测试用例分组模型 (Test Case Group Model)
    用于对测试用例进行逻辑分类管理。
    """
    __tablename__ = 'test_case_groups'
    id = Column(String(50), primary_key=True, comment='分组唯一标识符')
    name = Column(String(100), unique=True, nullable=False, comment='分组显示名称')
    description = Column(Text, comment='分组详细描述')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    test_cases = relationship('TestCase', backref='group', lazy=True)

class TestCase(db.Model):
    """
    测试用例模型 (Test Case Model)
    存储测试用例的核心配置信息，包括音频关联、背景噪音设置、算法配置等。
    """
    __tablename__ = 'test_cases'
    id = Column(String(50), primary_key=True, comment='用例唯一标识符')
    name = Column(String(150), nullable=False, comment='用例显示名称')
    description = Column(Text, comment='用例详细描述')
    config = Column(JSON, nullable=False, comment='用例详细配置信息 (JSON格式)，包含音频配置和评测维度配置')
    group_id = Column(String(50), ForeignKey('test_case_groups.id'), comment='所属分组ID')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    _algorithm_params = Column('algorithm_params', JSON, comment='算法参数配置 (JSON格式)，根据算法类型动态配置')
    _reference_params = Column('reference_params', JSON, comment='参考参数配置 (JSON格式)，存储参考文本/音频/文件等参考数据')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')

    tags = relationship('Tag', secondary='test_case_tags', backref='test_cases')

    @property
    def algorithm_params(self):
        return self._algorithm_params

    @algorithm_params.setter
    def algorithm_params(self, value):
        if value is None or value == '' or value == 'null':
            self._algorithm_params = None
        else:
            self._algorithm_params = value

    @property
    def reference_params(self):
        return self._reference_params

    @reference_params.setter
    def reference_params(self, value):
        if value is None or value == '' or value == 'null':
            self._reference_params = None
        else:
            self._reference_params = value

class TestCaseTag(db.Model):
    """
    测试用例标签关联模型 (Test Case-Tag Relation)
    维护测试用例与标签之间的多对多映射关系。
    """
    __tablename__ = 'test_case_tags'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    test_case_id = Column(String(50), ForeignKey('test_cases.id'), comment='关联测试用例ID')
    tag_id = Column(BigInteger, ForeignKey('tags.id'), comment='关联标签ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')



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
    current_spl_mapping_id = Column(Integer, ForeignKey('spl_mappings.id'), comment='当前生效的声压级映射ID')
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
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=True, comment='关联被测设备ID')
    tag_id = Column(Integer, ForeignKey('tags.id'), comment='关联标签ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

# 5. 音频文件管理 (Audio Management)

class TranslationDirection(db.Model):
    """
    翻译语向模型 (Translation Direction Model)
    定义音频翻译支持的源语言和目标语言组合。
    """
    __tablename__ = 'translation_directions'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    source_language = Column(String(20), nullable=False, comment='源语言代码 (如 zh, en)')
    target_language = Column(String(20), nullable=False, comment='目标语言代码 (如 en, ja)')
    description = Column(Text, comment='描述')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

class Audio(db.Model):
    """
    音频文件模型 (Audio Model)
    存储系统中所有音频文件的元数据及物理路径。
    """
    __tablename__ = 'audios'
    __table_args__ = (
        Index('idx_audios_deleted', 'deleted'),
        Index('idx_audios_created_at', 'created_at'),
        Index('idx_audios_deleted_created', 'deleted', 'created_at'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='音频唯一ID')
    name = Column(String(255), nullable=False, comment='音频显示名称')
    original_filename = Column(String(255), comment='上传时的原始文件名')
    file_path = Column(String(500), nullable=False, comment='音频文件在服务器上的物理路径')
    size = Column(Integer, nullable=False, comment='文件大小 (字节)')
    duration = Column(Float, nullable=False, comment='音频时长 (秒)')
    sample_rate = Column(Integer, comment='采样率 (Hz)')
    channels = Column(Integer, comment='声道数')
    bitrate = Column(Integer, comment='比特率 (bps)')
    format = Column(String(20), comment='音频格式 (如 wav, mp3)')
    audio_type = Column(String(20), default='dry', comment='音频类型 (dry: 信号音频 / noise: 噪音音频 / prompt: 提示词音频)')
    asr_text = Column(Text, comment='音频对应的 ASR 识别文本（参考值）')
    description = Column(Text, comment='详细描述')
    md5 = Column(String(32), comment='音频文件MD5值')
    deleted = Column(Boolean, default=False, nullable=False, comment='逻辑删除标志')
    source_language = Column(String(32), comment='源语言')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

class AudioAnnotation(db.Model):
    """
    音频标注模型 (Audio Annotation Model)
    存储音频文件的各种标注格式数据，支持 JSON、RTTM、STM 等格式。
    """
    __tablename__ = 'audio_annotations'
    __table_args__ = (
        Index('idx_audio_annotations_audio_id', 'audio_id'),
        Index('idx_audio_annotations_audio_deleted', 'audio_id', 'deleted'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    audio_id = Column(Integer, ForeignKey('audios.id'), nullable=False, comment='关联音频ID')
    format = Column(String(20), nullable=False, comment='标注格式 (text/json/rttm/stm)')
    code = Column(String(255), comment='标注代码/名称')
    data = Column(JSON, nullable=False, comment='标注数据内容')
    source_language = Column(String(20), comment='源语言代码')
    target_language = Column(String(20), comment='目标语言代码')
    deleted = Column(Boolean, default=False, nullable=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    audio = relationship('Audio', backref='annotations')

class AudioTag(db.Model):
    """
    音频标签关联模型 (Audio-Tag Relation)
    维护音频文件与标签之间的多对多映射关系。
    """
    __tablename__ = 'audio_tags'
    __table_args__ = (
        Index('idx_audio_tags_audio_id', 'audio_id'),
        Index('idx_audio_tags_tag_id', 'tag_id'),
        Index('idx_audio_tags_audio_tag', 'audio_id', 'tag_id'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    audio_id = Column(Integer, ForeignKey('audios.id'), comment='关联音频ID')
    tag_id = Column(Integer, ForeignKey('tags.id'), comment='关联标签ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')


class AudioAlgorithmRelation(db.Model):
    """
    音频与算法关联模型 (Audio-Algorithm Relation)
    支持一个音频关联多个算法。
    """
    __tablename__ = 'audio_algorithm_relations'
    __table_args__ = (
        Index('idx_audio_algorithm_audio', 'audio_id'),
        Index('idx_audio_algorithm_type', 'algorithm_type'),
        UniqueConstraint('audio_id', 'algorithm_type', name='uq_audio_algorithm'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    audio_id = Column(BigInteger, ForeignKey('audios.id', ondelete='CASCADE'), nullable=False, comment='关联音频ID')
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False, comment='关联算法类型')
    is_primary = Column(Boolean, default=False, comment='是否主要算法')
    weight = Column(Float, default=1.0, comment='权重')
    params = Column(JSON, comment='算法特定参数')
    deleted = Column(Boolean, default=False, nullable=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    audio = relationship('Audio', backref='algorithm_relations')
    algorithm = relationship('AlgorithmDefinition')

    def to_dict(self):
        return {
            'id': self.id,
            'audio_id': self.audio_id,
            'algorithm_type': self.algorithm_type,
            'algorithm_name': self.algorithm.name if self.algorithm else None,
            'is_primary': self.is_primary,
            'weight': self.weight,
            'params': self.params
        }

class PromptAudioRelation(db.Model):
    """
    提示词音频关联模型 (Prompt Audio Relation)
    支持多维度关联提示词音频：设备、算法类型、翻译方向/语言。
    """
    __tablename__ = 'prompt_audio_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    audio_id = Column(Integer, ForeignKey('audios.id'), nullable=False, comment='关联提示词音频ID')
    device_id = Column(Integer, ForeignKey('devices.id'), comment='关联设备ID (可选，为空表示通用)')
    algorithm_type = Column(String(50), comment='算法类型 (如: translation, asr, tts, speaker_recognition)')
    source_language = Column(String(20), comment='源语言代码 (如 zh, en)')
    target_language = Column(String(20), comment='目标语言代码 (如 en, ja)')
    translation_direction = Column(String(50), comment='翻译方向字符串 (如 zh2en, en2zh)')
    priority = Column(Integer, default=0, comment='匹配优先级 (数值越大优先级越高)')
    deleted = Column(Boolean, default=False, nullable=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

# 6. API 配置管理 (API Configuration)

class API(db.Model):
    """
    API 配置模型 (API Configuration Model)
    存储被测翻译 API 或语音识别 API 的连接配置及性能约束。
    """
    __tablename__ = 'apis'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='API唯一ID')
    name = Column(String(255), nullable=False, comment='API显示名称')
    vendor = Column(String(50), nullable=True, comment='供应商名称 (如 volc_ast, ali, tencent)')
    api_url = Column(String(512), comment='API微服务主入口URL')
    description = Column(Text, comment='详细描述')
    status = Column(String(20), nullable=False, default='online', comment='服务状态 (online/offline)')
    meta = Column(JSON, nullable=False, comment='API元数据 (鉴权信息、额外参数等)')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    max_process = Column(Integer, nullable=False, default=5, comment='最大并发处理数')
    max_timeout = Column(Integer, nullable=False, default=30, comment='最大超时时间 (秒)')
    max_audio_duration = Column(Integer, nullable=False, default=60, comment='支持的最大音频时长 (秒)')
    health_score = Column(Float, nullable=False, default=100.0, comment='健康度评分 (0-100)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    default_max_process = Column(Integer, nullable=False, default=5, comment='默认最大并发处理数')
    default_max_timeout = Column(Integer, nullable=False, default=30, comment='默认最大超时时间 (秒)')
    default_max_audio_duration = Column(Integer, nullable=False, default=60, comment='默认支持的最大音频时长 (秒)')
    api_endpoints = Column(JSON, nullable=False, default=list, comment='API接入点配置列表 (JSON格式)')


# 7. 测试任务管理 (Test Task Management)

class Task(db.Model):
    """
    测试任务模型 (Test Task Model)
    代表一次完整的测试执行过程，关联了用例、设备、API、算法配置及最终结果。
    """
    __tablename__ = 'test_tasks'
    __table_args__ = (
        Index('idx_task_status', 'status'),
        Index('idx_task_algorithm_type', 'algorithm_type'),
        Index('idx_task_created_at', 'created_at'),
        Index('idx_task_status_deleted', 'status', 'deleted'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='任务唯一ID')
    name = Column(String(255), nullable=False, comment='任务名称')
    description = Column(Text, comment='任务描述')
    type = Column(String(50), nullable=False, comment='任务类型 (api/e2e)')
    status = Column(String(20), nullable=False, default='pending', comment='任务状态 (pending/queued/running/evaluating/reevaluate_queued/reevaluating/completed/failed/stopped/paused/skipped)')
    config = Column(JSON, comment='任务执行时的特定配置')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    algorithm_params = Column(JSON, comment='算法参数配置 (JSON格式)')
    total_cases = Column(Integer, nullable=False, default=0, comment='总测试用例数量')
    completed_cases = Column(Integer, nullable=False, default=0, comment='已执行完成的用例数量')
    failed_cases = Column(Integer, nullable=False, default=0, comment='执行失败的用例数量')
    created_by = Column(Integer, comment='创建者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    started_at = Column(DateTime, comment='任务实际开始执行时间')
    completed_at = Column(DateTime, comment='任务执行结束时间')
    estimated_time = Column(Integer, comment='预计执行耗时 (秒)')
    actual_duration = Column(Integer, comment='实际执行耗时 (秒)')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    
    tags = relationship('Tag', secondary='task_tags', backref='tasks')
    cases = relationship('TestCase', secondary='task_case_relations', backref='tasks')
    devices = relationship('Device', secondary='task_device_relations', backref='tasks')
    apis = relationship('API', secondary='task_api_relations', backref='tasks')

class TaskTag(db.Model):
    """
    任务标签关联模型 (Task-Tag Relation)
    维护测试任务与标签之间的多对多映射关系。
    """
    __tablename__ = 'task_tags'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(BigInteger, ForeignKey('test_tasks.id'), comment='关联测试任务ID')
    tag_id = Column(BigInteger, ForeignKey('tags.id'), comment='关联标签ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

class TaskCase(db.Model):
    """
    任务-用例执行状态模型 (Task-Case Relation)
    记录特定任务中每个用例的执行状态和耗时。
    """
    __tablename__ = 'task_case_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(BigInteger, ForeignKey('test_tasks.id'), comment='关联测试任务ID')
    test_case_id = Column(String(50), ForeignKey('test_cases.id'), comment='关联测试用例ID')
    status = Column(String(50), default='pending', nullable=True, comment='该用例在任务中的最终结果 (pending/completed/failed/skipped)')
    execution_status = Column(String(20), default='pending', nullable=False, comment='执行过程状态 (pending/running/completed/stopped/failed)')
    evaluation_status = Column(String(20), default='pending', nullable=False, comment='评估过程状态 (queued/pending/running/calculating/completed/stopped/failed)')
    started_at = Column(DateTime, comment='开始执行时间')
    completed_at = Column(DateTime, comment='执行结束时间')
    duration = Column(Integer, comment='执行耗时 (秒)')
    error_message = Column(Text, comment='执行过程中的错误信息')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

class TaskDevice(db.Model):
    """
    任务设备关联模型 (Task-Device Relation)
    定义任务执行时所使用的被测设备。
    """
    __tablename__ = 'task_device_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(Integer, ForeignKey('test_tasks.id'), comment='关联测试任务ID')
    device_id = Column(Integer, ForeignKey('devices.id'), comment='关联被测设备ID')

class TaskAPI(db.Model):
    """
    任务 API 关联模型 (Task-API Relation)
    定义任务执行时所调用的 API 服务。
    """
    __tablename__ = 'task_api_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(Integer, ForeignKey('test_tasks.id'), comment='关联测试任务ID')
    api_id = Column(Integer, ForeignKey('apis.id'), comment='关联 API ID')

class TaskMergeRelation(db.Model):
    """
    任务合并关联模型 (Task Merge Relation)
    记录合并任务与源任务之间的多对多映射关系。
    """
    __tablename__ = 'task_merge_relations'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    merged_task_id = Column(Integer, ForeignKey('test_tasks.id'), nullable=False, comment='合并后的任务ID')
    source_task_id = Column(Integer, ForeignKey('test_tasks.id'), nullable=False, comment='源任务ID')
    source_result_count = Column(Integer, default=0, comment='该源任务贡献的结果数量')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

    merged_task = relationship('Task', foreign_keys=[merged_task_id], backref='source_relations')
    source_task = relationship('Task', foreign_keys=[source_task_id], backref='target_relations')

# 8. 测试结果管理 (Test Result Management)

class TestResult(db.Model):
    """
    测试结果模型 (Test Result Model)
    记录单个测试用例在特定设备和 API 上的执行详细结果。
    支持多种算法类型 (translation, asr, tts, speaker_recognition 等)。
    所有算法结果统一使用 algorithm_result (JSON) 存储。
    """
    __tablename__ = 'test_results'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='结果唯一ID')
    task_id = Column(Integer, ForeignKey('test_tasks.id'), comment='关联测试任务ID')
    test_case_id = Column(String(50), ForeignKey('test_cases.id'), comment='关联测试用例ID')
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=True, comment='关联被测设备ID')
    api_id = Column(Integer, ForeignKey('apis.id'), comment='关联 API ID')
    algorithm_type = Column(String(50), comment='算法类型 (如: translation, asr, tts, speaker_recognition)')
    execution_status = Column(String(20), default='pending', nullable=False, comment='执行过程状态 (pending/running/completed/stopped/failed)')
    response_time = Column(Integer, comment='API 响应时间 (ms)')
    algorithm_result = Column(JSON, comment='算法执行结果 (JSON，不同算法类型结构不同)')
    execution_steps = Column(JSON, default=list, comment='执行步骤详细日志 (JSON)')
    result_data = Column(JSON, nullable=False, comment='原始测试结果数据 (JSON)')
    error_message = Column(Text, comment='错误信息描述')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='生成时间')

class TestResultDimension(db.Model):
    """
    测试结果维度得分模型 (Test Result Dimension Score Model)
    存储单个测试结果在各个评估维度上的具体得分和状态。
    支持多种算法类型 (translation, asr, tts, speaker_recognition 等)。
    """
    __tablename__ = 'test_result_dimensions'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    test_result_id = Column(BigInteger, ForeignKey('test_results.id'), comment='关联测试结果ID')
    dimension_id = Column(BigInteger, ForeignKey('dimensions.id'), comment='关联评估维度ID')
    algorithm_type = Column(String(50), comment='算法类型 (如: translation, asr, tts, speaker_recognition)')
    dimension_value = Column(Float, comment='维度计算出的原始值 (如 BLEU 分数)')
    score = Column(Float, comment='维度最终得分')
    status = Column(String(20), nullable=True, comment='维度评估结果状态 (passed/failed)')
    evaluation_status = Column(String(20), default='pending', nullable=False, comment='评估过程状态 (pending/running/completed/stopped)')
    error_message = Column(Text, comment='评估过程中的错误信息')
    api_raw_response = Column(JSON, comment='评测API的原始响应数据')
    api_request_body = Column(JSON, comment='评测API的原始请求体数据')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='生成时间')

class Report(db.Model):
    """
    测试报告模型 (Test Report Model)
    存储任务执行完成后生成的汇总分析报告。
    """
    __tablename__ = 'test_reports'
    __table_args__ = (
        Index('idx_report_task_id', 'task_id'),
        Index('idx_report_type', 'type'),
        Index('idx_report_status', 'status'),
        Index('idx_report_created_at', 'created_at'),
        Index('idx_report_type_status', 'type', 'status'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='报告唯一ID')
    name = Column(String(255), nullable=False, comment='报告名称')
    type = Column(String(30), nullable=False, comment='报告类型')
    description = Column(Text, comment='报告详细描述')
    task_id = Column(Integer, ForeignKey('test_tasks.id'), comment='关联测试任务ID')
    status = Column(String(20), nullable=False, default='draft', comment='报告状态 (draft/published)')
    analysis = Column(Text, comment='人工/自动分析结论')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    task = relationship('Task', backref='reports')

    summary_info = relationship('ReportSummary', backref='report', uselist=False, lazy='joined', passive_deletes=True)
    detail_data = relationship('ReportDetailData', backref='report', uselist=False, lazy='joined', passive_deletes=True)

class ReportSummary(db.Model):
    """
    报告摘要模型 (Report Summary Model)
    存储报告的小数据量摘要信息，用于列表页快速查询。
    与 Report 一对一关联。
    """
    __tablename__ = 'report_summaries'
    __table_args__ = (
        Index('idx_report_summary_report_id', 'report_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='摘要唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, unique=True, comment='关联报告ID')
    task_ids = Column(JSON, comment='关联任务ID列表 (对比报告使用)')
    total_cases = Column(Integer, default=0, comment='总用例数')
    completed_cases = Column(Integer, default=0, comment='完成用例数')
    failed_cases = Column(Integer, default=0, comment='失败用例数')
    pass_rate = Column(Float, default=0, comment='通过率')
    dimension_values = Column(JSON, comment='维度平均分列表')
    duration = Column(Float, default=0, comment='任务执行时长(秒)')
    started_at = Column(DateTime, comment='任务开始时间')
    completed_at = Column(DateTime, comment='任务完成时间')
    case_categories = Column(JSON, comment='用例分组列表')
    all_case_tags = Column(JSON, comment='用例标签列表')
    devices = Column(JSON, comment='设备列表')
    apis = Column(JSON, comment='API列表')
    resources = Column(JSON, comment='资源列表')
    resource_headers = Column(JSON, comment='资源头信息')
    all_metrics = Column(JSON, comment='评估维度列表')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

class ReportDetailData(db.Model):
    """
    报告详情数据模型 (Report Detail Data Model)
    存储报告的大数据量详情信息，用于详情页按需加载。
    与 Report 一对一关联。
    """
    __tablename__ = 'report_detail_data'
    __table_args__ = (
        Index('idx_report_detail_report_id', 'report_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='详情唯一ID')
    report_id = Column(BigInteger, ForeignKey('test_reports.id'), nullable=False, unique=True, comment='关联报告ID')
    raw_data = Column(JSON, comment='原始维度分数数据')
    metric_data = Column(JSON, comment='分组指标数据')
    tag_metric_data = Column(JSON, comment='标签指标数据')
    tag_category_metric_data = Column(JSON, comment='按标签分类的指标数据')
    case_type_stats = Column(JSON, comment='用例类型统计数据')
    device_stats = Column(JSON, comment='设备统计数据')
    api_stats = Column(JSON, comment='API统计数据')
    cases = Column(JSON, comment='用例详情列表')
    comparison_matrix = Column(JSON, comment='对比矩阵数据 (对比报告使用)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

# 9. 评估维度管理 (Evaluation Dimension Management)

class Category(db.Model):
    """
    评估分类模型 (Category Model)
    用于对评估维度进行大类划分（如 准确性、流畅度、响应速度）。
    """
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='分类唯一ID')
    name = Column(String(100), unique=True, nullable=False, comment='分类名称')
    description = Column(Text, comment='分类详细描述')
    icon = Column(String(50), nullable=False, comment='分类图标标识')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

class Dimension(db.Model):
    """
    评估维度模型 (Dimension Model)
    定义具体的质量评估指标、评分规则及计算 API。
    支持主维度-子维度层级关系。
    """
    __tablename__ = 'dimensions'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='维度唯一ID')
    name = Column(String(255), nullable=False, comment='维度名称')
    keywords = Column(String(255), comment='搜索关键字')
    dimension_type = Column(String(20), default='main', comment='维度类型: main(主维度)/sub(子维度)')
    parent_dimension_id = Column(Integer, ForeignKey('dimensions.id'), nullable=True, comment='主维度ID')
    task_type_code = Column(String(50), nullable=True, comment='API调用的task_type值（如 wer）')
    description = Column(Text, comment='维度详细描述')
    category_id = Column(Integer, ForeignKey('categories.id'), comment='所属分类ID')
    type = Column(String(50), nullable=False, comment='评估类型 (auto/manual)')
    result_type = Column(Integer, nullable=False, comment='结果数据类型 (1:数值, 2:布尔, 3:文本)')
    result_min = Column(Float, comment='结果最小值限制')
    result_max = Column(Float, comment='结果最大值限制')
    decimal_places = Column(Integer, comment='数值保留小数位数')
    weight = Column(Integer, nullable=False, default=1, comment='维度权重')
    estimated_exec_time = Column(Integer, nullable=False, default=10, comment='预计执行时间 (秒)')
    rule = Column(JSON, nullable=True, default=dict, comment='评分规则配置')
    api_settings = Column(JSON, comment='API 调用详细设置')
    status = Column(Boolean, nullable=False, default=True, comment='是否启用标志')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    api_status = Column(String(20), nullable=False, default='online', comment='算法 API 在线状态')
    api_endpoints = Column(JSON, nullable=True, default=list, comment='多个评估算法 API 地址及配置')
    api_url = Column(String(512), comment='评估微服务主入口URL')
    score_unit = Column(String(50), nullable=True, default='', comment='分数单位')

    parent_dimension = relationship('Dimension', remote_side=[id], backref='sub_dimensions')

# 10. 日志管理 (Log Management)

class Log(db.Model):
    """
    系统日志模型 (System Log Model)
    存储系统运行过程中的各类日志信息，用于审计和故障排查。
    """
    __tablename__ = 'logs'
    __table_args__ = (
        Index('idx_task_time', 'task_id', 'time'),
        Index('idx_time', 'time'),
        Index('idx_task_id', 'task_id'),
        Index('idx_level', 'level'),
        Index('idx_category', 'category'),
        Index('idx_module', 'module'),
        Index('idx_level_time', 'level', 'time'),
        Index('idx_category_time', 'category', 'time'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='日志唯一ID')
    time = Column(DateTime, nullable=False, comment='日志产生时间')
    level = Column(String(20), nullable=False, comment='日志级别 (DEBUG/INFO/WARN/ERROR)')
    category = Column(String(50), nullable=False, comment='日志分类 (System/Task/Device)')
    module = Column(String(100), nullable=False, comment='所属代码模块')
    source = Column(String(100), nullable=False, comment='日志来源标识')
    content = Column(Text, nullable=False, comment='日志正文内容')
    mark = Column(String(20), comment='特定标记')
    device_id = Column(Integer, ForeignKey('devices.id'), comment='关联设备ID')
    task_id = Column(Integer, ForeignKey('test_tasks.id'), comment='关联任务ID')
    test_case_id = Column(String(50), ForeignKey('test_cases.id'), comment='关联用例ID')
    api_id = Column(Integer, ForeignKey('apis.id'), comment='关联API ID')
    thread_id = Column(String(50), comment='线程 ID')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='记录创建时间')

# 11. 扩展功能 (Extensions)

class SPLMapping(db.Model):
    """
    声压级映射模型 (SPL Mapping Model)
    存储播放设备在特定距离下，目标声压级与数字增益之间的对应关系，用于音频校准。
    """
    __tablename__ = 'spl_mappings'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='映射唯一ID')
    name = Column(String(100), nullable=False, comment='映射配置名称')
    description = Column(Text, comment='映射配置详细描述')
    device_id = Column(Integer, ForeignKey('playback_devices.id'), comment='关联播放设备ID')
    device_type = Column(String(50), comment='适用的设备类型')
    distance = Column(Float, default=1.0, comment='测试时的物理距离 (米)')
    target_spl = Column(Float, comment='目标声压级 (dB SPL)')
    digital_gain = Column(Float, comment='对应的数字增益值 (dB)')
    
    calibration_status = Column(String(20), default='uncalibrated', comment='校准状态 (calibrated/uncalibrated)')
    test_frequency = Column(Integer, default=1000, comment='校准时使用的测试频率 (Hz)')
    calibration_data = Column(JSON) # 详细校准测量点数据 (JSON)
    
    created_at = Column(DateTime, default=utc8now, nullable=False)
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False)

class CalibrationHistory(db.Model):
    __tablename__ = 'calibration_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    mapping_id = Column(Integer, ForeignKey('spl_mappings.id'), nullable=False)
    distance = Column(Float) # 校准时的距离
    test_frequency = Column(Integer) # 校准时的频率
    calibration_data = Column(JSON)
    created_at = Column(DateTime, default=utc8now, nullable=False)

# 12. 文件上传任务管理 (File Upload Management)

class UploadTask(db.Model):
    """
    上传任务模型 (Upload Task Model)
    存储文件上传任务的基本信息和状态
    """
    __tablename__ = 'upload_tasks'
    id = Column(String(50), primary_key=True, comment='任务唯一标识符')
    total_files = Column(Integer, nullable=False, default=0, comment='总文件数量')
    completed_files = Column(Integer, nullable=False, default=0, comment='已完成文件数量')
    failed_files = Column(Integer, nullable=False, default=0, comment='失败文件数量')
    total_size = Column(Integer, nullable=False, default=0, comment='总文件大小 (字节)')
    uploaded_size = Column(Integer, nullable=False, default=0, comment='已上传大小 (字节)')
    status = Column(String(20), nullable=False, default='preparing', comment='任务状态 (preparing/uploading/completed/failed)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    expired_at = Column(DateTime, comment='任务过期时间')
    
    files = relationship('UploadFile', backref='task', cascade="all, delete-orphan")

class UploadFile(db.Model):
    """
    上传文件模型 (Upload File Model)
    存储单个文件的上传信息
    """
    __tablename__ = 'upload_files'
    id = Column(String(50), primary_key=True, comment='文件唯一标识符')
    task_id = Column(String(50), ForeignKey('upload_tasks.id'), comment='关联上传任务ID')
    filename = Column(String(255), nullable=False, comment='文件名')
    original_filename = Column(String(255), nullable=False, comment='原始文件名')
    relative_path = Column(String(500), comment='相对路径')
    size = Column(Integer, nullable=False, default=0, comment='文件大小 (字节)')
    md5 = Column(String(32), comment='文件MD5值')
    status = Column(String(20), nullable=False, default='pending', comment='文件状态 (pending/uploading/completed/failed)')
    uploaded_size = Column(Integer, nullable=False, default=0, comment='已上传大小 (字节)')
    completed_chunks = Column(Integer, nullable=False, default=0, comment='已完成分片数量')
    total_chunks = Column(Integer, nullable=False, default=0, comment='总分片数量')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    
    chunks = relationship('UploadChunk', backref='file', cascade="all, delete-orphan")

class UploadChunk(db.Model):
    """
    上传分片模型 (Upload Chunk Model)
    存储单个文件分片的上传信息
    """
    __tablename__ = 'upload_chunks'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='分片唯一ID')
    file_id = Column(String(50), ForeignKey('upload_files.id'), comment='关联上传文件ID')
    chunk_index = Column(Integer, nullable=False, comment='分片索引')
    chunk_size = Column(Integer, nullable=False, comment='分片大小 (字节)')
    md5 = Column(String(32), comment='分片MD5值')
    status = Column(String(20), nullable=False, default='pending', comment='分片状态 (pending/uploading/completed/failed)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    
    stored_path = Column(String(500), comment='分片存储路径')


# 13. 统计缓存管理 (Stats Cache Management)

class StatsCache(db.Model):
    """
    统计缓存模型 (Stats Cache Model)
    存储预计算的统计数据，用于首页快速展示。
    数据变化时自动更新缓存。
    """
    __tablename__ = 'stats_cache'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='缓存唯一ID')
    cache_key = Column(String(100), nullable=False, unique=True, comment='缓存键值')
    cache_value = Column(JSON, nullable=False, comment='缓存数据 (JSON格式)')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='最后更新时间')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')

