import os
import json
import base64
import traceback
from evaluation_service.domain.services.evaluation_utils import render_body_template
from evaluation_service.infrastructure.evaluation_mixin import EvaluationLoggerMixin


class PayloadBuilder(EvaluationLoggerMixin):
    """
    负责构建评估API请求的Payload
    """

    def _process_field_by_type(self, field_value, field_type):
        """
        根据字段类型处理字段值

        对于 audio/file 类型：读取文件内容并转为 base64 data URI
        对于其他类型：如果值是文件路径字符串，自动检测并读取文件内容

        Args:
            field_value: 字段值
            field_type: 字段类型 (text, audio, file, reference, score, number等)

        Returns:
            处理后的字段值
        """
        if isinstance(field_value, dict):
            actual_value = field_value.get('value')
            actual_type = field_value.get('field_type', field_type)
            return self._process_field_by_type(actual_value, actual_type)

        if field_type in ('audio', 'file'):
            if not field_value:
                return None
            if isinstance(field_value, str):
                if field_value.startswith('data:') or ',' in field_value[:50]:
                    return field_value
                if os.path.isfile(field_value):
                    try:
                        with open(field_value, 'rb') as f:
                            return 'data:audio/wav;base64,' + base64.b64encode(f.read()).decode()
                    except Exception:
                        return field_value
                return field_value
            return field_value

        if isinstance(field_value, str) and field_value and not field_value.startswith('data:'):
            if os.path.isfile(field_value):
                try:
                    ext = os.path.splitext(field_value)[1].lower()
                    binary_exts = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac',
                                   '.pcm', '.opus', '.amr', '.wma', '.webm', '.mp4',
                                   '.mpg', '.mpeg', '.avi', '.mov', '.mkv'}
                    with open(field_value, 'rb') as f:
                        content = f.read()
                    if ext in binary_exts:
                        mime = 'audio/wav' if ext == '.wav' else 'audio/' + ext.lstrip('.')
                        return 'data:' + mime + ';base64,' + base64.b64encode(content).decode()
                    else:
                        return content.decode('utf-8', errors='replace')
                except Exception:
                    return field_value

        return field_value

    def build_payload(self, body_template, context, task_id=None, test_case_id=None, algorithm_type=None):
        """
        构建API请求的Payload
        """
        processed_context = {}

        special_fields = set()
        if algorithm_type:
            from evaluation_service.infrastructure.acl.algorithm_acl_repository import (
                algorithm_acl_repository,
            )
            output_fields = algorithm_acl_repository.get_output_fields(algorithm_type)
            for field in output_fields:
                source_param = field.get('source_param', '')
                if source_param:
                    special_fields.add(source_param)

        for k, v in context.items():
            if special_fields and k in special_fields and isinstance(v, dict) and 'text' in v and 'json' in v:
                processed_context[k] = v
            elif isinstance(v, dict) and 'field_type' in v:
                processed_context[k] = self._process_field_by_type(v, v.get('field_type', 'text'))
            elif isinstance(v, dict) and 'text' in v:
                processed_context[k] = v.get('text', '')
            else:
                processed_context[k] = v

        self._log(
            level='DEBUG',
            content=f"[build_payload] body_template={body_template}, special_fields={special_fields}, processed_context keys={list(processed_context.keys())}, processed_context values={dict((k, str(v)[:100]) for k, v in processed_context.items())}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        if body_template:
            if isinstance(body_template, str):
                return render_body_template(body_template, processed_context)
            elif isinstance(body_template, dict):
                result = {}
                for k, v in body_template.items():
                    if k == 'rounds' and isinstance(v, list) and len(v) > 0:
                        # rounds 结构：body_template 里声明了每轮的字段模板
                        round_template = v[0] if isinstance(v[0], dict) else {}
                        rounds_data = processed_context.get('rounds', [])
                        # 若无 rounds_data，则从顶层 context 字段构建单轮数据
                        if not rounds_data and round_template:
                            single_round = {}
                            for rk, rv in round_template.items():
                                if isinstance(rv, str) and rv.startswith('{{') and rv.endswith('}}'):
                                    placeholder_key = rv[2:-2]
                                    if placeholder_key in processed_context:
                                        single_round[rk] = processed_context[placeholder_key]
                                    else:
                                        single_round[rk] = ''
                                else:
                                    single_round[rk] = rv
                            rounds_data = [single_round]
                        rendered_rounds = []
                        for rd in rounds_data:
                            rendered_rd = {}
                            for rk, rv in round_template.items():
                                if isinstance(rv, str) and rv.startswith('{{') and rv.endswith('}}'):
                                    placeholder_key = rv[2:-2]
                                    rendered_rd[rk] = rd.get(placeholder_key, '')
                                elif rk in rd:
                                    rendered_rd[rk] = rd[rk]
                                else:
                                    rendered_rd[rk] = rv
                            rendered_rounds.append(rendered_rd)
                        result['rounds'] = rendered_rounds
                    elif k in processed_context and processed_context[k] not in (None, ''):
                        result[k] = processed_context[k]
                    elif isinstance(v, str) and v.startswith('{{') and v.endswith('}}'):
                        placeholder_key = v[2:-2]
                        if placeholder_key in processed_context and processed_context[placeholder_key] not in (None, ''):
                            result[k] = processed_context[placeholder_key]
                        # context 中无值或为空时不设该字段，让 eval_server 使用自身配置
                    else:
                        result[k] = v
                return result
        return processed_context
