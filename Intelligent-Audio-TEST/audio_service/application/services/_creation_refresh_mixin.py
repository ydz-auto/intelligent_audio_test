# -*- coding: utf-8 -*-
"""测试用例创建 - 关联用例刷新 Mixin

从 audio_testcase_creation_service.py 拆分出的职责：
- refresh_test_cases_for_audios：按 audio_id 反查关联 TestCase 并刷新 algorithm_params
- _refresh_single_testcase_params：刷新单个用例的 algorithm_params

依赖说明：与 CreationAnnotationMixin 组合使用（复用其中的
_ensure_round_params_entry / _extract_field_value_from_annotation_data /
_resolve_interferer_ids 辅助方法）。
"""
class CreationRefreshMixin:
    """音频变更后反向刷新关联测试用例的职责"""

    def refresh_test_cases_for_audios(self, audio_ids, algorithm_type=None):
        """按 audio_id 反查 config.rounds[].audios[].audio_id 关联的 TestCase

        通过 ACL 仓储 ListTestCases 分页获取所有用例，在本地过滤出引用了
        目标 audio_id 的用例；再通过 ACL 仓储 UpdateTestCaseConfig 更新
        algorithm_params，由 task_service 侧触发参考参数刷新。
        """
        target_ids = set(audio_ids)

        # 分页获取所有测试用例，本地过滤出引用目标 audio_id 的用例
        affected_tcs = self._collect_testcases_referencing_audios(target_ids)
        if not affected_tcs:
            return []

        refreshed_ids = []
        for tc in affected_tcs:
            tc_id = tc.get('id')
            tc_algo_type = algorithm_type or tc.get('algorithm_type')
            if tc_algo_type:
                self._refresh_single_testcase_params(tc, tc_id, tc_algo_type)
            refreshed_ids.append(tc_id)

        return refreshed_ids

    def _collect_testcases_referencing_audios(self, target_ids):
        """分页遍历所有测试用例，本地过滤出引用目标 audio_id 的用例"""
        affected_tcs = []
        page = 1
        per_page = 100
        while True:
            data = self._testcase_acl.list_testcases(
                page=page, per_page=per_page, include_deleted=False,
            )
            if not data:
                break

            items = data.get('items', [])
            total = data.get('total', 0)

            for tc in items:
                if self._testcase_references_audios(tc, target_ids):
                    affected_tcs.append(tc)

            if page * per_page >= total or not items:
                break
            page += 1
        return affected_tcs

    @staticmethod
    def _testcase_references_audios(tc, target_ids):
        """判断用例 config.rounds[].audios[].audio_id 是否引用了目标音频"""
        config = tc.get('config') or {}
        rounds = config.get('rounds', [])
        if not isinstance(rounds, list):
            return False
        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue
            for audio_item in round_item.get('audios', []):
                if isinstance(audio_item, dict) and audio_item.get('audio_id') in target_ids:
                    return True
        return False

    def _refresh_single_testcase_params(self, tc, tc_id, tc_algo_type):
        """刷新单个用例的 algorithm_params（从标注重新提取）"""
        case_params_list = self._algorithm_acl.list_case_params(tc_algo_type)

        tc_test_type = tc.get('type') or tc.get('test_type') or 'api'
        scoped_params = [
            p for p in case_params_list
            if p.get('scope') == 'common' or p.get('scope') == tc_test_type
        ]

        if not scoped_params:
            return

        config = tc.get('config') or {}
        rounds = config.get('rounds', [])
        algo_params_col = tc.get('algorithm_params') or []

        # 预查音频文件名→ID、设备名→ID 映射，用于 interferers 的 ID 解析
        _audio_name_to_id_map, _dev_name_to_id = self._build_name_to_id_maps()

        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue
            round_number = round_item.get('round_number', 1)
            round_audios = round_item.get('audios', [])
            if not isinstance(round_audios, list):
                continue

            round_audio_ids = [
                a.get('audio_id') for a in round_audios
                if isinstance(a, dict) and a.get('audio_id')
            ]
            if not round_audio_ids:
                continue

            raw_anns = self._load_raw_annotations(round_audio_ids)
            if not raw_anns:
                continue

            extracted_params = self._extract_round_params_from_annotations(
                scoped_params, raw_anns, tc_algo_type,
                _audio_name_to_id_map, _dev_name_to_id,
            )

            round_ap_entry = self._ensure_round_params_entry(algo_params_col, round_number)
            existing_codes = set(
                p.get('field_code') for p in round_ap_entry.get('params', [])
            )
            for p in extracted_params:
                if p['field_code'] not in existing_codes:
                    round_ap_entry.setdefault('params', []).append(p)
                    existing_codes.add(p['field_code'])

        # 通过 ACL 仓储 UpdateTestCaseConfig 更新 algorithm_params
        # （task_service 侧会自动触发 ReferenceParamsGenerator.apply_to_config）
        update_data = {'algorithm_params': algo_params_col}
        self._testcase_acl.update_testcase_config(str(tc_id), update_data)

    def _load_raw_annotations(self, audio_ids):
        """按音频 ID 列表加载原始标注（code + data）"""
        raw_anns = []
        for aid in audio_ids:
            anns = self.repo.get_annotations_by_audio(aid)
            for ann in anns:
                raw_anns.append({
                    'code': ann.code,
                    'data': ann.data,
                })
        return raw_anns

    def _extract_round_params_from_annotations(self, scoped_params, raw_anns, algo_type,
                                               audio_name_to_id_map, dev_name_to_id):
        """从原始标注中按作用域参数定义提取参数值列表"""
        extracted_params = []
        for param in scoped_params:
            param_code = param.get('param_code')
            field_path = param.get('field_path') or param_code
            ann_code = param.get('annotation_code') or algo_type
            matched_anns = [a for a in raw_anns if a.get('code') == ann_code]
            if not matched_anns:
                matched_anns = raw_anns
            value = None
            for ann in matched_anns:
                a_data = ann.get('data')
                if a_data is None:
                    continue
                if isinstance(a_data, str):
                    value = a_data
                    break
                if isinstance(a_data, dict):
                    value = self._extract_field_value_from_annotation_data(a_data, field_path)
                    if value is not None:
                        break
            if value is not None:
                # 如果是 interferers 字段，对提取出的每个干扰人做 ID 解析
                if param_code == 'interferers' and isinstance(value, list):
                    self._resolve_interferer_ids(value, audio_name_to_id_map, dev_name_to_id)
                extracted_params.append({
                    'field_code': param_code,
                    'field_value': value
                })
        return extracted_params
