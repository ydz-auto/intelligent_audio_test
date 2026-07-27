import json


def extract_by_path(data, path):
    """
    简单路径提取器，支持 a.b.c 格式
    """
    if not path or not data:
        return None
    try:
        for part in path.split('.'):
            if isinstance(data, dict):
                data = data.get(part)
            elif isinstance(data, list) and part.isdigit():
                data = data[int(part)]
            else:
                return None
        return data
    except:
        return None


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
