# 10 - reference_params_generator 适配（上传生成文件，独立列存路径）

## 涉及文件
- `Intelligent-Audio-TEST/backend/utils/algorithm/reference_params_generator.py`

## 现状分析

`ReferenceParamsGenerator` 从 `config.audios` 获取全部音频，查询 `AudioAnnotation`，聚合标注文本/RTTM 到一个 JSON，写入 `TestCase.reference_params` 列。

**问题**：
- 100+ 音频聚合后可达 MB 级别
- 无法按轮区分
- 数据来源：`AudioAnnotation.data` 包含 `[{speaker, start, end, text}]` 分段

## 改造方案（上传生成文件，独立列存路径，用户可编辑）

### 核心变更

```
旧流程：音频标注 → 聚合 → 写入 TestCase.reference_params 列（MB级，单份）
新流程：上传音频 → 按轮从 AudioAnnotation 生成 → 写入文件 → 路径按轮存入 TestCase.reference_params 列
```

### 生成时机

**用户上传音频并关联到轮次时**，自动触发生成：

```python
def on_audio_associated(self, test_case_id, round_number, audio_id):
    """音频关联到轮次时，自动生成/更新参考文本文件"""
    # 1. 获取本轮所有音频
    round_audios = self._get_round_audios(test_case_id, round_number)
    
    # 2. 查询 AudioAnnotation
    annotations = self._query_annotations(round_audios)
    
    # 3. 生成参考文本
    ref_content = self._generate_reference(annotations)
    
    # 4. 写入文件
    file_path = self._write_ref_file(test_case_id, round_number, ref_content)
    
    # 5. 路径写入 TestCase.reference_params 列（按轮分组）
    self._update_round_ref_path(test_case_id, round_number, file_path)
```

### 文件存储

```python
def _write_ref_file(self, test_case_id, round_number, content):
    """写入参考文本文件"""
    file_path = f"ref_params/{test_case_id}/round_{round_number}.json"
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    return file_path
```

### 文件内容

```json
{
  "reference_text": "本轮音频的聚合参考文本",
  "reference_rttm": "SPEAKER_00 1 0.5 3.2 ...",
  "segment_count": 3,
  "audio_ids": ["audio_001", "audio_002"],
  "generated_at": "2026-06-08T10:00:00Z"
}
```

### 用户可编辑

前端提供查看/编辑界面：

```
前端读取 reference_params 列中本轮 reference_params_path → 请求后端读取文件内容 → 展示给用户
 用户修改 → 前端提交修改 → 后端写入同一文件（路径不变）
```

后端接口：

```python
# GET /api/ref-params/{path}  — 读取文件内容
# PUT /api/ref-params/{path}  — 用户编辑后保存
```

### 执行时读取

```python
def _load_round_ref_file(self, reference_params_col, round_number):
    """执行测试时从 reference_params 列按轮读取参考文本文件"""
    if not reference_params_col:
        return {}
    for item in reference_params_col:
        if item.get('round_number') == round_number:
            path = item.get('reference_params_path')
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            break
    return {}
```

### TestCase.reference_params 列结构（保留，按轮分组）

| 变更 | 说明 |
|------|------|
| `TestCase.reference_params` | **保留** — 按轮分组 `[{round_number, reference_params_path}]` |
| 文件内容 | 可被用户编辑，执行时按路径读取 |

### 数据量对比

| 场景 | 旧设计 | 新设计 |
|------|--------|--------|
| DB 列 | MB 级 reference_params（单份） | 按轮分组，只存路径字符串 |
| 文件 | 无 | MB 级文件（不影响 DB 列） |
| 用户编辑 | 需解析大 JSON | 直接编辑文件内容 |
| 按轮区分 | 不支持 | 支持（每轮一个文件 + 一条路径记录） |

## 相关文档
- [03_Config_JSON扁平化设计.md](03_Config_JSON扁平化设计.md)
- [09_case_parameter_extractor适配.md](09_case_parameter_extractor适配.md)
