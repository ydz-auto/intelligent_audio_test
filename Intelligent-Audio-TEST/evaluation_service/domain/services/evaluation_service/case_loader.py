"""测试用例与参考文本加载混入

P0 DDD 改造：移除模块级 infrastructure/acl import，改用方法内延迟导入。
Domain 层不应在编译期依赖 infrastructure 层。
"""


class CaseLoaderMixin:
    """加载测试用例、算法类型、参考文本和维度配置"""

    # 用例配置维度条目的多轮整体评估口径值（round_scope，与建用例侧/前端协议一致）
    OVERALL_ROUND_SCOPE = 'multi'

    def _load_test_case_and_refs(self, test_case_id, field_mapper, kwargs, task_id, round_number=None):
        """加载测试用例、算法类型、参考文本和维度配置"""
        # P0-1: 通过依赖注入的 ABC 访问 ACL，domain 层不 import infrastructure
        test_case = self._task_acl_repo.get_test_case_detail(str(test_case_id))
        if not test_case:
            self._log(level='ERROR', content=f"找不到测试用例 {test_case_id}", task_id=task_id)
            return None

        algorithm_type = test_case.algorithm_type or kwargs.get('algorithm_type', 'translation')
        eval_input_fields = field_mapper.get_evaluation_input_fields(algorithm_type)

        ref_texts = self._extract_ref_texts(eval_input_fields, kwargs, task_id, test_case_id)

        self._log(
            level='DEBUG',
            content=f"[ref_texts] final ref_texts={ref_texts}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 从 test_case.config 按 round_number 过滤维度配置（单轮取该轮维度，整体取顶层维度）
        test_case_config = test_case.config or {}
        dimensions_config = self._merge_dimensions_config(test_case_config, round_number=round_number)

        return {
            'test_case': test_case,  # P1.4: 现在是 TestCaseDetailDTO
            'algorithm_type': algorithm_type,
            'ref_texts': ref_texts,
            'dimensions_config': dimensions_config,
        }

    def _merge_dimensions_config(self, test_case_config, round_number=None):
        """按 round_number 过滤维度配置（评估维度隔离，对齐 V9.7.10 设计文档）：

        - round_number=<int>（单轮评估）：只取 rounds[round_number].evaluation.dimensions，
          剔除其中 round_scope=multi 的整体口径维度（整体维度不参与逐轮评估）
        - round_number=None（整体评估）：取顶层 config.dimensions，并合并轮次注入的
          round_scope=multi 维度（INT-126：上传口径把评估维度逐轮注入 rounds 且
          case 级 config.dimensions 为空，整体维度不要求显式配置在顶层；
          per_round 维度由按轮评估出分，不混入整体评估）
        - 未标注 round_scope 的维度按逐轮（单轮）口径处理，维持既有行为
        """
        dimensions_config = []
        seen_dim_ids = set()
        rounds = test_case_config.get('rounds', [])
        if round_number is not None:
            # 单轮评估：只取指定轮的 dimensions（排除整体口径维度）
            if rounds and isinstance(rounds, list) and round_number < len(rounds):
                round_item = rounds[round_number]
                if isinstance(round_item, dict):
                    evaluation = round_item.get('evaluation', {})
                    if isinstance(evaluation, dict):
                        round_dims = evaluation.get('dimensions', [])
                        for d in round_dims:
                            if self._is_overall_scope_dim(d):
                                continue
                            dim_id = d.get('id') if isinstance(d, dict) else d
                            if dim_id and dim_id not in seen_dim_ids:
                                seen_dim_ids.add(dim_id)
                                dimensions_config.append(d)
            return dimensions_config
        # 整体评估：顶层 config.dimensions + 轮次注入的整体口径维度（round_scope=multi）
        top_dims = test_case_config.get('dimensions', [])
        for d in top_dims:
            dim_id = d.get('id') if isinstance(d, dict) else d
            if dim_id and dim_id not in seen_dim_ids:
                seen_dim_ids.add(dim_id)
                dimensions_config.append(d)
        if rounds and isinstance(rounds, list):
            for round_item in rounds:
                if not isinstance(round_item, dict):
                    continue
                evaluation = round_item.get('evaluation', {})
                if not isinstance(evaluation, dict):
                    continue
                for d in evaluation.get('dimensions', []) or []:
                    if not self._is_overall_scope_dim(d):
                        continue
                    dim_id = d.get('id') if isinstance(d, dict) else d
                    if dim_id and dim_id not in seen_dim_ids:
                        seen_dim_ids.add(dim_id)
                        dimensions_config.append(d)
        return dimensions_config

    @classmethod
    def _is_overall_scope_dim(cls, dim):
        """维度条目是否为多轮整体评估口径（round_scope=multi）

        未标注 round_scope 或逐轮口径（single/per_round）的维度按逐轮处理。
        """
        return isinstance(dim, dict) and dim.get('round_scope') == cls.OVERALL_ROUND_SCOPE

    def _extract_ref_texts(self, eval_input_fields, kwargs, task_id, test_case_id):
        """从 kwargs 中提取参考文本"""
        ref_texts = {}
        ref_text_keys = {'rttm_ref', 'stm_ref', 'asr_ref', 'asr_rerference_text'}

        for field_key, field_info in eval_input_fields.items():
            field_type = field_info.get('type', 'text')
            field_value = kwargs.get(field_key)

            self._log(
                level='DEBUG',
                content=f"[kwargs field_key] field_key={field_key}, field_value={field_value}, field_value_type={type(field_value)}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            if not field_value:
                continue

            if field_key in ref_text_keys and isinstance(field_value, dict) and 'text' in field_value:
                ref_texts[field_key] = {
                    'text': field_value.get('text', ''),
                    'json': field_value.get('json', field_value.get('segments', []))
                }
            else:
                ref_texts[field_key] = {
                    'value': field_value,
                    'field_type': field_type
                }

        return ref_texts

    def _extract_dimension_ids(self, dimensions_config):
        """从维度配置中提取维度ID列表"""
        dimension_ids = []
        for item in dimensions_config:
            if isinstance(item, dict):
                dimension_id = item.get('id')
                if dimension_id:
                    dimension_ids.append(dimension_id)
            else:
                dimension_ids.append(item)
        return dimension_ids
