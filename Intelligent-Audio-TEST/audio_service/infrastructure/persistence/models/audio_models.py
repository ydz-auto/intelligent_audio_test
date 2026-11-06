# -*- coding: utf-8 -*-
"""audio_service 音频文件管理 PO 定义

归属：audio_service（e2e 测试上下文，音频素材所有权）
表：audios / audio_annotations / audio_tags / audio_algorithm_relations / audio_playback_history

P5 改造：从 shared/models/models/audio_models.py 真正下沉到本服务。

关键决策：移除 AudioAlgorithmRelation.algorithm 跨域 relationship
（AlgorithmDefinition 归属 algorithm_service）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index, ForeignKey, text,
)
from sqlalchemy.orm import relationship


class Audio(Base):
    """音频文件模型 (Audio Model)
    存储系统中所有音频文件的元数据及物理路径。
    """
    __tablename__ = 'audios'
    # INT-1784：idx_audios_deleted 已下线（deleted 是 (deleted, created_at) 的列序前缀）
    __table_args__ = (
        Index('idx_audios_created_at', 'created_at'),
        Index('idx_audios_deleted_created', 'deleted', 'created_at'),
        # INT-423 数据可见性：行级过滤高频列表表复合索引（与迁移脚本对齐）
        Index('idx_audios_created_visibility', 'created_by_user_id', 'visibility'),
        # INT-2280 上传去重 / stream 可见性校验：按 md5、file_path 等值查询此前无索引，
        # 逐文件一次全表扫描（ZIP 回导 O(文件数 × 表行数)）。两条读路径
        # （get_audio_by_md5 / get_audio_by_file_path / get_audios_by_md5_list）恒带
        # deleted = false，故建局部索引（软删行不进索引，体积更小）。
        # 与 scripts/migrations/202611/add_audios_md5_filepath_index.py 定义对齐。
        Index('idx_audios_md5', 'md5', postgresql_where=text('deleted = false')),
        Index('idx_audios_file_path', 'file_path', postgresql_where=text('deleted = false')),
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
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    deleted_by_user_id = Column(BigInteger, nullable=True, comment='执行删除操作的用户ID（JWT，INT-299）')
    source_language = Column(String(32), comment='源语言')
    # INT-1784：(created_by_user_id, visibility) 复合索引覆盖该列，单列索引下线
    created_by_user_id = Column(BigInteger, nullable=True, comment='创建者用户ID')
    visibility = Column(String(20), nullable=False, default='shared', server_default='shared',
                        comment='数据可见性（shared/private，INT-423）')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')


class AudioAnnotation(Base):
    """音频标注模型 (Audio Annotation Model)
    存储音频文件的各种标注格式数据，支持 JSON、RTTM、STM 等格式。
    """
    __tablename__ = 'audio_annotations'
    __table_args__ = (
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
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')

    audio = relationship('Audio', foreign_keys='AudioAnnotation.audio_id', backref='annotations')


class AudioTag(Base):
    """音频标签关联模型 (Audio-Tag Relation)
    维护音频文件与标签之间的多对多映射关系。
    """
    __tablename__ = 'audio_tags'
    __table_args__ = (
        Index('idx_audio_tags_tag_id', 'tag_id'),
        Index('idx_audio_tags_audio_tag', 'audio_id', 'tag_id'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    audio_id = Column(Integer, comment='关联音频ID')
    tag_id = Column(Integer, comment='关联标签ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')


class AudioAlgorithmRelation(Base):
    """音频与算法关联模型 (Audio-Algorithm Relation)
    支持一个音频关联多个算法。

    P5: 跨域 relationship algorithm 移除（AlgorithmDefinition 归属 algorithm_service）。
    跨域查询算法定义改通过 algorithm_service gRPC。
    """
    __tablename__ = 'audio_algorithm_relations'
    __table_args__ = (
        Index('idx_audio_algorithm_audio', 'audio_id'),
        Index('idx_audio_algorithm_type', 'algorithm_type'),
        Index('uq_audio_algorithm', 'audio_id', 'algorithm_type',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    audio_id = Column(BigInteger, ForeignKey('audios.id'), nullable=False, comment='关联音频ID')
    algorithm_type = Column(String(50), nullable=False, comment='关联算法类型')
    is_primary = Column(Boolean, default=False, comment='是否主要算法')
    weight = Column(Float, default=1.0, comment='权重')
    params = Column(JSON, comment='算法特定参数')
    deleted = Column(Boolean, default=False, nullable=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')

    audio = relationship('Audio', foreign_keys='AudioAlgorithmRelation.audio_id', backref='algorithm_relations')

    def to_dict(self):
        return {
            'id': self.id,
            'audio_id': self.audio_id,
            'algorithm_type': self.algorithm_type,
            'is_primary': self.is_primary,
            'weight': self.weight,
            'params': self.params
        }


class AudioPlaybackHistory(Base):
    """音频播放历史模型 (Audio Playback History Model)
    记录音频文件的播放历史（INT-782#2：试听 preview 落点，播放时间/测试用例/播放设备/结果/时长）。
    """
    __tablename__ = 'audio_playback_history'
    __table_args__ = (
        Index('idx_aph_audio_played_at', 'audio_id', 'created_at'),
        Index('idx_aph_created_at', 'created_at'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    audio_id = Column(Integer, ForeignKey('audios.id'), nullable=False, comment='关联音频ID')
    testcase_id = Column(String(50), nullable=True, comment='关联测试用例ID（UUID，INT-782#2 返工；纯音频试听为空）')
    testcase_name = Column(String(255), nullable=True, comment='测试用例名称快照')
    device_id = Column(String(100), nullable=True, comment='播放设备标识快照（设备ID/唯一ID）')
    device_name = Column(String(255), nullable=False, comment='播放设备名称快照')
    result = Column(String(20), nullable=False, default='success', comment='播放结果 (success/failed)')
    duration = Column(Float, nullable=True, comment='播放时长（秒，音频时长快照）')
    source = Column(String(20), nullable=False, default='preview', comment='记录来源 (preview: 试听 / execution: 测试执行回放)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='触发播放的用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='播放时间/创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
