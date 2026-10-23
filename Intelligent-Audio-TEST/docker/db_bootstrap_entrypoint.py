# -*- coding: utf-8 -*-
"""INT-272：数据库结构引导 job 入口（compose db_bootstrap 服务 CMD）。

执行 scripts/migrations/README.md 全新库初始化链（全脚本幂等）：
    1. create_all_tables.py            —— 69 表建表（Base.metadata.create_all）
    2. 202608 结构基线 + 审计列 + RBAC 种子
    3. 202609 结构列 + 种子
    4. 202610 结构迁移 + dev 引导用户种子
    （数据回填/清洗类脚本不在引导链内：仅对存量数据有意义，全新库为 no-op）

任一步非零退出即整体失败 —— compose 以 service_completed_successfully 门控
后端服务启动，未引导完成的库不会被业务服务连接。

种子/迁移脚本以子进程运行（与 README 手工口径 1:1，脚本各自处理幂等与输出）；
连接串统一经 DATABASE_URI 环境变量注入（compose 设置）。
"""
import os
import subprocess
import sys

SCRIPTS = '/opt/scripts'
APP_ROOT = '/app'

# 引导链：按 scripts/migrations/README.md「执行顺序总览」精选结构/种子项。
# 排除项（数据回填/清洗/一次性修复）：backfill_*、cleanup_*、
# drop_task_type_and_testcase_test_type（破坏性收尾，全新库无此列）、
# fix_audio_tags_types（历史临时脚本遗留 + 硬编码连接串）、
# fix_partial_unique_indexes（可选项，沿用运行库现状）。
# （add_laboratory_tables 已于 INT-537 纳入：实验室扩展随 ① 落地，全新库须建表）
BOOTSTRAP_STEPS = [
    # ① 初始建表（69 表）
    ('python', 'scripts/create_all_tables.py'),
    # ② 结构基线：删 FK（应用层管理引用完整性）+ 软删除/审计列 + 索引
    ('python', 'scripts/migrations/202608/remove_foreign_keys_and_soft_delete.py'),
    # ③ 审计/软删除列兜底（逐表对齐 ORM 元数据）
    ('python', 'scripts/migrations/202608/add_audit_columns.py'),
    # ④ 重新评估列
    ('python', 'scripts/migrations/202608/add_reevaluated_at.py'),
    # ④.1 实验室扩展：laboratories 主表 + task_laboratory_relations + 各表 lab_id 列
    #     （INT-493/INT-537 拆分①；脚本幂等，全步骤 CREATE IF NOT EXISTS / 列存在跳过）
    ('python', 'scripts/migrations/202608/add_laboratory_tables.py'),
    # ⑦ RBAC 种子（权限点 + 5 角色，含 INT-537 lab:* 三码）
    ('python', 'scripts/migrations/202608/seed_rbac.py'),
    # ⑧ 评估阈值列
    ('python', 'scripts/migrations/202609/add_pass_threshold_to_eval_params.py'),
    # ⑨ 用例级设备路由列
    ('python', 'scripts/migrations/202609/add_task_case_device_type.py'),
    # ⑩ 已发布任务表 + 日常任务追溯字段
    ('python', 'scripts/migrations/202609/add_published_tasks.py'),
    # 维度列扩展（dimension seeds 的前置：sort_order / agg_denominator /
    # exclude_rounds 为 fresh create_all 库缺失的列；worker_instance_id 为
    # test_results 执行实例列）
    ('python', 'scripts/migrations/202609/add_dimension_sort_order.py'),
    ('python', 'scripts/migrations/202609/add_agg_denominator_column.py'),
    ('python', 'scripts/migrations/202609/add_exclude_rounds_column.py'),
    ('python', 'scripts/migrations/202609/add_worker_instance_id.py'),
    # 维度种子（评估域金标；seed_voice_llm 为 ㉓㉔㉕ 前置）
    ('python', 'scripts/migrations/202609/seed_voice_llm.py'),
    ('python', 'scripts/migrations/202609/seed_interruption_dimensions.py'),
    ('python', 'scripts/migrations/202609/seed_noise_latency.py'),
    ('python', 'scripts/migrations/202609/seed_reject_judge.py'),
    ('python', 'scripts/migrations/202609/seed_non_interactive_latency.py'),
    ('python', 'scripts/migrations/202609/seed_xiaoyi_dimensions.py'),
    ('python', 'scripts/migrations/202609/seed_env_sound_judge.py'),
    # ⑫ 时间戳列 DB 级 DEFAULT（INT-47；create_all 新库为 no-op）
    ('python', 'scripts/migrations/202610/add_timestamp_db_defaults.py'),
    # ⑬ Benchmark 排行 4 表 + 指标映射种子（INT-27）
    ('python', 'scripts/migrations/202610/add_benchmark_tables.py'),
    # ⑯ INT-88 残留约束修复（FK / 唯一约束 / 缺失索引）
    ('python', 'scripts/migrations/202610/fix_leftover_foreign_keys_and_indexes.py'),
    # ⑰-⑲ apis 列扩展（RMS-SPL 映射 / output_types / device adapter 三列）
    ('python', 'scripts/migrations/202610/add_api_rms_spl_mappings.py'),
    ('python', 'scripts/migrations/202610/add_api_output_types.py'),
    ('python', 'scripts/migrations/202610/add_api_device_adapter_columns.py'),
    # ㉑ users schema 漂移收敛 + dev 引导用户种子（INT-156）
    ('python', 'scripts/migrations/202610/fix_users_schema_drift.py', '--apply'),
    # ㉒ user_oauth_bindings 表（全新库 create_all 已含，执行为全 SKIP）
    ('python', 'scripts/migrations/202610/add_user_oauth_bindings.py'),
    # INT-1140 access_tokens 表（Access Token + skill/MCP 鉴权令牌；全新库 create_all 已含，执行为全 SKIP）
    ('python', 'scripts/migrations/202610/add_access_tokens_table.py'),
    # ㉓㉔㉕ INT-192 三族维度种子（依赖 seed_voice_llm）
    ('python', 'scripts/migrations/202610/seed_turn_eval.py'),
    ('python', 'scripts/migrations/202610/seed_env_judge.py'),
    ('python', 'scripts/migrations/202610/seed_interruption_v2.py'),
    # INT-299 CUD 操作人列（幂等兜底）
    ('python', 'scripts/migrations/202610/add_operator_columns_int299.py'),
    # INT-141 收藏表 + 删除操作人列
    ('python', 'scripts/migrations/202610/add_trash_operator_and_favorites.py'),
    # published_tasks 算法类型列（INT-303 追溯）
    ('python', 'scripts/migrations/202610/add_published_task_type_algorithm_type.py'),
    # 自定义 OAuth 提供方种子（INT-147 数据行形态）
    ('python', 'scripts/migrations/202610/seed_custom_oauth_providers.py'),
    # ㉘ task_case_relations (task, case, 路由) 唯一索引（INT-604；建索引前先查重）
    ('python', 'scripts/migrations/202610/add_uq_task_case_route_int604.py'),
    # ㊳ test_cases 执行口径派生列（INT-1469/INT-1565）：create_all 只建缺失的表、
    #    不给存量表补列，存量库（真实库 / 隔离库）缺 derived_test_type 时新镜像
    #    建用例/列表即 UndefinedColumn 400。脚本幂等（列/索引存在即 SKIP、回填按
    #    值比对），全新库为全 SKIP；默认 dry-run，引导链必须带 --apply。
    ('python', 'scripts/migrations/202610/add_derived_test_type_int1469.py', '--apply'),
    # ㊴ report_export_records 报告导出历史表（INT-1555；INT-1609 补迁移守卫）：
    #     create_all 只建缺失的表，建库早于 INT-1555 的存量库在引导链里建表自愈；
    #     脚本幂等（表/索引存在即 SKIP），全新库为全 SKIP。
    ('python', 'scripts/migrations/202610/add_report_export_records_int1555.py'),
]


