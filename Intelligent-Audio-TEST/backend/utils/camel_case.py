def camel_to_snake(name):
    """
    将驼峰命名转换为蛇形命名
    
    Args:
        name: 驼峰命名的字符串
        
    Returns:
        蛇形命名的字符串
    """
    import re
    # 处理空格，替换为下划线
    name = name.replace(' ', '_')
    # 处理连续大写字母的情况（如 WER -> wer, WEREn -> wer_en）
    # 先处理全大写的情况
    if name.isupper():
        return name.lower()
    # 匹配大写字母，在前面添加下划线，然后转换为小写
    s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    s2 = re.sub('([A-Z]+)([A-Z][a-z])', r'\1_\2', s1)
    return s2.lower()


def snake_to_camel(name, capitalize_first=False):
    """
    将蛇形命名转换为驼峰命名
    
    Args:
        name: 蛇形命名的字符串
        capitalize_first: 是否大写首字母（默认为False）
        
    Returns:
        驼峰命名的字符串
    """
    # 分割下划线，将每个单词首字母大写，然后连接
    parts = name.split('_')
    if capitalize_first:
        return ''.join(word.capitalize() for word in parts)
    else:
        if not parts:
            return ''
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])
