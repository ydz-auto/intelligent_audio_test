# -*- coding: utf-8 -*-
"""
算法配置数据模型

定义算法定义、设备参数、API参数、评估维度参数、参数映射等数据库模型

架构设计：
- AlgorithmDefinition: 算法定义
- AlgorithmDeviceParam: 设备参数（单算法专用）
- AlgorithmApiParam: API参数（单算法专用）
- EvaluationDimensionParam: 评估维度参数（多算法共用）
- ParamMapping: 参数映射（设备/API参数 → 评估维度参数）
- AlgorithmDimensionRelation: 算法与评估维度关联
"""

from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Float, ForeignKey, UniqueConstraint, DateTime, JSON
from sqlalchemy.orm import relationship
from .database import db


class AlgorithmGroup(db.Model):
    """算法分组表"""

    __tablename__ = 'algorithm_groups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, comment='分组名称')
    description = Column(Text, comment='分组描述')
    icon = Column(String(200), comment='图标URL')
    display_order = Column(Integer, default=0, comment='排序权重')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithms = relationship('AlgorithmDefinition', back_populates='group', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'display_order': self.display_order,
            'algorithm_count': self.algorithms.filter_by(deleted=False).count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AlgorithmDefinition(db.Model):
    """算法定义表"""

    __tablename__ = 'algorithm_definitions'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(String(50), unique=True, nullable=False, comment='算法类型代码')
    name = Column(String(100), nullable=False, comment='算法显示名称')
    group_id = Column(BigInteger, ForeignKey('algorithm_groups.id', ondelete='SET NULL'), comment='关联分组ID')
    description = Column(Text, comment='算法描述')
    status = Column(String(20), default='online', comment='状态：online, offline')
    icon = Column(String(200), comment='图标URL')
    display_order = Column(Integer, default=0, comment='排序权重')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    group = relationship('AlgorithmGroup', back_populates='algorithms')
    device_params = relationship('AlgorithmDeviceParam', back_populates='algorithm', cascade='all, delete-orphan')
    api_params = relationship('AlgorithmApiParam', back_populates='algorithm', cascade='all, delete-orphan')
    mappings = relationship('ParamMapping', back_populates='algorithm', cascade='all, delete-orphan')
    dimension_relations = relationship('AlgorithmDimensionRelation', back_populates='algorithm', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'name': self.name,
            'group_id': self.group_id,
            'group_name': self.group.name if self.group else None,
            'description': self.description,
            'status': self.status,
            'icon': self.icon,
            'display_order': self.display_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AlgorithmDeviceParam(db.Model):
    """设备参数定义表 - 单个算法专用"""

    __tablename__ = 'algorithm_device_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False, comment='关联算法类型')
    param_code = Column(String(50), nullable=False, comment='参数代码')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称（用于映射配置中的显示）')
    param_type = Column(String(30), nullable=False, comment='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction = Column(String(10), default='input', comment='方向：input, output')
    required = Column(Boolean, default=False, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON格式）')
    validation_rules = Column(Text, comment='验证规则（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='device_params')

    __table_args__ = (
        UniqueConstraint('algorithm_type', 'param_code', 'direction', name='uq_algorithm_device_param_direction'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'param_type': self.param_type,
            'direction': self.direction,
            'required': self.required,
            'default_value': self._parse_json(self.default_value),
            'validation': self._parse_json(self.validation_rules),
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'hidden': self.hidden
        }

    def _parse_json(self, json_str):
        if not json_str:
            return None
        try:
            import json
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


class AlgorithmApiParam(db.Model):
    """API参数定义表 - 单个算法专用"""

    __tablename__ = 'algorithm_api_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False, comment='关联算法类型')
    param_code = Column(String(50), nullable=False, comment='参数代码')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称（用于映射配置中的显示）')
    param_type = Column(String(30), nullable=False, comment='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction = Column(String(10), default='input', comment='方向：input, output')
    required = Column(Boolean, default=False, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON格式）')
    validation_rules = Column(Text, comment='验证规则（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='api_params')

    __table_args__ = (
        UniqueConstraint('algorithm_type', 'param_code', 'direction', name='uq_algorithm_api_param_direction'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'param_type': self.param_type,
            'direction': self.direction,
            'required': self.required,
            'default_value': self._parse_json(self.default_value),
            'validation': self._parse_json(self.validation_rules),
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'hidden': self.hidden
        }

    def _parse_json(self, json_str):
        if not json_str:
            return None
        try:
            import json
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


class AlgorithmReferenceParam(db.Model):
    """算法参考参数定义表 - 单个算法专用"""

    __tablename__ = 'algorithm_reference_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False, comment='关联算法类型')
    code = Column(String(50), nullable=False, comment='参数代码')
    name = Column(String(100), comment='参数显示名称')
    param_type = Column(String(30), default='text', comment='参考类型：text, audio, json, rttm, stm')
    annotation_code = Column(String(100), nullable=True, comment='关联的音频标注代码（匹配AudioAnnotation.code）')
    annotation_format = Column(String(20), nullable=True, comment='关联的音频标注格式（text/json/rttm/stm）')
    field_path = Column(String(255), nullable=True, comment='标注数据字段路径，如 model / segments[].emotion')
    merge_mode = Column(String(20), nullable=True, default='join', comment='多音频合并方式：join(空格拼接)/collect(收集数组)/first(取第一个)')
    help_text = Column(Text, comment='帮助提示文字')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    __table_args__ = (
        UniqueConstraint('algorithm_type', 'code', name='uq_algorithm_reference_param_code'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'code': self.code,
            'name': self.name,
            'type': self.param_type,
            'annotation_code': self.annotation_code,
            'annotation_format': self.annotation_format,
            'field_path': self.field_path,
            'merge_mode': self.merge_mode or 'join',
            'help_text': self.help_text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class EvaluationDimensionParam(db.Model):
    """评估维度参数定义表 - 多个算法共用"""

    __tablename__ = 'evaluation_dimension_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    dimension_id = Column(Integer, ForeignKey('dimensions.id', ondelete='CASCADE'), nullable=False, comment='关联评估维度ID')
    param_code = Column(String(50), nullable=False, comment='参数代码（评估API需要的字段名）')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称')
    field_type = Column(String(20), default='text', comment='字段类型：text, audio, number, boolean, json')
    required = Column(Boolean, default=True, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    dimension = relationship('Dimension')

    __table_args__ = (
        UniqueConstraint('dimension_id', 'param_code', name='uq_dimension_param_code'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'dimension_id': self.dimension_id,
            'dimension_name': self.dimension.name if self.dimension else None,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'field_type': self.field_type,
            'required': self.required,
            'default_value': self._parse_json(self.default_value),
            'help_text': self.help_text,
            'ui_order': self.ui_order
        }

    def _parse_json(self, json_str):
        if not json_str:
            return None
        try:
            import json
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


class ParamMapping(db.Model):
    """参数映射表 - 设备/API/用例参数 → 评估维度参数"""

    __tablename__ = 'param_mappings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False, comment='关联算法类型')
    source = Column(String(20), nullable=False, default='api', comment='参数来源：case=用例参数, reference=参考参数, device=设备输出, api=API输出')
    source_param = Column(String(50), nullable=False, comment='源参数代码')
    source_direction = Column(String(10), default='output', comment='源参数方向：input, output')
    dimension_id = Column(Integer, ForeignKey('dimensions.id', ondelete='CASCADE'), nullable=True, comment='目标评估维度ID(可为空)')
    target_param = Column(String(50), nullable=False, comment='目标评估维度参数代码')
    transform_type = Column(String(20), default='none', comment='转换类型：none, uppercase, lowercase, json_parse, base64')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='mappings')
    dimension = relationship('Dimension')

    __table_args__ = (
        UniqueConstraint('algorithm_type', 'source', 'source_param', 'dimension_id', name='uq_algorithm_source_to_dimension'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'source': self.source,
            'source_param': self.source_param,
            'source_direction': self.source_direction,
            'dimension_id': self.dimension_id,
            'dimension_name': self.dimension.name if self.dimension else None,
            'target_param': self.target_param,
            'transform_type': self.transform_type
        }


class AlgorithmDimensionRelation(db.Model):
    """评估维度与算法关联表"""

    __tablename__ = 'algorithm_dimension_relations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False, comment='关联算法类型')
    dimension_id = Column(Integer, ForeignKey('dimensions.id', ondelete='CASCADE'), nullable=False, comment='关联评估维度ID')
    is_default = Column(Boolean, default=False, comment='是否默认评估维度')
    weight = Column(Float, default=1.0, comment='权重')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='dimension_relations')
    dimension = relationship('Dimension')

    __table_args__ = (
        UniqueConstraint('algorithm_type', 'dimension_id', name='uq_algorithm_dimension'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'dimension_id': self.dimension_id,
            'dimension_name': self.dimension.name if self.dimension else None,
            'is_default': self.is_default,
            'weight': self.weight
        }


class CaseAlgorithmParam(db.Model):
    """用例专属参数定义表 - 特定算法专用"""

    __tablename__ = 'case_algorithm_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type', ondelete='CASCADE'), nullable=False, comment='关联算法类型')
    param_code = Column(String(50), nullable=False, comment='参数代码')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称')
    param_type = Column(String(20), nullable=False, comment='参数类型：select, text, number, textarea, slider, switch')
    required = Column(Boolean, default=False, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON格式）')
    options_source = Column(String(50), comment='选项来源')
    options_field = Column(String(50), comment='选项值字段')
    options_label_field = Column(String(50), comment='选项显示字段')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    scope = Column(String(10), nullable=False, default='common', comment='参数适用范围 (common/api/e2e)')
    min_value = Column(Float, nullable=True, comment='最小值 (slider/number)')
    max_value = Column(Float, nullable=True, comment='最大值 (slider/number)')
    step = Column(Float, nullable=True, comment='步长 (slider/number)')
    unit = Column(String(20), nullable=True, comment='单位显示 (如 cm, dB, s)')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition')

    __table_args__ = (
        UniqueConstraint('algorithm_type', 'param_code', name='uq_case_algorithm_param_code'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'param_type': self.param_type,
            'required': self.required,
            'default_value': self._parse_json(self.default_value),
            'options_source': self.options_source,
            'options_field': self.options_field,
            'options_label_field': self.options_label_field,
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'hidden': self.hidden,
            'scope': self.scope,
            'min': self.min_value,
            'max': self.max_value,
            'step': self.step,
            'unit': self.unit
        }

    def _parse_json(self, json_str):
        if not json_str:
            return None
        try:
            import json
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


class Language(db.Model):
    """语言表 - 存储系统支持的语言"""

    __tablename__ = 'languages'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, unique=True, comment='语言代码 (如 zh, en, ja)')
    name = Column(String(50), nullable=False, comment='语言名称 (如 中文, 英语, 日语)')
    name_en = Column(String(50), comment='语言英文名称 (如 Chinese, English, Japanese)')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'name_en': self.name_en,
            'deleted': self.deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
