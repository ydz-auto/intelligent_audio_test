# -*- coding: utf-8 -*-
"""往平台 DB 插一条打断评估虚拟结果（case1 真实值），供前端显示验证。

直接写 TestResultDimension.dimension_value/score（绕过 extract_by_path 的 field_path 前缀问题）。
挂到最新 task + 一个 test_case，插 mock TaskCase + TestResult + 6 维度行。跑完打印查看 URL。
"""
import json
from datetime import datetime
from sqlalchemy import create_engine, text

URI = "postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test"
eng = create_engine(URI)

# case1 真实值
DIM_VALUES = {  # dimension.name -> (dimension_value, score)
    '打断成功率': (1.0, 1.0),
    '打断检查时延': (2.6, 2.6),
    '打断恢复时延': (2.9, 2.9),
    '平均连贯性': (5.0, 5.0),
    '平均相关性': (5.0, 5.0),
    '平均适应性': (5.0, 5.0),
}

# 设备输出（algorithm_result，前端 algorithm_results 区显示）
ALGO_RESULT = {
    "user_wav": "D:/work/fwqdata/270/270/fbec58d7-054e-446f-916d-86eebe5d289a/5SM0125613000197/103590_16000_1_1_cap_client_process_out.wav",
    "ai_wav": "D:/work/fwqdata/270/270/fbec58d7-054e-446f-916d-86eebe5d289a/5SM0125613000197/103590_16000_2_1_cap_client_ec_out.wav",
    "answer": "嘿，最近怎么样？这个问题嘛。今天主要有三个重点新闻…好的，那就不说啦。",
    "question": "给我简单说一下今天的新闻。行了，别说了。",
}

# 完整 eval_server 返回（api_raw_response + evaluation_data aux）
FULL_RESULT = {
    "interruption_success_rate": 1.0,
    "avg_stop_latency_s": 2.6,
    "avg_recovery_latency_s": 2.9,
    "stop_rate": 1.0, "resume_rate": 1.0,
    "n_events": 1, "n_user_segments": 1, "n_recovery_only": 0, "n_no_model_speech": 0,
    "avg_overlap_s": 1.2, "avg_silence_gap_s": 1.5,
    "message": "OK (LLM)",
    "llm_recovery_avg_coherence": 5.0, "llm_recovery_avg_relevance": 5.0, "llm_recovery_avg_adaptability": 5.0,
    "llm_recovery_coherence_reason": "AI顺畅响应停止播报指令并自然引导新话题，衔接流畅。",
    "llm_recovery_relevance_reason": "准确理解用户“别说了”的意图并立即遵从，完全切题。",
    "llm_recovery_adaptability_reason": "话题切换适应良好，自然转入闲聊互动。",
    "llm_interaction_behavior_summary": {"回应": 1, "恢复": 0, "询问": 0, "无关回复": 0, "沉默或无视": 0},
    "llm_interaction_per_round": [{"round": 1, "is_interrupted": True, "reaction_behavior": "回应",
        "reaction_reason": "AI正面回应用户的停止指令，表达“好的，那就不说啦”并主动询问其他话题。"}],
    "llm_recovery_per_round": [{
        "round": 1, "is_interrupted": True,
        "is_interrupted_reason": "AI在播报新闻时，用户开口说“行了，别说了”进行打断。",
        "success": True, "success_reason": "AI说完当前句子后停下新闻播报，并准确确认不再继续说，同时引导新话题。",
        "stop_latency_s": 2.6, "stop_reason": "用户约46.000s开口打断，AI于48.600s播报完当前句停下，差值为2.600s。",
        "recovery_latency_s": 2.9, "recovery_reason": "用户约47.200s说完打断语，AI于50.100s重新开口回应，差值为2.900s。",
        "user_interrupt_segment": [46.0, 47.2], "model_active_segment": [41.2, 48.6], "model_next_segment": [50.1, 51.7],
        "reaction_behavior": "回应", "reaction_reason": "AI正面回应用户的停止指令…",
    }],
    "per_event": [],
    "llm_eval": {"enabled": True, "model": "gemini-3.7-flash",
        "timing_comparison": {"timing_success_rate": 0.0, "timing_avg_stop_latency_s": None,
            "timing_avg_recovery_latency_s": None, "llm_success_rate": 1.0,
            "llm_avg_stop_latency_s": 2.6, "llm_avg_recovery_latency_s": 2.9},
        "audio_dropped": False, "message": "OK"},
}
# evaluation_data 用 param_code 作 key（前端 combined_data 展开）
EVAL_DATA = {
    "interruption_stop_rate": 1.0, "interruption_resume_rate": 1.0,
    "interruption_n_events": 1, "interruption_n_user_segments": 1,
    "interruption_n_recovery_only": 0, "interruption_n_no_model_speech": 0,
    "interruption_avg_overlap_s": 1.2, "interruption_avg_silence_gap_s": 1.5,
    "interruption_per_event": FULL_RESULT["llm_recovery_per_round"],
    "interruption_message": "OK (LLM)",
    "llm_recovery_avg_coherence": 5.0, "llm_recovery_avg_relevance": 5.0, "llm_recovery_avg_adaptability": 5.0,
    "llm_recovery_coherence_reason": FULL_RESULT["llm_recovery_coherence_reason"],
    "llm_recovery_relevance_reason": FULL_RESULT["llm_recovery_relevance_reason"],
    "llm_recovery_adaptability_reason": FULL_RESULT["llm_recovery_adaptability_reason"],
    "llm_interaction_behavior_summary": FULL_RESULT["llm_interaction_behavior_summary"],
    "llm_interaction_per_round": FULL_RESULT["llm_interaction_per_round"],
    "llm_recovery_per_round": FULL_RESULT["llm_recovery_per_round"],
    "llm_eval": FULL_RESULT["llm_eval"],
}
RESULT_DATA = {"evaluation_data": EVAL_DATA}

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

