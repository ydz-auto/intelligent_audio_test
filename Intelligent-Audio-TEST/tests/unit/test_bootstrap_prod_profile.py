# -*- coding: utf-8 -*-
"""生产引导档位（DB_BOOTSTRAP_PROFILE=prod）：只跑结构 DDL，默认拒绝 seed / 数据迁移。

背景：生产库的算法参数、评估参数、设备参数与映射是金标，不能被 seed 脚本或
数据迁移改写。引导链默认是 dev 口径（全链），生产必须显式切到 prod 档。

本文件钉死：
1. dev（缺省）仍执行完整 BOOTSTRAP_STEPS；
2. prod 只执行 PROD_DDL_SCRIPTS 白名单（默认拒绝）；
3. prod 必须跳过 seed_*、restore_api_algorithm_level、设备/音箱/实验室数据迁移；
4. add_param_profiles_scope 在 prod 只带 --ddl-only（建表不搬数据）；
5. ANALYZE 仍是 prod 档最后一步；
6. 白名单里的脚本必须都在引导链里（防拼写错误导致静默跳过）。
"""
import importlib.util
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')

# 生产绝对不允许执行的数据脚本（seed / 数据迁移 / 回填）
# 例外：seed_rbac 属系统基线（权限点/角色），已进 prod 白名单
PROD_FORBIDDEN = {
    'scripts/migrations/202609/seed_voice_llm.py',
    'scripts/migrations/202609/seed_interruption_dimensions.py',
    'scripts/migrations/202609/seed_noise_latency.py',
    'scripts/migrations/202609/seed_reject_judge.py',
    'scripts/migrations/202609/seed_non_interactive_latency.py',
    'scripts/migrations/202609/seed_xiaoyi_dimensions.py',
    'scripts/migrations/202609/seed_env_sound_judge.py',
    'scripts/migrations/202610/seed_turn_eval.py',
    'scripts/migrations/202610/seed_env_judge.py',
    'scripts/migrations/202610/seed_interruption_v2.py',
    'scripts/migrations/202610/seed_custom_oauth_providers.py',
    'scripts/migrations/202610/seed_voice_llm_device_output_int1748.py',
    'scripts/migrations/202610/seed_api_eval_mapping_int1746.py',
    'scripts/migrations/202610/fix_voice_llm_reference_params_definitions.py',
    'scripts/migrations/202610/backfill_result_type_channel_20261029.py',
    'scripts/migrations/202611/migrate_device_params_to_profiles.py',
    'scripts/migrations/202611/associate_devices_to_default_lab.py',
    'scripts/migrations/202611/seed_playback_speaker_groups.py',
    'scripts/migrations/202611/normalize_report_status_int2238.py',
    'scripts/migrations/202611/restore_api_algorithm_level.py',
}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_bootstrap = _load(_BOOTSTRAP_PATH, 'prod_profile_db_bootstrap')


def test_dev_profile_runs_full_chain(monkeypatch):
    monkeypatch.delenv('DB_BOOTSTRAP_PROFILE', raising=False)
    assert _bootstrap.bootstrap_profile() == 'dev'
    assert _bootstrap.select_steps() == list(_bootstrap.BOOTSTRAP_STEPS)


def test_prod_profile_is_ddl_only_default_deny(monkeypatch):
    monkeypatch.setenv('DB_BOOTSTRAP_PROFILE', 'prod')
    scripts = [step[1] for step in _bootstrap.select_steps()]

    missing = PROD_FORBIDDEN & set(scripts)
    assert not missing, f'生产档仍包含数据脚本: {sorted(missing)}'
    assert 'scripts/create_all_tables.py' in scripts
    assert 'scripts/migrations/202611/add_param_change_history.py' in scripts
    assert 'scripts/migrations/202611/add_device_id_scope.py' in scripts
    assert scripts[-1].endswith('analyze_stale_statistics_int1741.py')


def test_prod_includes_rbac_seed_before_bootstrap_user(monkeypatch):
    """RBAC 属系统基线（130 权限 / 5 角色），必须进 prod 档，
    且排在 fix_users_schema_drift 之前——否则 roles 缺失、引导管理员被跳过。"""
    monkeypatch.setenv('DB_BOOTSTRAP_PROFILE', 'prod')
    scripts = [step[1] for step in _bootstrap.select_steps()]
    assert 'scripts/migrations/202608/seed_rbac.py' in scripts
    assert scripts.index('scripts/migrations/202608/seed_rbac.py') < \
        scripts.index('scripts/migrations/202610/fix_users_schema_drift.py')


