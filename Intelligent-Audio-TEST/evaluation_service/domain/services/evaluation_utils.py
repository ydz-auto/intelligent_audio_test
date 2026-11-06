import json

# INT-107: 用例级失败原因上限——完整堆栈留在维度行（test_result_dimensions.error_message），
# task_case_relations.error_message 只保留可读摘要
CASE_ERROR_MESSAGE_MAX_LEN = 2000


def compose_case_error_message(dim_error_messages):
    """将维度失败原因聚合为用例级 error_message 摘要

    INT-107 缺陷①：评估整例失败时 task_case_relations.error_message 为空串，
    失败原因只在维度行里，排障困难。此函数生成 "维度评估失败: 原因1; 原因2" 形式的摘要，
    相同原因（如同一端点不可达导致多维度同报 ConnectTimeout）去重后只保留一条。
    """
    reasons = []
    for m in (dim_error_messages or []):
        if not m:
            continue
        text = str(m).strip()
        if text and text not in reasons:
            reasons.append(text)
    if not reasons:
        return ''
    message = '维度评估失败: ' + '; '.join(reasons)
    if len(message) > CASE_ERROR_MESSAGE_MAX_LEN:
        message = message[:CASE_ERROR_MESSAGE_MAX_LEN] + '...(截断，完整原因见各维度错误信息)'
    return message


def calculate_score(value, rule):
    """
    根据评分规则计算分值
    rule 示例: {"type": "linear", "min": 0, "max": 100, "score_min": 0, "score_max": 100}
    或 {"type": "threshold", "thresholds": [{"val": 0.8, "score": 100}, {"val": 0.5, "score": 60}]}
    """
    if not rule or value is None:
        return 0
    
    rule_type = rule.get('type', 'direct')
    try:
        if rule_type == 'direct':
            return float(value)
        if rule_type == 'linear':
            v_min = rule.get('min', 0)
            v_max = rule.get('max', 1)
            s_min = rule.get('score_min', 0)
            s_max = rule.get('score_max', 100)
            if v_max == v_min:
                return s_max
            # 线性插值
            ratio = (value - v_min) / (v_max - v_min)
            score = s_min + ratio * (s_max - s_min)
            return min(max(score, s_min), s_max)
        if rule_type == 'threshold':
            thresholds = sorted(rule.get('thresholds', []), key=lambda x: x['val'], reverse=True)
            for t in thresholds:
                if value >= t['val']:
                    return t['score']
            return 0
    except:
        return 0
    return 0


def render_body_template(body_template, context):
    """
    渲染请求体模板，替换占位符
    """
    if not body_template or not isinstance(body_template, str):
        return None
    
    body_str = body_template
    for k, v in context.items():
        placeholder = "{{" + k + "}}"
        if placeholder in body_str:
            if isinstance(v, (list, dict)):
                import json as _json
                body_str = body_str.replace(placeholder, _json.dumps(v, ensure_ascii=False))
            else:
                body_str = body_str.replace(placeholder, str(v))
    return json.loads(body_str)
