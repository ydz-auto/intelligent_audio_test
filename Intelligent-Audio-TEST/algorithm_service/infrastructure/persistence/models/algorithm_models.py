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
import json
from datetime import datetime

from shared.models.common_enums import CaseParamScope
from shared.models.database import Base
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, Boolean, Float,
    DateTime, JSON, ForeignKey, Index, text,
)
from sqlalchemy.orm import relationship

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
# （对齐 task_service favorite_models 的 _PK_BIGINT 口径，INT-299）
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


def parse_json_or_raw(value):
    """JSON 文本字段宽松读取（INT-222 统一语义）。

    - 空值（None / ''）返回 None
    - 合法 JSON 形态（'{"k":1}' / '[1,2]' / '42'）解析为对象
    - 解析失败（非 JSON 纯文本如 'zh'、截断 JSON）返回原始字符串，不吞成 None
    """
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


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
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID（INT-299）')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID（INT-299）')
    deleted_by_user_id = Column(BigInteger, nullable=True, comment='执行删除操作的用户ID（JWT，INT-299）')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

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
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True)
    type = Column(String(50), unique=True, nullable=False, comment='算法类型代码')
    name = Column(String(100), nullable=False, comment='算法显示名称')
    group_id = Column(BigInteger, ForeignKey('algorithm_groups.id'), comment='关联分组ID')
    description = Column(Text, comment='算法描述')
    status = Column(String(20), default='online', comment='状态：online, offline')
    icon = Column(String(200), comment='图标URL')
    display_order = Column(Integer, default=0, comment='排序权重')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID（INT-299）')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID（INT-299）')
    deleted_by_user_id = Column(BigInteger, nullable=True, comment='执行删除操作的用户ID（JWT，INT-299）')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

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
        Index('uq_algorithm_device_param_algo_level',
              'algorithm_type', 'param_code', 'direction', unique=True,
              postgresql_where=text('deleted = false AND device_id IS NULL')),
        Index('uq_algorithm_device_param_device_level',
              'algorithm_type', 'device_id', 'param_code', 'direction', unique=True,
              postgresql_where=text('deleted = false AND device_id IS NOT NULL')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
    # 设备级作用域：指向 device_service 的 devices.id（不建跨服务 FK）。
    # NULL = 算法类型级默认；合并读取时设备级行覆盖同键算法级行。
    device_id = Column(Integer, nullable=True, comment='设备ID（NULL=算法类型级默认）')
    param_code = Column(String(50), nullable=False, comment='参数代码')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称（用于映射配置中的显示）')
    param_type = Column(String(30), nullable=False, comment='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction = Column(String(10), default='input', comment='方向：input, output')
    required = Column(Boolean, default=False, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON 或纯文本）')
    validation_rules = Column(Text, comment='验证规则（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='device_params', foreign_keys='AlgorithmDeviceParam.algorithm_type')

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'device_id': self.device_id,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'param_type': self.param_type,
            'direction': self.direction,
            'required': self.required,
            'default_value': parse_json_or_raw(self.default_value),
            'validation': parse_json_or_raw(self.validation_rules),
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'hidden': self.hidden
        }


class AlgorithmApiParam(Base):
    """API参数定义表 - 单个算法专用"""
    __tablename__ = 'algorithm_api_params'
    __table_args__ = (
        Index('uq_algorithm_api_param_direction', 'algorithm_type', 'param_code', 'direction',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
    # INT-1756（C6a）：API 实例级作用域，指向 api_test_service 的 apis.id。
    # 不建 ForeignKey：apis 归 api_test_service，跨服务 DB 约束违反架构红线；
    # 存在性与算法类型一致性由网关写路径校验。NULL = 算法类型级默认。
    api_id = Column(Integer, nullable=True, comment='API 实例ID（NULL=算法类型级默认）')
    param_code = Column(String(50), nullable=False, comment='参数代码')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称（用于映射配置中的显示）')
    param_type = Column(String(30), nullable=False, comment='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction = Column(String(10), default='input', comment='方向：input, output')
    required = Column(Boolean, default=False, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON 或纯文本）')
    validation_rules = Column(Text, comment='验证规则（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    field_path = Column(String(255), comment='输出字段取值路径（点号 + 数组下标，如 data.events[0].text；空 = 按 param_code 取顶层键）')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='api_params', foreign_keys='AlgorithmApiParam.algorithm_type')

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'api_id': self.api_id,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'param_type': self.param_type,
            'direction': self.direction,
            'required': self.required,
            'default_value': parse_json_or_raw(self.default_value),
            'validation': parse_json_or_raw(self.validation_rules),
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'hidden': self.hidden,
            'field_path': self.field_path,
        }


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
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

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
    default_value = Column(Text, comment='默认值（JSON 或纯文本）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    pass_threshold = Column(Float, nullable=True, comment='评估通过阈值（agg_role=pass_le/pass_ge/pass_eq 时使用）')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

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
            'default_value': parse_json_or_raw(self.default_value),
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'pass_threshold': self.pass_threshold
        }


class ParamMapping(Base):
    """参数映射表 - 设备/API/用例参数 → 评估维度参数"""
    __tablename__ = 'param_mappings'
    __table_args__ = (
        Index('uq_param_mapping_algo_level', 'algorithm_type', 'source',
              'source_param', 'dimension_id', unique=True,
              postgresql_where=text(
                  'deleted = false AND api_id IS NULL AND device_id IS NULL')),
        Index('uq_param_mapping_api_level', 'algorithm_type', 'api_id', 'source',
              'source_param', 'dimension_id', unique=True,
              postgresql_where=text(
                  'deleted = false AND api_id IS NOT NULL AND device_id IS NULL')),
        Index('uq_param_mapping_device_level', 'algorithm_type', 'device_id', 'source',
              'source_param', 'dimension_id', unique=True,
              postgresql_where=text('deleted = false AND device_id IS NOT NULL')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), ForeignKey('algorithm_definitions.type'), nullable=False, comment='关联算法类型')
    # INT-1756（C6a）：API 实例级作用域，指向 api_test_service 的 apis.id（不建跨服务 FK）。
    # NULL = 算法类型级默认；合并读取时 API 级行覆盖同键算法级行。
    api_id = Column(Integer, nullable=True, comment='API 实例ID（NULL=算法类型级默认）')
    # 设备级作用域：指向 device_service 的 devices.id（不建跨服务 FK）。
    # NULL = 算法类型级默认；合并读取时设备级行覆盖同键算法级行（优先于 api 级）。
    device_id = Column(Integer, nullable=True, comment='设备ID（NULL=算法类型级默认）')
    source = Column(String(20), nullable=False, default='api', comment='参数来源：case=用例参数, reference=参考参数, device=设备输出, api=API输出')
    source_param = Column(String(50), nullable=False, comment='源参数代码')
    source_direction = Column(String(10), default='output', comment='源参数方向：input, output')
    dimension_id = Column(Integer, nullable=True, comment='目标评估维度ID(可为空)')
    target_param = Column(String(50), nullable=False, comment='目标评估维度参数代码')
    transform_type = Column(String(20), default='none', comment='转换类型：none, uppercase, lowercase, json_parse, base64')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    algorithm = relationship('AlgorithmDefinition', back_populates='mappings', foreign_keys='ParamMapping.algorithm_type')
    # P5: 跨域 relationship dimension 移除（Dimension 归属 evaluation_service）

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'api_id': self.api_id,
            'device_id': self.device_id,
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
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

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
    default_value = Column(Text, comment='默认值（JSON 或纯文本）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    scope = Column(String(20), nullable=False, default=CaseParamScope.COMMON.value,
                   comment='参数适用范围 (common/physical/http_api/websocket_api)')
    min_value = Column(Float, nullable=True, comment='最小值 (slider/number)')
    max_value = Column(Float, nullable=True, comment='最大值 (slider/number)')
    step = Column(Float, nullable=True, comment='步长 (slider/number)')
    unit = Column(String(20), nullable=True, comment='单位显示 (如 cm, dB, s)')
    annotation_code = Column(String(100), nullable=True, comment='关联的音频标注代码，默认同 param_code')
    field_path = Column(String(255), nullable=True, comment='标注数据字段路径，默认同 param_code')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

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
            'default_value': parse_json_or_raw(self.default_value),
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


class AlgorithmDefinitionDraft(Base):
    """算法定义草稿表（INT-589 草稿存储模型）。

    仅 1 表、JSON 快照：30s 自动保存写快照、恢复时物化、显式发布才写正式
    六表（algorithm_definitions + 5 张子表）。依据：
    - algorithm_definitions.type 全表唯一，草稿与已发布同 type 无法共存；
    - config_cache 只加载 online，同行置 draft 会让执行链路失服；
    - INT-582/585 编辑模态窗针对已发布算法，自动保存草稿必须与线上版本分离。

    只按 algorithm_type 存一份快照（upsert），不做版本历史。
    snapshot 为完整定义 JSON（与 SaveAlgorithmDefinitionRequest.data 同构，
    含基础字段 + 六类子实体），恢复时整体物化为正式六表。
    """
    __tablename__ = 'algorithm_definition_drafts'
    __table_args__ = (
        Index('uq_algorithm_definition_draft_type', 'algorithm_type', unique=True),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    algorithm_type = Column(String(50), nullable=False, comment='算法类型代码（草稿唯一键）')
    snapshot = Column(Text, comment='完整定义 JSON 快照（INT-589）')
    created_by_user_id = Column(BigInteger, nullable=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'algorithm_type': self.algorithm_type,
            'snapshot': parse_json_or_raw(self.snapshot),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ParamProfile(Base):
    """参数策略（可复用的字段声明 + 映射模板）。

    API 参数与映射从「算法类型级默认（api_id IS NULL）」改为「显式命名策略」：
    - ``scope='api'``：由 API 实例经 ``api_param_bindings`` 引用（绑定点归本服务，
      运行时解析不必跨服务查 ``apis``）；
    - ``scope='device'``：预留（物理侧按驱动标识 ``(system, keywords)`` 绑定，
      本轮不接线）。
    多个实例引用同一策略即共享同一份声明，差异只在实例覆盖行里表达。

    ``cloned_from`` 记录来源策略 id，仅作血缘展示，不参与任何解析。
    """
    __tablename__ = 'param_profiles'
    __table_args__ = (
        Index('uq_param_profile_scope_type_name', 'scope', 'algorithm_type', 'name',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(10), nullable=False, default='api', comment='作用域：api / device')
    algorithm_type = Column(String(50), nullable=False, comment='关联算法类型')
    name = Column(String(100), nullable=False, comment='策略名称（同作用域+算法类型内唯一）')
    description = Column(Text, comment='策略描述')
    status = Column(String(20), nullable=False, default='online', comment='状态：online / offline / draft')
    cloned_from = Column(Integer, nullable=True, comment='来源策略ID（仅血缘记录）')
    # API 配置快照（JSON 文本）：协议/流式性/请求模板/响应解析/音频格式/厂商适配器 等
    # 「与端点地址无关」的配置项；新建 API 时可整体套用（复制/覆盖）。
    config_snapshot = Column(Text, comment='API 配置快照（JSON）')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    # 子表按 profile_id 显式查询（跨表无 FK，DTO 不暴露关系），不建 ORM relationship

    def to_dict(self):
        return {
            'id': self.id,
            'scope': self.scope,
            'algorithm_type': self.algorithm_type,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'cloned_from': self.cloned_from,
            'config': parse_json_or_raw(self.config_snapshot),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ParamProfileParam(Base):
    """策略字段声明（与 algorithm_api_params 字段同构）。"""
    __tablename__ = 'param_profile_params'
    __table_args__ = (
        Index('uq_param_profile_param_key', 'profile_id', 'param_code', 'direction',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, nullable=False, comment='关联策略ID')
    param_code = Column(String(50), nullable=False, comment='参数代码')
    param_name = Column(String(100), comment='参数显示名称')
    label = Column(String(100), comment='字段显示名称')
    param_type = Column(String(30), nullable=False, comment='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction = Column(String(10), default='input', comment='方向：input, output')
    required = Column(Boolean, default=False, comment='是否必填')
    default_value = Column(Text, comment='默认值（JSON 或纯文本）')
    validation_rules = Column(Text, comment='验证规则（JSON格式）')
    help_text = Column(Text, comment='帮助提示文字')
    ui_order = Column(Integer, default=0, comment='界面排序')
    hidden = Column(Boolean, default=False, comment='是否隐藏')
    field_path = Column(String(255), comment='输出字段取值路径（空 = 按 param_code 取顶层键）')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'profile_id': self.profile_id,
            'param_code': self.param_code,
            'param_name': self.param_name,
            'label': self.label,
            'param_type': self.param_type,
            'direction': self.direction,
            'required': self.required,
            'default_value': parse_json_or_raw(self.default_value),
            'validation': parse_json_or_raw(self.validation_rules),
            'help_text': self.help_text,
            'ui_order': self.ui_order,
            'hidden': self.hidden,
            'field_path': self.field_path,
        }


class ParamProfileMapping(Base):
    """策略参数映射（API 输出 → 评估维度参数），与 param_mappings 同构。"""
    __tablename__ = 'param_profile_mappings'
    __table_args__ = (
        Index('uq_param_profile_mapping_key', 'profile_id', 'source', 'source_param',
              'dimension_id', unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, nullable=False, comment='关联策略ID')
    source = Column(String(20), nullable=False, default='api', comment='参数来源：case / reference / device / api / case_config')
    source_param = Column(String(50), nullable=False, comment='源参数代码')
    source_direction = Column(String(10), default='output', comment='源参数方向：input, output')
    dimension_id = Column(Integer, nullable=True, comment='目标评估维度ID')
    target_param = Column(String(50), nullable=False, comment='目标评估维度参数代码')
    transform_type = Column(String(20), default='none', comment='转换类型：none, uppercase, lowercase, json_parse, base64')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'profile_id': self.profile_id,
            'source': self.source,
            'source_param': self.source_param,
            'source_direction': self.source_direction,
            'dimension_id': self.dimension_id,
            'target_param': self.target_param,
            'transform_type': self.transform_type,
        }


class ApiParamBinding(Base):
    """API 实例 → 参数策略绑定。

    绑定归 algorithm_service 所有：运行时按 ``api_id`` 解析策略不需要跨服务读
    ``apis``，也避免 ``apis.param_profile_id`` 列与本表形成双写。

    ``api_id`` 指向 api_test_service 的 ``apis.id``，跨服务不建 DB 外键；
    存在性与算法类型一致性由网关写路径校验。
    """
    __tablename__ = 'api_param_bindings'
    __table_args__ = (
        Index('uq_api_param_binding_api', 'api_id',
              unique=True, postgresql_where=text('deleted = false')),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_id = Column(Integer, nullable=False, comment='API 实例ID（apis.id）')
    profile_id = Column(Integer, nullable=False, comment='关联策略ID')
    deleted = Column(Boolean, default=False, comment='逻辑删除标志')
    created_at = Column(DateTime, default=datetime.now, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'api_id': self.api_id,
            'profile_id': self.profile_id,
        }
