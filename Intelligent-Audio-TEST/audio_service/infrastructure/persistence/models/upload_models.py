# -*- coding: utf-8 -*-
"""audio_service 文件上传 PO 定义

归属：audio_service（e2e 测试上下文，音频上传所有权）
表：upload_tasks / upload_files / upload_chunks

P5 改造：从 shared/models/models/upload_models.py 真正下沉到本服务。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship


class UploadTask(Base):
    """上传任务模型 (Upload Task Model)
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
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    expired_at = Column(DateTime, comment='任务过期时间')

    files = relationship('UploadFile', foreign_keys='UploadFile.task_id', backref='task', cascade="all, delete-orphan")


class UploadFile(Base):
    """上传文件模型 (Upload File Model)
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
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    chunks = relationship('UploadChunk', foreign_keys='UploadChunk.file_id', backref='file', cascade="all, delete-orphan")


class UploadChunk(Base):
    """上传分片模型 (Upload Chunk Model)
    存储单个文件分片的上传信息
    """
    __tablename__ = 'upload_chunks'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='分片唯一ID')
    file_id = Column(String(50), ForeignKey('upload_files.id'), comment='关联上传文件ID')
    chunk_index = Column(Integer, nullable=False, comment='分片索引')
    chunk_size = Column(Integer, nullable=False, comment='分片大小 (字节)')
    md5 = Column(String(32), comment='分片MD5值')
    status = Column(String(20), nullable=False, default='pending', comment='分片状态 (pending/uploading/completed/failed)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    stored_path = Column(String(500), comment='分片存储路径')