with eng.begin() as conn:
    # 1. 查 6 个 interruption 维度 id
    dims = conn.execute(text(
        "SELECT id, name FROM dimensions WHERE task_type_code='interruption_metrics' AND deleted=false "
        "AND name IN :names"
    ), {"names": tuple(DIM_VALUES.keys())}).fetchall()
    dim_map = {n: i for i, n in dims}
    print("维度:", dim_map)
    missing = [n for n in DIM_VALUES if n not in dim_map]
    if missing:
        print(f"!! 缺维度(先跑 seed_interruption_dimensions.py): {missing}"); raise SystemExit(1)

    # 2. 找 task(优先270) + test_case
    task_id = conn.execute(text("SELECT id FROM test_tasks WHERE id=270")).scalar()
    if not task_id:
        task_id = conn.execute(text("SELECT id FROM test_tasks ORDER BY id DESC LIMIT 1")).scalar()
    test_case_id = conn.execute(text("SELECT id FROM test_cases ORDER BY id DESC LIMIT 1")).scalar()
    print(f"挂载: task_id={task_id} test_case_id={test_case_id}")
    if not (task_id and test_case_id):
        print("!! 无 task/test_case，先在平台建任务/用例"); raise SystemExit(1)

    # 3. mock TaskCase
    tc_id = conn.execute(text(
        "INSERT INTO task_case_relations (task_id, test_case_id, status, execution_status, evaluation_status, created_at) "
        "VALUES (:t, :c, 'completed', 'completed', 'completed', :n) RETURNING id"
    ), {"t": task_id, "c": test_case_id, "n": now}).scalar()

    # 4. TestResult
    tr_id = conn.execute(text(
        "INSERT INTO test_results (task_id, test_case_id, algorithm_type, execution_status, "
        "algorithm_result, result_data, created_at) VALUES (:t, :c, 'voice_llm', 'completed', "
        ":algo, :rd, :n) RETURNING id"
    ), {"t": task_id, "c": test_case_id, "algo": json.dumps(ALGO_RESULT),
        "rd": json.dumps(RESULT_DATA, ensure_ascii=False), "n": now}).scalar()

    # 5. 6 个 TestResultDimension
    for name, (val, score) in DIM_VALUES.items():
        conn.execute(text(
            "INSERT INTO test_result_dimensions (test_result_id, dimension_id, algorithm_type, "
            "round_number, dimension_value, score, status, evaluation_status, api_raw_response, created_at) "
            "VALUES (:tr, :d, 'voice_llm', NULL, :v, :s, 'passed', 'completed', :resp, :n)"
        ), {"tr": tr_id, "d": dim_map[name], "v": val, "s": score,
            "resp": json.dumps(FULL_RESULT, ensure_ascii=False), "n": now})

    print(f"\n✅ 插入完成: task_case_id={tc_id} test_result_id={tr_id}")
    print(f"   后端查看: GET http://localhost:5000/api/v1/tasks/{task_id}/cases/{test_case_id}/detail")
    print(f"   前端: 打开任务 {task_id} → 用例 {test_case_id} → 用例详情/报告")
