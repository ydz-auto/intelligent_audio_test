"""多轮评估数据构建混入：从 algorithm_result.rounds 提取/构建单轮评估数据"""
import copy

from shared.utils.json_utils import deserialize_algorithm_result


class RoundDataBuilderMixin:
    """从多轮 algorithm_result 中提取单轮评估数据"""

    def _extract_round_eval_data(self, algorithm_result, round_number):
        """从多轮 algorithm_result 中提取单轮评估数据

        当 round_number 不为 None 时，从 rounds[round_number] 提取该轮的扁平字段
        （asr_text 等），供评估端点直接使用。

        Args:
            algorithm_result: 完整的 algorithm_result（含 rounds[] 结构）
            round_number: 0-indexed 轮次编号

        Returns:
            dict: 单轮扁平数据，若轮次不存在返回 None
        """
        # 反序列化，兼容双重序列化的历史数据
        algorithm_result = deserialize_algorithm_result(algorithm_result)

        if not algorithm_result:
            return None

        rounds = algorithm_result.get('rounds', [])
        if not rounds or round_number >= len(rounds):
            return None

        round_data = rounds[round_number]
        output = round_data.get('output', {})

        # 构建扁平结构，把 rounds[i].output 的字段提升到顶层
        flat = dict(output) if isinstance(output, dict) else {}
        if 'latency' in round_data:
            flat['latency'] = round_data['latency']

        return flat

    def _build_rounds_list(self, algorithm_result, reference_params_col,
                            field_mapper, algorithm_type, test_type, task_id, test_case_id,
                            algorithm_params_col=None):
        """从 algo_result.rounds 构建 [{reference, hypothesis, ...}, ...] 列表

        遍历 param_mappings，按 source 类型从每轮的 output（device/api）、
        按轮加载的 reference_params（reference）和按轮加载的 case 参数（case）取值，
        用 target_param 作为 key。
        """
        from evaluation_service.infrastructure.acl import algorithm_acl_repository

        rounds = algorithm_result.get('rounds', [])
        # field_mapper 是通过 ACL 包装器包装的对象
        output_field_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)
        mappings = algorithm_acl_repository.get_param_mapping(algorithm_type, 'evaluation')

        if not mappings:
            self._log(
                level='WARNING',
                content=f"[_build_rounds_list] 未找到 {algorithm_type} 的 evaluation param mappings",
                task_id=task_id, test_case_id=test_case_id
            )
            return []

        # case_config 映射来源需要 test_case.config（rounds[].audios 等结构性配置），
        # 仅存在此类映射时按需加载（避免无谓的用例加载）
        case_config = None
        if any(m.get('source') == 'case_config' for m in mappings):
            case_config = self._load_case_config(test_case_id, task_id)

        rounds_list = []
        for rd in rounds:
            item = self._build_single_round(
                rd, reference_params_col, mappings,
                test_type, algorithm_type, task_id, test_case_id,
                algorithm_acl_repository.get_reference_params_list,
                algorithm_acl_repository.load_reference_params_file,
                algorithm_params_col=algorithm_params_col,
                case_config=case_config,
            )
            rounds_list.append(item)

        return rounds_list

    def _load_case_config(self, test_case_id, task_id):
        """加载 test_case.config 整份配置（供 source=case_config 映射取用例配置结构化字段）

        评估维度以 test_case.config 为统一评估上下文来源，
        rounds[].audios 等结构性字段与用例级 background_noise（rounds 外层的
        全局背景噪声）由此读取。
        加载失败返回空 dict（case_config 映射降级为不注入）。
        """
        try:
            test_case = self._task_acl_repo.get_test_case_detail(str(test_case_id))
            config = getattr(test_case, 'config', None) or {}
            return config if isinstance(config, dict) else {}
        except Exception as e:
            self._log(
                level='WARNING',
                content=f"[_load_case_config] 加载 test_case.config 失败: {e}",
                task_id=task_id, test_case_id=test_case_id
            )
            return {}

    @staticmethod
    def _gen_reference_value(ref_item, test_type, ref_type):
        """根据 ref_type 从参考参数项提取值（迁移自 reference_params_generator.get_reference_value）"""
        value = ref_item.get('value')
        if value is None:
            return ''
        if isinstance(value, list):
            if not value:
                return ''
            if ref_type == 'json':
                return value
            first_item = value[0]
            if isinstance(first_item, dict):
                return first_item.get('text', '')
            return str(first_item)
        if not ref_type or ref_type in ('text', 'audio'):
            if isinstance(value, dict):
                return {'text': value.get('text', ''), 'json': value.get('json', value.get('segments', []))}
            return {'text': str(value) if value else '', 'json': []}
        if ref_type in ('rttm_text', 'stm_text'):
            if isinstance(value, dict):
                return {'text': value.get('text', ''), 'json': value.get('json', value.get('segments', []))}
            return {'text': str(value) if value else '', 'json': []}
        if ref_type in ('rttm_json', 'stm_json', 'rttm', 'stm'):
            if isinstance(value, dict):
                return {'text': value.get('text', ''), 'segments': value.get('segments', [])}
            return {'text': '', 'segments': []}
        if isinstance(value, dict):
            return value.get('text', '')
        return value

    def _build_single_round(self, round_item, reference_params_col, mappings,
                            test_type, algorithm_type, task_id, test_case_id,
                            get_reference_params_fn, load_round_ref_file_fn,
                            algorithm_params_col=None, case_config=None):
        """构建单轮评估数据 item

        按轮加载 reference_params，遍历 mappings 按 source 类型从 output / reference / case_config 取值。
        """
        output = round_item.get('output', {})
        round_number = round_item.get('round', 0)

        item = {}

        # 按轮加载 reference_params
        # algo_result.rounds[].round 是 0-indexed，reference_params_col 用 1-indexed
        round_ref_data = {}
        if reference_params_col:
            round_ref_data = self._load_round_ref_file(
                reference_params_col, round_number + 1, load_round_ref_file_fn
            )
        for m in mappings:
            source = m.get('source', 'api')
            source_param = m.get('source_param', '')
            target_param = m.get('target_param', '')
            value = None

            if source in ('device', 'api'):
                # output 的 key 是 target_param 名（build_algorithm_result 已映射）
                # 用 None 而非 '' 作为默认值，避免空串覆盖维度级默认值
                value = output.get(target_param)
            elif source == 'reference':
                # 从按轮加载的 reference 取
                ref_item = round_ref_data.get(source_param)
                if ref_item and isinstance(ref_item, dict):
                    ref_type = None
                    for ref_def in get_reference_params_fn(algorithm_type):
                        if ref_def.get('code') == source_param:
                            ref_type = ref_def.get('type')
                            break
                    value = self._gen_reference_value(ref_item, test_type, ref_type)
            elif source == 'case':
                # 按轮从独立列加载 case 参数
                # algo_result.rounds[].round 是 0-indexed，algorithm_params_col 用 1-indexed
                if algorithm_params_col:
                    from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
                    round_case_params = ParamNormalizerService.normalize_algorithm_params(
                        ParamNormalizerService.get_round_algo_params(algorithm_params_col, round_number + 1))
                    value = round_case_params.get(source_param)
            elif source == 'case_config':
                # 从用例配置(test_case.config.rounds)取结构性字段
                # （被播放音频 audios、背景噪声 background_noise、干扰人 interferers 等）
                # round_number 为 0-indexed，与 config.rounds[].round_number(1-indexed) 对齐
                if case_config:
                    cfg_round = self._resolve_config_round(case_config.get('rounds'), round_number)
                    if cfg_round:
                        # 深拷贝避免污染共享的 test_case.config（写入 audio_path 等运行时字段）
                        cfg_round = copy.deepcopy(cfg_round)
                        # 归一化结构化音频字段：background_noise（轮次/用例级）、
                        # interferers（algorithm_params 提升）、三类音频 audio_path 补全
                        self._normalize_round_eval_fields(cfg_round, case_config, task_id, test_case_id)
                        value = cfg_round.get(source_param)

            if value is not None:
                item[target_param] = value

        return item

    @staticmethod
    def _resolve_config_round(rounds, round_number):
        """从 test_case.config.rounds 按轮取对应配置（0-indexed 对齐）

        config.rounds[].round_number 为 1-indexed，优先按该字段对齐，
        字段缺失时按下标兜底。
        """
        if not rounds or not isinstance(rounds, list):
            return None
        expected_no = round_number + 1
        for rc in rounds:
            if isinstance(rc, dict) and rc.get('round_number') == expected_no:
                return rc
        if 0 <= round_number < len(rounds) and isinstance(rounds[round_number], dict):
            return rounds[round_number]
        return None

    def _fill_round_audio_paths(self, round_cfg, task_id, test_case_id):
        """为轮次内结构化音频字段（audios/background_noise/interferers）中的
        audio_id 运行时补全 audio_path（幂等：已填则跳过）

        背景噪声为单个配置块（dict），干扰人与被播放音频为音频列表（list of dict）。
        评估服务以二进制（multipart）接收音频文件，主服务需先把 audio_id 解析为
        服务器物理路径，后续由 api_request_handler 提取文件上传。
        """
        targets = []
        audios = round_cfg.get('audios') if isinstance(round_cfg, dict) else None
        if isinstance(audios, list):
            targets.extend(audios)
        bg_noise = round_cfg.get('background_noise')
        if isinstance(bg_noise, dict):
            targets.append(bg_noise)
        interferers = round_cfg.get('interferers')
        if isinstance(interferers, list):
            targets.extend(interferers)
        if not targets:
            return
        try:
            from shared.models.database import get_db_session
            from sqlalchemy import text
            session = get_db_session()
            for item in targets:
                if not isinstance(item, dict):
                    continue
                audio_id = item.get('audio_id')
                if not audio_id or item.get('audio_path'):
                    continue
                row = session.execute(
                    text("SELECT file_path FROM audios WHERE id = :aid AND deleted = false"),
                    {'aid': audio_id}
                ).fetchone()
                if row and row[0]:
                    item['audio_path'] = row[0]
                else:
                    self._log(
                        level='WARNING',
                        content=f"[_fill_round_audio_paths] 未找到音频记录或文件路径: audio_id={audio_id}",
                        task_id=task_id, test_case_id=test_case_id
                    )
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            self._log(
                level='ERROR',
                content=f"[_fill_round_audio_paths] 查询音频失败: error={e}",
                task_id=task_id, test_case_id=test_case_id
            )

    def _normalize_round_eval_fields(self, round_cfg, case_config=None,
                                     task_id=None, test_case_id=None):
        """评估上下文轮次数归一化（原地修改，幂等）。

        将与播放链对齐的结构化音频字段统一到轮级 snake_case，供评估参数映射
        （source=case_config）经 cfg_round.get(source_param) 取值：

        - 背景噪声：轮次无 background_noise 且用例级存在全局背景噪声时注入副本
          （播放链中用例级全局噪声跨轮持续播放，需一并传递给评估服务）
        - 干扰人：从 algorithm_params（dict 或 [{field_code, field_value}]）提升为轮级 interferers
        - 为 audios/background_noise/interferers 中的 audio_id 补全 audio_path
        """
        if not isinstance(round_cfg, dict):
            return
        if round_cfg.get('background_noise') is None and isinstance(case_config, dict):
            case_bg = case_config.get('background_noise')
            if isinstance(case_bg, dict):
                round_cfg['background_noise'] = copy.deepcopy(case_bg)
        if round_cfg.get('interferers') is None:
            algo_params = round_cfg.get('algorithm_params')
            if algo_params is not None:
                from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
                interferers = ParamNormalizerService.normalize_algorithm_params(algo_params).get('interferers')
                if interferers is not None:
                    round_cfg['interferers'] = interferers
        self._fill_round_audio_paths(round_cfg, task_id, test_case_id)

    @staticmethod
    def _load_round_ref_file(reference_params_col, round_number, load_fn):
        """从 reference_params 独立列按轮加载参考参数文件（迁移自 CaseParameterExtractor._load_round_ref_file）

        Args:
            reference_params_col: [{round_number, reference_params_path}]
            round_number: 轮次序号
            load_fn: gRPC 函数 algo_load_reference_params_file(filepath)
        Returns:
            解析后的参考参数 dict，找不到返回 {}
        """
        if not reference_params_col:
            return {}
        for item in reference_params_col:
            if item.get('round_number') == round_number:
                path = item.get('reference_params_path')
                if not path:
                    return {}
                data = load_fn(path)
                if isinstance(data, list):
                    result = {}
                    for d in data:
                        if isinstance(d, dict) and 'code' in d:
                            result[d['code']] = d
                    return result
                if isinstance(data, dict):
                    return data
                return {}
        return {}
