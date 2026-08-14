# -*- coding: utf-8 -*-
"""algorithm_service 算法配置 PO 定义

归属：algorithm_service（算法定义 + 参数映射上下文）
表：algorithm_groups / algorithm_definitions / algorithm_device_params
     / algorithm_api_params / algorithm_reference_params
     / evaluation_dimension_params / param_mappings
     / algorithm_dimension_relations / case_algorithm_params

P5 改造：从 shared/models/algorithm_models.py 真正下沉到本服务。
shared/models/algorithm_models.py 改为从这里 re-export。

关键决策：移除跨域 relationship 到 `Dimension`（归属 evaluation_service）。
- EvaluationDimensionParam.dimension / ParamMapping.dimension /
  AlgorithmDimensionRelation.dimension 三个跨域 relationship 全部移除
- 跨域查询 Dimension 改通过 evaluation_service.EvaluationConfigService.GetDimensionByIds gRPC 调用
- 保留 AlgorithmDefinition 的同域 relationship（device_params/api_params/mappings/dimension_relations）
"""
from datetime import datetime

from shared.models.database import Base
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Float,
    DateTime, JSON, ForeignKey, Index, text,
)
from sqlalchemy.orm import relationship


class AlgorithmGroup(Base):
    """算法分组表"""
    __tablename__ = 'algorithm_groups'
    __table_args__ = (
        Index('uq_algorithm_group_name', 'name', unique=True,
              postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment='分组名称')
    description = Column(Text, comment='分组描述')
    icon = Column(String(200), comment='图标URL')
    display_order = Column(Integer, default=0, comment='排序权重')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithms = relationship('AlgorithmDefinition', back_populates='group', lazy='dynamic', foreign_keys='AlgorithmDefinition.group_id')

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


class AlgorithmDefinition(Base):
    """算法定义表"""
    __tablename__ = 'algorithm_definitions'
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(String(50), unique=True, nullable=False, comment='算法类型代码')
    name = Column(String(100), nullable=False, comment='算法显示名称')
    group_id = Column(BigInteger, ForeignKey('algorithm_groups.id'), comment='关联分组ID')
    description = Column(Text, comment='算法描述')
    status = Column(String(20), default='online', comment='状态：online, offline')
    icon = Column(String(200), comment='图标URL')
    display_order = Column(Integer, default=0, comment='排序权重')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    group = relationship('AlgorithmGroup', back_populates='algorithms', foreign_keys='AlgorithmDefinition.group_id')
    device_params = relationship('AlgorithmDeviceParam', back_populates='algorithm', cascade='all, delete-orphan', foreign_keys='AlgorithmDeviceParam.algorithm_type')
    api_params = relationship('AlgorithmApiParam', back_populates='algorithm', cascade='all, delete-orphan', foreign_keys='AlgorithmApiParam.algorithm_type')
    mappings = relationship('ParamMapping', back_populates='algorithm', cascade='all, delete-orphan', foreign_keys='ParamMapping.algorithm_type')
    dimension_relations = relationship('AlgorithmDimensionRelation', back_populates='algorithm', cascade='all, delete-orphan', foreign_keys='AlgorithmDimensionRelation.algorithm_type')

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


class AlgorithmDeviceParam(Base):
    """设备参数定义表 - 单个算法专用"""
    __tablename__ = 'algorithm_device_params'
    __table_args__ = (
        Index('uq_algorithm_device_param_direction', 'algorithm_type', 'param_code', 'direction',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
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

    algorithm = relationship('AlgorithmDefinition', back_populates='device_params', foreign_keys='AlgorithmDeviceParam.algorithm_type')

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


class AlgorithmApiParam(Base):
    """API参数定义表 - 单个算法专用"""
    __tablename__ = 'algorithm_api_params'
    __table_args__ = (
        Index('uq_algorithm_api_param_direction', 'algorithm_type', 'param_code', 'direction',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
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

    algorithm = relationship('AlgorithmDefinition', back_populates='api_params', foreign_keys='AlgorithmApiParam.algorithm_type')

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


class AlgorithmReferenceParam(Base):
    """算法参考参数定义表 - 单个算法专用"""
    __tablename__ = 'algorithm_reference_params'
    __table_args__ = (
        Index('uq_algorithm_reference_param_code', 'algorithm_type', 'code',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), nullable=False, comment='关联算法类型')
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


class EvaluationDimensionParam(Base):
    """评估维度参数定义表 - 多个算法共用"""
    __tablename__ = 'evaluation_dimension_params'
    __table_args__ = (
        Index('uq_dimension_param_code_direction', 'dimension_id', 'param_code', 'param_direction',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    dimension_id = Column(Integer, nullable=False, comment='关联评估维度ID')
    param_code = Column(String(50), nullable=False, comment='参数代码（评估API需要的字段名）')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称')
    field_type = Column(String(20), default='text', comment='字段类型：text, audio, number, boolean, json')
    param_direction = Column(String(10), nullable=False, default='input', comment='参数方向：input(输入参数), output(结果提取字段)')
    field_path = Column(String(200), nullable=True, comment='结果提取路径（output专用，如 wer 或 data.result.wer）')
    agg_role = Column(String(20), nullable=True, comment='聚合角色（output专用）：numerator(分子), denominator(分母), value(直接值)')
    output_role = Column(String(10), nullable=True, comment='输出字段角色（output专用）：main(主结果), aux(辅助字段)')
    visible_in_report = Column(Boolean, default=True, comment='是否在报告中显示该字段')
    required = Column(Boolean, default=True, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # P5: 跨域 relationship dimension 移除（Dimension 归属 evaluation_service）
    # 跨域查询 Dimension 改通过 evaluation_service.EvaluationConfigService.GetDimensionByIds gRPC

    def to_dict(self):
        return {
            'id': self.id,
            'dimension_id': self.dimension_id,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'field_type': self.field_type,
            'param_direction': self.param_direction,
            'field_path': self.field_path,
            'agg_role': self.agg_role,
            'output_role': self.output_role,
            'visible_in_report': self.visible_in_report if self.visible_in_report is not None else True,
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


class ParamMapping(Base):
    """参数映射表 - 设备/API/用例参数 → 评估维度参数"""
    __tablename__ = 'param_mappings'
    __table_args__ = (
        Index('uq_algorithm_source_to_dimension', 'algorithm_type', 'source', 'source_param', 'dimension_id',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
    source = Column(String(20), nullable=False, default='api', comment='参数来源：case=用例参数, reference=参考参数, device=设备输出, api=API输出')
    source_param = Column(String(50), nullable=False, comment='源参数代码')
    source_direction = Column(String(10), default='output', comment='源参数方向：input, output')
    dimension_id = Column(Integer, nullable=True, comment='目标评估维度ID(可为空)')
    target_param = Column(String(50), nullable=False, comment='目标评估维度参数代码')
    transform_type = Column(String(20), default='none', comment='转换类型：none, uppercase, lowercase, json_parse, base64')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='mappings', foreign_keys='ParamMapping.algorithm_type')
    # P5: 跨域 relationship dimension 移除（Dimension 归属 evaluation_service）

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'source': self.source,
            'source_param': self.source_param,
            'source_direction': self.source_direction,
            'dimension_id': self.dimension_id,
            'target_param': self.target_param,
            'transform_type': self.transform_type
        }


class AlgorithmDimensionRelation(Base):
    """评估维度与算法关联表"""
    __tablename__ = 'algorithm_dimension_relations'
    __table_args__ = (
        Index('uq_algorithm_dimension', 'algorithm_type', 'dimension_id',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
    dimension_id = Column(Integer, nullable=False, comment='关联评估维度ID')
    is_default = Column(Boolean, default=False, comment='是否默认评估维度')
    weight = Column(Float, default=1.0, comment='权重')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='dimension_relations', foreign_keys='AlgorithmDimensionRelation.algorithm_type')
    # P5: 跨域 relationship dimension 移除（Dimension 归属 evaluation_service）

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'dimension_id': self.dimension_id,
            'is_default': self.is_default,
            'weight': self.weight
        }


class CaseAlgorithmParam(Base):
    """用例专属参数定义表 - 特定算法专用"""
    __tablename__ = 'case_algorithm_params'
    __table_args__ = (
        Index('uq_case_algorithm_param_code', 'algorithm_type', 'param_code',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
    param_code = Column(String(50), nullable=False, comment='参数代码')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称')
    param_type = Column(String(20), nullable=False, comment='参数类型：text, number, textarea, slider, switch, audio_select, device_select, json')
    required = Column(Boolean, default=False, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    scope = Column(String(10), nullable=False, default='common', comment='参数适用范围 (common/api/e2e)')
    min_value = Column(Float, nullable=True, comment='最小值 (slider/number)')
    max_value = Column(Float, nullable=True, comment='最大值 (slider/number)')
    step = Column(Float, nullable=True, comment='步长 (slider/number)')
    unit = Column(String(20), nullable=True, comment='单位显示 (如 cm, dB, s)')
    annotation_code = Column(String(100), nullable=True, comment='关联的音频标注代码，默认同 param_code')
    field_path = Column(String(255), nullable=True, comment='标注数据字段路径，默认同 param_code')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', foreign_keys='CaseAlgorithmParam.algorithm_type')

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
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'hidden': self.hidden,
            'scope': self.scope,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'step': self.step,
            'unit': self.unit,
            'annotation_code': self.annotation_code,
            'field_path': self.field_path
        }

    def _parse_json(self, json_str):
        if not json_str:
            return None
        try:
            import json
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
