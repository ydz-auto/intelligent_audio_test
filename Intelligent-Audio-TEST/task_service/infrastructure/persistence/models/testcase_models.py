# -*- coding: utf-8 -*-
"""task_service 标签与测试用例 PO 定义

归属：task_service（测试用例上下文，Tag 隶属 TestCase）
表：tag_categories / tags / test_case_groups / test_cases / test_case_tags

P5 改造：从 shared/models/models/testcase_models.py 真正下沉到本服务。
shared/models/models/testcase_models.py 改为从这里 re-export。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean, JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship


class TagCategory(Base):
    """标签分类模型 (Tag Category Model)
    用于对标签进行分类管理，如人数、场景、语种等。
    """
    __tablename__ = 'tag_categories'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='分类唯一ID')
    name = Column(String(50), nullable=False, comment='分类名称')
    description = Column(Text, comment='分类描述')
    color = Column(String(20), comment='分类颜色标识 (Hex或名称)')
    sort_order = Column(Integer, default=0, comment='排序顺序 (数值越小越靠前)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')

    tags = relationship('Tag', foreign_keys='Tag.category_id', backref='category', lazy=True)


class Tag(Base):
    """通用标签模型 (Tag Model)
    可被应用于测试用例、设备、音频、任务等实体的通用标签。
    """
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='标签唯一ID')
    name = Column(String(50), nullable=False, comment='标签名称')
    description = Column(Text, comment='标签描述')
    color = Column(String(20), comment='标签颜色标识 (Hex或名称)')
    category_id = Column(Integer, ForeignKey('tag_categories.id'), comment='所属分类ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')


class TestCaseGroup(Base):
    """测试用例分组模型 (Test Case Group Model)
    用于对测试用例进行逻辑分类管理。
    """
    __tablename__ = 'test_case_groups'
    id = Column(String(50), primary_key=True, comment='分组唯一标识符')
    name = Column(String(100), nullable=False, comment='分组显示名称')
    description = Column(Text, comment='分组详细描述')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    test_cases = relationship('TestCase', foreign_keys='TestCase.group_id', backref='group', lazy=True)


class TestCase(Base):
    """测试用例模型 (Test Case Model)
    存储测试用例的核心配置信息，包括音频关联、背景噪音设置、算法配置等。
    """
    __tablename__ = 'test_cases'
    id = Column(String(50), primary_key=True, comment='用例唯一标识符')
    name = Column(String(150), nullable=False, comment='用例显示名称')
    description = Column(Text, comment='用例详细描述')
    config = Column(JSON, nullable=False, comment='用例结构性配置 (JSON)，含 rounds/dimensions/background_noise 等，不含算法参数和参考参数')
    algorithm_params = Column(JSON, comment='算法参数（按轮分组 [{round_number, params:[{field_code, field_value}]}]）')
    reference_params = Column(JSON, comment='参考参数路径（按轮分组 [{round_number, reference_params_path}]，内容存文件）')
    group_id = Column(String(50), ForeignKey('test_case_groups.id'), comment='所属分组ID')
    algorithm_type = Column(String(50), comment='关联算法类型 (如: translation, asr, speaker_recognition, tts)')
    test_type = Column(String(10), nullable=False, default='api', index=True, comment='测试类型 (api/e2e)')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')

    tags = relationship('Tag', secondary='test_case_tags',
        primaryjoin='TestCase.id == TestCaseTag.test_case_id',
        secondaryjoin='Tag.id == TestCaseTag.tag_id',
        backref='test_cases')


class TestCaseTag(Base):
    """测试用例标签关联模型 (Test Case-Tag Relation)
    维护测试用例与标签之间的多对多映射关系。
    """
    __tablename__ = 'test_case_tags'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    test_case_id = Column(String(50), comment='关联测试用例ID')
    tag_id = Column(BigInteger, comment='关联标签ID')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
