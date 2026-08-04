"""
音频文件管理模型 (Audio Management)

包含音频文件、音频标注、音频-标签关联、音频-算法关联模型。
"""
from ._base import (
    db, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    Index, UniqueConstraint, relationship, utc8now,
)


# 5. 音频文件管理 (Audio Management)

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
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    source_language = Column(String(32), comment='源语言')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
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
    audio_id = Column(Integer, nullable=False, comment='关联音频ID')
    format = Column(String(20), nullable=False, comment='标注格式 (text/json/rttm/stm)')
    code = Column(String(255), comment='标注代码/名称')
    data = Column(JSON, nullable=False, comment='标注数据内容')
    source_language = Column(String(20), comment='源语言代码')
    target_language = Column(String(20), comment='目标语言代码')
    deleted = Column(Boolean, default=False, nullable=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    audio = relationship('Audio', foreign_keys='AudioAnnotation.audio_id', backref='annotations')

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
    audio_id = Column(Integer, comment='关联音频ID')
    tag_id = Column(Integer, comment='关联标签ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
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
    audio_id = Column(BigInteger, nullable=False, comment='关联音频ID')
    algorithm_type = Column(String(50), nullable=False, comment='关联算法类型')
    is_primary = Column(Boolean, default=False, comment='是否主要算法')
    weight = Column(Float, default=1.0, comment='权重')
    params = Column(JSON, comment='算法特定参数')
    deleted = Column(Boolean, default=False, nullable=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    audio = relationship('Audio', foreign_keys='AudioAlgorithmRelation.audio_id', backref='algorithm_relations')
    algorithm = relationship('AlgorithmDefinition', foreign_keys='AudioAlgorithmRelation.algorithm_type')

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
