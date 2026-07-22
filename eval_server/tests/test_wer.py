import re
import numpy as np

# 计算编辑距离（Levenshtein 距离）
def levenshtein_distance(ref, hyp):
    ref_len = len(ref)
    hyp_len = len(hyp)
    
    # 创建距离矩阵
    dp = np.zeros((ref_len + 1, hyp_len + 1), dtype=int)
    
    # 初始化第一行和第一列
    for i in range(ref_len + 1):
        dp[i][0] = i
    for j in range(hyp_len + 1):
        dp[0][j] = j
    
    # 填充矩阵
    for i in range(1, ref_len + 1):
        for j in range(1, hyp_len + 1):
            if ref[i-1] == hyp[j-1]:
                cost = 0
            else:
                cost = 1
            dp[i][j] = min(dp[i-1][j] + 1,      # 删除
                          dp[i][j-1] + 1,      # 插入
                          dp[i-1][j-1] + cost)  # 替换
    
    return dp[ref_len][hyp_len]

# 分割文本为字符列表，区分中文和英文
def split_text(text):
    # 中文正则：匹配中文字符
    zh_pattern = re.compile(r'[\u4e00-\u9fa5]')
    # 英文正则：匹配英文字母
    en_pattern = re.compile(r'[a-zA-Z]')
    
    chars = []
    zh_chars = []
    en_chars = []
    
    i = 0
    while i < len(text):
        char = text[i]
        if zh_pattern.match(char):
            # 中文字符，直接添加
            chars.append(char)
            zh_chars.append(char)
            i += 1
        elif en_pattern.match(char):
            # 英文字符，合并连续的英文单词
            word = ''
            while i < len(text) and en_pattern.match(text[i]):
                word += text[i]
                i += 1
            chars.append(word)
            en_chars.append(word)
        else:
            # 其他字符，跳过
            i += 1
    
    return chars, zh_chars, en_chars

# 计算 WER
def calculate_wer(ref_text, hyp_text):
    # 分割参考文本
    ref_chars, ref_zh, ref_en = split_text(ref_text)
    # 分割识别结果
    hyp_chars, hyp_zh, hyp_en = split_text(hyp_text)
    
    print(f"参考文本分割: {ref_chars}")
    print(f"识别结果分割: {hyp_chars}")
    print(f"中文参考: {ref_zh}")
    print(f"中文识别: {hyp_zh}")
    print(f"英文参考: {ref_en}")
    print(f"英文识别: {hyp_en}")
    
    # 计算总 WER
    total_errors = levenshtein_distance(ref_chars, hyp_chars)
    total_wer = total_errors / len(ref_chars) if len(ref_chars) > 0 else 0.0
    
    # 计算中文 WER
    zh_errors = levenshtein_distance(ref_zh, hyp_zh)
    zh_wer = zh_errors / len(ref_zh) if len(ref_zh) > 0 else 0.0
    
    # 计算英文 WER
    en_errors = levenshtein_distance(ref_en, hyp_en)
    en_wer = en_errors / len(ref_en) if len(ref_en) > 0 else 0.0
    
    return {
        'wer': round(total_wer, 4),
        'wer_zh': round(zh_wer, 4),
        'wer_en': round(en_wer, 4)
    }

# 测试 WER 计算
if __name__ == "__main__":
    ref_text = "这是一个测试测试文本text"
    hyp_text = "这是一个测试文本text"
    
    print("测试 WER 计算:")
    print(f"参考文本: {ref_text}")
    print(f"识别结果: {hyp_text}")
    
    result = calculate_wer(ref_text, hyp_text)
    print(f"WER 结果: {result}")