def main():
    if not os.path.isdir(SCRIPTS):
        print(f"[BOOTSTRAP] scripts 卷未挂载: {SCRIPTS} 不存在", flush=True)
        return 1
    if not os.environ.get('DATABASE_URI'):
        print("[BOOTSTRAP] DATABASE_URI 未设置", flush=True)
        return 1

    env = os.environ.copy()
    # 脚本读 BaseConfig.DATABASE_URL（required=True）而非 DATABASE_URI：
    # compose 注入的 DATABASE_URI（迁移脚本口径）同步映射到 DATABASE_URL。
    env.setdefault('DATABASE_URL', env['DATABASE_URI'])
    # BaseConfig 还要求 OSS 凭据（建表路径不触网，仅 import 期校验非空）：
    # 缺省注入与 rustfs 容器一致的本地凭据，显式配置的值优先。
    env.setdefault('OSS_ACCESS_KEY', 'intelligent_audio_test')
    env.setdefault('OSS_SECRET_KEY', 'intelligent_audio_test666')
    # 交互式确认类 seed 脚本（202609 seed_voice_llm 等 6 个的 input() 提示）：
    # stdin 预喂 y 逐条确认（脚本幂等，重复执行安全）。
    confirmations = ['y'] * len(BOOTSTRAP_STEPS)
    # 脚本以「仓库根」为 cwd 运行（README 手工口径：python scripts/migrations/...）。
    # BOOTSTRAP_STEPS 的路径自带 scripts/ 前缀，故 script_root 必须是仓库根：
    #   - 卷挂载形态：scripts/ 挂在 /opt/scripts → 取其父目录 /opt 为根；
    #   - 镜像内兜底：COPY 已把 scripts/ 打入 /app/scripts → 根即 /app。
    # （.dockerignore 只排除 scripts/**/__pycache__，镜像内含脚本副本，卷缺席
    #   也可引导；两者内容同源。）
    if os.path.isdir(os.path.join(SCRIPTS, 'migrations')):
        script_root = os.path.dirname(SCRIPTS)
    else:
        script_root = APP_ROOT
    for step in BOOTSTRAP_STEPS:
        script = step[1]
        if not os.path.isfile(os.path.join(script_root, script)):
            print(f"[BOOTSTRAP] [SKIP] 脚本不存在: {script}", flush=True)
            continue
        print(f"[BOOTSTRAP] ==> {script}", flush=True)
        result = subprocess.run(list(step), cwd=script_root, env=env,
                                input=confirmations.pop(0) + '\n',
                                text=True)
        if result.returncode != 0:
            print(f"[BOOTSTRAP] [FAIL] {script} 退出码 {result.returncode}", flush=True)
            return result.returncode

    print("[BOOTSTRAP] 数据库结构引导完成（全脚本幂等通过）。", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
