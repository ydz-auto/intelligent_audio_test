# -*- coding: utf-8 -*-
"""TestCase 聚合根 — 测试用例配置实体

TestCase 是测试用例上下文的聚合根，管理用例的配置信息、算法参数、
参考参数和标签关联。TestCase 是 Task 的输入数据，Task 通过 ID 引用 TestCase。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class TestCaseType(str, Enum):
    """测试类型"""
    API = "api"
    E2E = "e2e"


@dataclass
class CaseConfig:
    """用例配置值对象（rounds/dimensions/background_noise 等）"""
    rounds: int = 1
    dimensions: List[str] = field(default_factory=list)
    background_noise: Optional[Dict] = None

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "CaseConfig":
        if not data:
            return cls()
        return cls(
            rounds=data.get('rounds', 1),
            dimensions=data.get('dimensions', []),
            background_noise=data.get('background_noise'),
        )


@dataclass
class AlgorithmParam:
    """单轮算法参数"""
    round_number: int
    params: List[Dict] = field(default_factory=list)


@dataclass
class ReferenceParam:
    """单轮参考参数"""
    round_number: int
    reference_params_path: Optional[str] = None


@dataclass
class TestCaseSnapshot:
    """TestCase 快照值对象 — 用于 Task 引用 TestCase 时的配置快照"""
    case_id: str
    name: str
    algorithm_type: str
    test_type: str
    config: Optional[CaseConfig] = None
    algorithm_params: Optional[List[AlgorithmParam]] = None
    reference_params: Optional[List[ReferenceParam]] = None


@dataclass
class TestCaseEntity:
    """测试用例实体（非聚合根，聚合根是 TestCaseAggregate）"""
    id: str
    name: str
    description: Optional[str] = None
    algorithm_type: Optional[str] = None
    test_type: TestCaseType = TestCaseType.API
    group_id: Optional[str] = None


@dataclass
class TestCaseTagEntity:
    """用例-标签关联实体"""
    id: int
    test_case_id: str
    tag_id: int


@dataclass
class TestCaseGroupEntity:
    """用例分组实体"""
    id: str
    name: str
    description: Optional[str] = None
    algorithm_type: Optional[str] = None


@dataclass
class TagEntity:
    """标签实体"""
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    category_id: Optional[int] = None


@dataclass
class TagCategoryEntity:
    """标签分类实体"""
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0


@dataclass
class TestCaseAggregate:
    """TestCase 聚合根

    聚合测试用例的全部配置：基本信息、配置、算法参数、参考参数、标签。
    所有对用例的变更通过聚合根进行。
    """
    id: str
    name: str
    description: Optional[str] = None
    config: Optional[CaseConfig] = None
    algorithm_params: List[AlgorithmParam] = field(default_factory=list)
    reference_params: List[ReferenceParam] = field(default_factory=list)
    group_id: Optional[str] = None
    algorithm_type: Optional[str] = None
    test_type: TestCaseType = TestCaseType.API
    tags: List[TagEntity] = field(default_factory=list)

    @classmethod
    def create(cls, case_id: str, name: str, algorithm_type: str = "",
               test_type: str = "api", config: Optional[dict] = None,
               algorithm_params: Optional[list] = None,
               reference_params: Optional[list] = None,
               group_id: Optional[str] = None,
               description: Optional[str] = None) -> "TestCaseAggregate":
        return cls(
            id=case_id,
            name=name,
            description=description,
            config=CaseConfig.from_dict(config),
            algorithm_params=[
                AlgorithmParam(round_number=p.get('round_number', 0), params=p.get('params', []))
                for p in (algorithm_params or [])
            ],
            reference_params=[
                ReferenceParam(round_number=p.get('round_number', 0),
                               reference_params_path=p.get('reference_params_path'))
                for p in (reference_params or [])
            ],
            group_id=group_id,
            algorithm_type=algorithm_type,
            test_type=TestCaseType(test_type) if test_type else TestCaseType.API,
        )

    def to_snapshot(self) -> TestCaseSnapshot:
        """生成快照，供 Task 引用"""
        return TestCaseSnapshot(
            case_id=self.id,
            name=self.name,
            algorithm_type=self.algorithm_type or "",
            test_type=self.test_type.value,
            config=self.config,
            algorithm_params=self.algorithm_params,
            reference_params=self.reference_params,
        )

    def add_tag(self, tag: TagEntity) -> None:
        """添加标签"""
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag_id: int) -> None:
        """移除标签"""
        self.tags = [t for t in self.tags if t.id != tag_id]