def test_prod_user_email_unique_runs_with_apply(monkeypatch):
    """fix_users_email_unique 默认 dry-run，prod 档必须换参数为 --apply。"""
    monkeypatch.setenv('DB_BOOTSTRAP_PROFILE', 'prod')
    step = next(
        item for item in _bootstrap.select_steps()
        if item[1] == 'scripts/migrations/202610/fix_users_email_unique.py'
    )
    assert step[2:] == ('--apply',)


def test_prod_runs_param_profiles_migration_as_ddl_only(monkeypatch):
    monkeypatch.setenv('DB_BOOTSTRAP_PROFILE', 'prod')
    step = next(
        item for item in _bootstrap.select_steps()
        if item[1] == 'scripts/migrations/202610/add_param_profiles_scope.py'
    )
    assert step[2:] == ('--apply', '--ddl-only')


def test_prod_allowlist_has_no_typos(monkeypatch):
    monkeypatch.setenv('DB_BOOTSTRAP_PROFILE', 'prod')
    chain = {step[1] for step in _bootstrap.BOOTSTRAP_STEPS}
    unknown = _bootstrap.PROD_DDL_SCRIPTS - chain
    assert not unknown, f'白名单脚本不在引导链中（疑似拼写错误）: {sorted(unknown)}'


# 2026-11-02 生产热备副本演练查出的结构缺口（create_all 不给已有表补列）：
# 新代码读这些列会 UndefinedColumn，dev / prod 两档都必须补齐。
SCHEMA_GAP_SCRIPTS = {
    'scripts/migrations/202610/add_users_display_name.py',
    'scripts/migrations/202610/add_api_proxy_columns.py',
    'scripts/migrations/202610/add_evaluation_deleted_by_int841.py',
    'scripts/migrations/202610/add_tag_operator_columns_int840.py',
    'scripts/migrations/202610/add_evaluation_strategies_int590.py',
    'scripts/migrations/202610/add_test_result_reviews_int340.py',
    'scripts/migrations/202610/add_result_excluded_columns_int305.py',
    # 2026-11-03 干净副本实测：表存在但种子 0 行 / 索引缺失
    'scripts/migrations/202610/add_system_options_table.py',
    'scripts/migrations/202610/fix_users_email_unique.py',
    'scripts/migrations/202610/add_logs_query_indexes_int1468.py',
    'scripts/migrations/202610/add_test_cases_group_id_index_int1470.py',
}


def test_schema_gap_scripts_run_in_both_profiles():
    chain = {step[1] for step in _bootstrap.BOOTSTRAP_STEPS}
    assert not (SCHEMA_GAP_SCRIPTS - chain), \
        f'引导链缺少存量库补列脚本: {sorted(SCHEMA_GAP_SCRIPTS - chain)}'
    assert not (SCHEMA_GAP_SCRIPTS - _bootstrap.PROD_DDL_SCRIPTS), \
        f'prod 白名单缺少存量库补列脚本: {sorted(SCHEMA_GAP_SCRIPTS - _bootstrap.PROD_DDL_SCRIPTS)}'


def test_bootstrap_step_order_constraints():
    """演练实测的顺序硬约束：错了整链失败。"""
    chain = [step[1] for step in _bootstrap.BOOTSTRAP_STEPS]
    idx = {script: i for i, script in enumerate(chain)}

    def before(first, second):
        assert idx[first] < idx[second], f'{first} 必须在 {second} 之前'

    before('scripts/migrations/202610/add_visibility_columns_int423.py',
           'scripts/migrations/202608/remove_foreign_keys_and_soft_delete.py')
    before('scripts/migrations/202610/add_param_profiles_scope.py',
           'scripts/migrations/202611/add_device_id_scope.py')
    before('scripts/migrations/202610/add_param_profiles_scope.py',
           'scripts/migrations/202611/add_device_param_bindings.py')
    # RBAC 种子依赖 ⑫ 补齐 permissions/roles 的 created_at DB 默认值，
    # 又必须先于 fix_users_schema_drift（后者依赖 roles 种子管理员）
    before('scripts/migrations/202610/add_timestamp_db_defaults.py',
           'scripts/migrations/202608/seed_rbac.py')
    before('scripts/migrations/202608/seed_rbac.py',
           'scripts/migrations/202610/fix_users_schema_drift.py')
    assert chain[-1].endswith('analyze_stale_statistics_int1741.py')
