# 03 — create_task 对话模式

> **所属步骤**：04_执行测试 → api_adapter  
> **改造类型**：修改  
> **涉及文件**：`api_adaper_service/app/main.py`

---

## 背景

现有 `POST /api/create_task` 仅支持音频流式传输模式。voice_llm 需要支持对话模式：文本或音频输入，返回 ASR + 翻译结果，支持多轮会话。

---

## 改造内容

### 1. 新增对话模式端点

```python
@app.route('/api/create_dialog_task', methods=['POST'])
def api_create_dialog_task():
    """
    voice_llm 对话模式任务创建。

    Request Body:
    {
        "session_id": "sess-001",
        "round": 0,
        "input_type": "text",        // "text" | "audio"
        "input_data": "你好世界",     // 文本或 base64 音频
        "source_lang": "zh",
        "target_lang": "en",
        "vendor": "voice_llm_vendor",
        "context": [...]             // 可选，由 session_store 管理
    }
    """
    data = request.get_json()

    session_id = data.get('session_id')
    round_idx = data.get('round', 0)
    input_type = data.get('input_type', 'text')
    input_data = data.get('input_data', '')
    vendor = data.get('vendor', '')
    source_lang = data.get('source_lang', 'zh')
    target_lang = data.get('target_lang', 'en')

    if not session_id:
        return jsonify({'code': 4000, 'msg': 'session_id is required'}), 400

    # 创建任务
    task_id = str(uuid.uuid4())
    task = {
        'task_id': task_id,
        'session_id': session_id,
        'round': round_idx,
        'input_type': input_type,
        'input_data': input_data,
        'vendor': vendor,
        'source_lang': source_lang,
        'target_lang': target_lang,
        'status': 'processing',
    }

    # 提交到处理线程
    thread = threading.Thread(
        target=process_dialog_task,
        args=(task,),
        daemon=True,
    )
    thread.start()

    return jsonify({
        'code': 0,
        'msg': 'success',
        'data': {'task_id': task_id, 'session_id': session_id},
    })
```

### 2. 对话任务处理

```python
def process_dialog_task(task):
    """处理 voice_llm 对话任务"""
    task_id = task['task_id']
    session_id = task['session_id']

    try:
        task_manager.update_task_status(task_id, 'processing')

        # 获取会话上下文
        context = session_store.get_context(session_id)

        # 选择适配器
        vendor_config = config.get(f'vendor.{task["vendor"]}', {})
        adapter = HttpAdapter(vendor_config)

        # 发送请求
        result = adapter.send_request(
            task_id=task_id,
            session_id=session_id,
            input_type=task['input_type'],
            input_data=task['input_data'],
            source_lang=task['source_lang'],
            target_lang=task['target_lang'],
            context=context,
        )

        # 更新会话上下文
        session_store.add_round(
            session_id=session_id,
            round_idx=task['round'],
            input_text=task['input_data'] if task['input_type'] == 'text' else '',
            output_text=result.get('asr_text', ''),
            latency=result.get('latency', 0),
        )

        # 存储轮次结果
        task_manager.add_round_result(
            task_id=task_id,
            round_idx=task['round'],
            result=result,
        )

        task_manager.update_task_status(task_id, 'completed')

    except Exception as e:
        logger.error(f'Dialog task failed: {e}')
        task_manager.update_task_status(task_id, 'failed', str(e))
```

### 3. 与现有 create_task 的对比

| 特性 | 现有 create_task | create_dialog_task |
|------|-----------------|-------------------|
| 协议 | WebSocket 流式 | HTTP 请求-响应 |
| 输入 | 音频文件（帧级传输） | 文本或音频 |
| 会话 | 无 | session_id 多轮 |
| 结果 | 帧级 ASR + 翻译 | 轮次级结果 |
| 适配器 | WebSocket/Mock | HTTP |
| 并发 | 方向限制 | 会话限制 |

### 4. 端点汇总

| 路由 | 说明 |
|------|------|
| `POST /api/create_task` | 现有音频流式任务（不变） |
| `POST /api/create_dialog_task` | voice_llm 对话模式（新增） |
| `GET /api/get_status/<task_id>` | 查询状态（不变） |
| `GET /api/get_final_result/<task_id>` | 查询结果（扩展轮次数据） |

---

## 不变部分

- 现有 `/api/create_task` 接口不变
- WebSocket 流式处理不变
- `/health` 端点不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_voice_llm_HTTP适配器` | HTTP 请求发送 |
| `02_会话状态管理` | 会话上下文 |
| `04_task_manager轮次结果` | 结果存储 |
