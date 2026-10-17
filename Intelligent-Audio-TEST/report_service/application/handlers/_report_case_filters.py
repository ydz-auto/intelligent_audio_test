# -*- coding: utf-8 -*-
"""报告用例过滤公共函数（从 report_handlers.py 拆分，P4-5）。

TestResult / TestCase 客户端过滤辅助：分组名 / 标签提取与过滤循环。
dict 与对象两种载荷形态统一兼容。
"""
from typing import Any, Dict, List, Optional


def tc_group_name(tc) -> Optional[str]:
    """提取用例的分组名（兼容 dict / 对象载荷）。"""
    if isinstance(tc, dict):
        g = tc.get('group')
        if isinstance(g, dict):
            return g.get('name')
        return g
    g = getattr(tc, 'group', None)
    if g is not None:
        return getattr(g, 'name', None)
    return None


def tc_tags(tc) -> List[Any]:
    """提取用例的标签名列表（兼容字符串列表 / 对象列表）。"""
    if isinstance(tc, dict):
        t = tc.get('tags')
        if t is None:
            return []
        if isinstance(t, list):
            # tags 可能是字符串列表或对象列表
            result = []
            for tag in t:
                if isinstance(tag, dict):
                    result.append(tag.get('name'))
                else:
                    result.append(tag)
            return result
        return t
    t = getattr(tc, 'tags', None)
    if t is None:
        return []
    return t


def tc_has_tag(tc, tag_names) -> bool:
    """判断用例是否含有任一指定标签。"""
    tc_tag_set = set(str(t) for t in tc_tags(tc) if t is not None)
    for tn in tag_names:
        if str(tn) in tc_tag_set:
            return True
    return False


def tc_has_any_tag(tc) -> bool:
    """判断用例是否有任意标签。"""
    return len(tc_tags(tc)) > 0


def filter_test_cases(test_cases, category, categories, tags,
                      include_untagged: bool) -> List[Any]:
    """按 category / categories / tags / include_untagged 客户端过滤用例。"""
    filtered_cases = []
    for tc in test_cases.values() if isinstance(test_cases, dict) else test_cases:
        group_name = tc_group_name(tc)
        # category 过滤
        if category and category != 'all':
            if group_name != category:
                continue
        # categories 过滤
        if categories and len(categories) > 0:
            if group_name not in categories:
                continue
        # tags 过滤
        if include_untagged:
            if tags and len(tags) > 0:
                if not tc_has_tag(tc, tags) and tc_has_any_tag(tc):
                    continue
            else:
                if tc_has_any_tag(tc):
                    continue
        elif tags and len(tags) > 0:
            if not tc_has_tag(tc, tags):
                continue
        filtered_cases.append(tc)
    return filtered_cases


def extract_case_ids(cases) -> List[Any]:
    """从用例列表提取非空 ID（兼容 dict / 对象载荷）。"""
    ids = []
    for case in cases:
        cid = case.get('id') if isinstance(case, dict) else getattr(case, 'id', None)
        if cid is not None:
            ids.append(cid)
    return ids


def filter_results_by_case_ids(test_results, case_ids) -> List[Any]:
    """按 test_case_id 集合过滤测试结果（兼容 dict / 对象载荷）。"""
    case_id_set = {str(cid) for cid in case_ids}
    results = []
    for tr in test_results:
        tr_tc_id = tr.get('test_case_id') if isinstance(tr, dict) else getattr(tr, 'test_case_id', None)
        if tr_tc_id is not None and str(tr_tc_id) in case_id_set:
            results.append(tr)
    return results


def find_result_by_case_id(test_results, case_id) -> Optional[Any]:
    """按 test_case_id 查找单条测试结果（兼容 dict / 对象载荷）。"""
    for tr in test_results:
        tr_tc_id = tr.get('test_case_id') if isinstance(tr, dict) else getattr(tr, 'test_case_id', None)
        if tr_tc_id is not None and str(tr_tc_id) == str(case_id):
            return tr
    return None


def filter_results_by_case_evaluation(test_results, dim_results_map) -> List[Any]:
    """按用例评估状态过滤测试结果（统计前置过滤，对齐 V9.7.10 ReportUtils.filter_results_by_case_evaluation）。

    语义：若某用例（test_case_id）的任一维度评估结果 evaluation_status 非 'completed'，
    则该用例的所有测试结果都不参与统计。evaluation_status 为 None（旧数据/无评估行）不排除，
    对齐 V9.7.10 SQL 语义（NULL != 'completed' 在 SQL 中不命中）。

    Args:
        test_results: 测试结果列表（dict 或对象载荷）
        dim_results_map: {result_id: [维度评估结果 dict, ...]}，每项含
            evaluation_status / dimension_id 等字段（来自 _grpc_get_dim_results）

    Returns:
        过滤后的测试结果列表；无排除或空输入时原样返回。
    """
    if not test_results or not dim_results_map:
        return test_results

    # result_id -> test_case_id 映射（test_results 可能为 dict / 对象混合）
    result_to_case = {}
    for tr in test_results:
        tr_id = tr.get('id') if isinstance(tr, dict) else getattr(tr, 'id', None)
        if tr_id is None:
            continue
        tr_tc_id = tr.get('test_case_id') if isinstance(tr, dict) else getattr(tr, 'test_case_id', None)
        result_to_case[tr_id] = tr_tc_id

    # 统计「任一维度评估状态非 completed」的用例集合（对齐 V9.7.10 按 case 排除，
    # 而非按单条结果排除；None 状态与 SQL NULL 同语义不排除）
    excluded_case_ids = set()
    for rid, items in dim_results_map.items():
        tc_id = result_to_case.get(rid)
        if tc_id is None:
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            ev_status = it.get('evaluation_status')
            if ev_status is not None and ev_status != 'completed':
                excluded_case_ids.add(tc_id)
                break

    if not excluded_case_ids:
        return test_results

    return [
        tr for tr in test_results
        if (tr.get('test_case_id') if isinstance(tr, dict) else getattr(tr, 'test_case_id', None))
        not in excluded_case_ids
    ]
