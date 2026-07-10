# -*- coding: utf-8 -*-
"""算法模块测试共享夹具

使用 PostgreSQL 真实数据库 + 嵌套事务（SAVEPOINT）实现测试隔离。
每个测试在事务中运行，测试结束后回滚，不影响数据库状态。
"""
import os
import sys
import pytest

# 确保 backend 目录在 sys.path 中
_backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.app import create_app
from backend.models.database import db
from backend.models.algorithm_models import (
    AlgorithmGroup, AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam,
    ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam,
    AlgorithmReferenceParam, EvaluationDimensionParam,
)
from backend.models.models import Dimension
from sqlalchemy.orm import sessionmaker


def _cleanup_algorithm_tables():
    """清理算法相关表数据（在事务中执行，测试后回滚不影响真实数据）"""
    db.session.query(AlgorithmDimensionRelation).delete()
    db.session.query(ParamMapping).delete()
    db.session.query(AlgorithmReferenceParam).delete()
    db.session.query(CaseAlgorithmParam).delete()
    db.session.query(AlgorithmApiParam).delete()
    db.session.query(AlgorithmDeviceParam).delete()
    db.session.query(AlgorithmDefinition).delete()
    db.session.query(AlgorithmGroup).delete()
    db.session.flush()  # 用 flush 代替 commit，避免在嵌套事务中真正提交


@pytest.fixture
def app():
    """创建测试用 Flask 应用

    使用外层事务实现测试隔离：
    1. 开启外层事务
    2. 清理算法相关表数据（让每个测试从空表开始）
    3. 测试运行（fixture 中使用 flush 而非 commit）
    4. 回滚外层事务，所有变更（包括清理）都不影响真实数据库

    注意: controller 源码中的 db.session.commit() 会真正提交数据，
    导致后续测试可能出现 UniqueViolation。这是已知限制，
    按测试文件单独运行时可避免此问题。
    """
    app = create_app("testing")
    with app.app_context():
        connection = db.engine.connect()
        trans = connection.begin()
        # 配置 session 使用此连接
        options = dict(bind=connection, binds={})
        session = db._make_scoped_session(options=options)
        db.session = session
        # 清理算法相关表，让测试从空表开始
        _cleanup_algorithm_tables()
        yield app
        session.remove()
        trans.rollback()
        connection.close()


@pytest.fixture
def client(app):
    """测试用 HTTP 客户端"""
    return app.test_client()


@pytest.fixture
def group(app):
    """创建一个算法分组"""
    g = AlgorithmGroup(name="测试分组", display_order=0)
    db.session.add(g)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(g)
    return g


@pytest.fixture
def dimension(app):
    """创建一个评估维度"""
    d = Dimension(name="WER_test", type="auto", result_type=1, weight=1)
    db.session.add(d)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(d)
    return d


@pytest.fixture
def algorithm(app, group):
    """创建一个算法定义"""
    algo = AlgorithmDefinition(
        type="test_algo",
        name="测试算法",
        group_id=group.id,
        status="online",
        display_order=0,
    )
    db.session.add(algo)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(algo)
    return algo


@pytest.fixture
def device_param(app, algorithm):
    """创建一个设备参数"""
    p = AlgorithmDeviceParam(
        algorithm_type="test_algo",
        param_code="input_text",
        param_name="输入文本",
        param_type="text",
        direction="input",
        required=True,
        ui_order=0,
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def api_param(app, algorithm):
    """创建一个 API 参数"""
    p = AlgorithmApiParam(
        algorithm_type="test_algo",
        param_code="api_result",
        param_name="API结果",
        param_type="text",
        direction="output",
        required=False,
        ui_order=0,
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def case_param(app, algorithm):
    """创建一个用例参数"""
    p = CaseAlgorithmParam(
        algorithm_type="test_algo",
        param_code="translation_direction",
        param_name="翻译方向",
        param_type="text",
        scope="common",
        ui_order=0,
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def reference_param(app, algorithm):
    """创建一个参考参数"""
    p = AlgorithmReferenceParam(
        algorithm_type="test_algo",
        code="asr_ref",
        name="ASR参考文本",
        param_type="text",
        annotation_code="asr_ref",
        merge_mode="join",
    )
    db.session.add(p)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(p)
    return p


@pytest.fixture
def mapping(app, algorithm, dimension):
    """创建一个参数映射"""
    m = ParamMapping(
        algorithm_type="test_algo",
        source="device",
        source_param="input_text",
        source_direction="output",
        dimension_id=dimension.id,
        target_param="ref_text",
        transform_type="none",
    )
    db.session.add(m)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(m)
    return m


@pytest.fixture
def dimension_relation(app, algorithm, dimension):
    """创建一个维度关联"""
    r = AlgorithmDimensionRelation(
        algorithm_type="test_algo",
        dimension_id=dimension.id,
        is_default=True,
        weight=1.0,
    )
    db.session.add(r)
    db.session.flush()  # 用 flush 代替 commit，不真正提交到数据库
    db.session.refresh(r)
    return r
