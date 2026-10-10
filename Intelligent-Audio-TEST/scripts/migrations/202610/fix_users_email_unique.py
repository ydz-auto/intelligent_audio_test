# -*- coding: utf-8 -*-
"""
修复 users_email_key 空邮箱撞唯一约束（INT-84）
=============================================================================

问题：
  历史库 users.email 带 UNIQUE 约束（users_email_key，ORM 未声明的历史遗留），
  email='' 的空串占位后，第二个空邮箱用户（自助注册 / e2e 建号未传 email）
  INSERT 必撞唯一约束而失败。

修复（三步，全部幂等，可安全重复执行）：
  ① 数据兜底：存量 email 空串/纯空白 归一化为 NULL；
  ② 删除历史唯一约束 users_email_key（DROP CONSTRAINT 会连带其背后索引）；
  ③ 建部分唯一索引：仅非空 email 唯一（NULL 与 '' 均不参与唯一性检查）。

应用层（auth_service UserRepository._normalize_email）已同步把空 email 落 NULL，
本迁移保证既有库结构与数据对齐；全新库经 create_all_tables 建表后执行本脚本
为 no-op（无该约束则跳过）。

用法：
    python scripts/migrations/202610/fix_users_email_unique.py           # 预览
    python scripts/migrations/202610/fix_users_email_unique.py --apply   # 实际执行

⚠️ 先停服务再执行（README 执行须知：ALTER TABLE 需 ACCESS EXCLUSIVE 锁）。
"""
import os
import sys

from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

OLD_CONSTRAINT = 'users_email_key'
NEW_INDEX = 'uq_users_email'


def main():
    apply = '--apply' in sys.argv

    print("=" * 60)
    print("users_email 唯一约束修复（空邮箱归一化 + 部分唯一索引）")
    print(f"模式: {'实际执行 (--apply)' if apply else '预览 (dry-run)'}")
    print("=" * 60)

    engine = create_engine(POSTGRES_URI)

    with engine.connect() as conn:
        # ---- ① 存量空邮箱数据兜底 ----
        empty_rows = conn.execute(text(
            "SELECT count(*) FROM users "
            "WHERE email IS NOT NULL AND btrim(email) = ''"
        )).scalar()
        print(f"\n① 空邮箱存量行: {empty_rows} 条"
              f"{'（UPDATE ... SET email = NULL）' if empty_rows else '（无需处理）'}")
        if apply and empty_rows:
            conn.execute(text(
                "UPDATE users SET email = NULL "
                "WHERE email IS NOT NULL AND btrim(email) = ''"
            ))
            conn.commit()
            print("  [OK] 空邮箱已归一化为 NULL")

        # ---- ② 删除历史唯一约束 ----
        exists = conn.execute(text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = :name AND conrelid = 'users'::regclass"
        ), {'name': OLD_CONSTRAINT}).fetchone()
        if exists:
            print(f"\n② 旧约束 {OLD_CONSTRAINT}: 存在，需删除"
                  f"{'（已执行）' if apply else ''}")
            if apply:
                conn.execute(text(
                    f"ALTER TABLE users DROP CONSTRAINT {OLD_CONSTRAINT}"))
                conn.commit()
                print("  [OK] 已删除旧约束（连带其唯一索引）")
        else:
            print(f"\n② 旧约束 {OLD_CONSTRAINT}: 不存在（已迁移过或全新库）")

        # ---- ③ 非空 email 部分唯一索引 ----
        idx_exists = conn.execute(text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :name"
        ), {'name': NEW_INDEX}).fetchone()
        if idx_exists:
            print(f"\n③ 目标索引 {NEW_INDEX}: 已存在（幂等跳过）")
        else:
            print(f"\n③ 目标: CREATE UNIQUE INDEX {NEW_INDEX} ON users (email) "
                  f"WHERE email IS NOT NULL AND email <> ''")
            if apply:
                conn.execute(text(
                    f"CREATE UNIQUE INDEX {NEW_INDEX} ON users (email) "
                    f"WHERE email IS NOT NULL AND email <> ''"
                ))
                conn.commit()
                print("  [OK] 已创建部分唯一索引")

    if not apply:
        print("\n" + "=" * 60)
        print("预览完成，加上 --apply 参数执行实际迁移")
    print("\n完成！")


if __name__ == '__main__':
    main()
