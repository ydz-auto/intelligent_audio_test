"""
评估维度管理模型 (Evaluation Dimension Management)

包含评估分类和评估维度模型，支持主维度-子维度层级关系。
"""
from ._base import (
    db, Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON,
    relationship, utc8now,
)


# 9. 评估维度管理 (Evaluation Dimension Management)

class Category(db.Model):
    """
    评估分类模型 (Category Model)
    用于对评估维度进行大类划分（如 准确性、流畅度、响应速度）。
    """
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='分类唯一ID')
    name = Column(String(100), nullable=False, comment='分类名称')
    description = Column(Text, comment='分类详细描述')
    icon = Column(String(50), nullable=False, comment='分类图标标识')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')

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
    parent_dimension_id = Column(Integer, nullable=True, comment='主维度ID')
    task_type_code = Column(String(50), nullable=True, comment='API调用的task_type值（如 wer）')
    description = Column(Text, comment='维度详细描述')
    category_id = Column(Integer, comment='所属分类ID')
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
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')
    api_status = Column(String(20), nullable=False, default='online', comment='算法 API 在线状态')
    api_endpoints = Column(JSON, nullable=True, default=list, comment='多个评估算法 API 地址及配置')
    api_url = Column(String(512), comment='评估微服务主入口URL')
    score_unit = Column(String(50), nullable=True, default='', comment='分数单位')
    statistic_method = Column(String(30), nullable=False, default='average', comment='统计方式: average(简单平均), weighted_wer(加权WER: Σerrors/Σlength)')

    parent_dimension = relationship('Dimension', remote_side=[id], foreign_keys='Dimension.parent_dimension_id', backref='sub_dimensions')
