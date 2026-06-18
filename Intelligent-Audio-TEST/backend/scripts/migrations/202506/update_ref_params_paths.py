# -*- coding: utf-8 -*-
r"""
将数据库中 referenceParamsPath 的旧路径替换为新路径:
  backend\data\ref_params  ->  static\ref_params
  backend/data/ref_params  ->  static/ref_params

使用方法：
    python backend/scripts/migrations/202506/update_ref_params_paths.py
    python backend/scripts/migrations/202506/update_ref_params_paths.py --dry-run
"""
import json
import os
import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

def replace_old_path(path: str) -> str:
    """
    将旧路径替换为新的相对路径: static\\ref_params\\<filename>
    与 Config.STATIC_BASE_PATH (= 'static') 保持一致。
    """
    if 'ref_params' not in path:
        return path
    # 提取文件名 (最后一段)
    normalized = path.replace('\\', '/')
    filename = normalized.rsplit('/', 1)[-1]
    # 新路径: 相对路径，与 STATIC_BASE_PATH 一致
    return os.path.join('static', 'ref_params', filename)

def main():
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("=== DRY-RUN MODE ===")

    eng = create_engine(POSTGRES_URI)
    conn = eng.connect()
    trans = conn.begin()

    try:
        rows = conn.execute(text(
            "SELECT id, config FROM test_cases "
            "WHERE deleted = false AND config::text LIKE '%referenceParamsPath%'"
        )).fetchall()

        print(f"Found {len(rows)} cases with referenceParamsPath")

        if rows:
            for i, row in enumerate(rows[:3]):
                cfg = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                for rd in cfg.get('rounds', []):
                    if isinstance(rd, dict) and rd.get('referenceParamsPath'):
                        print(f"  Sample[{i}] id={row[0]}, path={repr(rd['referenceParamsPath'])}")

        updated = 0
        errors = 0
        for row in rows:
            case_id = row[0]
            config = row[1] if isinstance(row[1], dict) else json.loads(row[1])
            rounds = config.get('rounds', [])
            changed = False

            for rd in rounds:
                if not isinstance(rd, dict):
                    continue
                path = rd.get('referenceParamsPath', '')
                if not path:
                    continue
                new_path = replace_old_path(path)

                if new_path != path:
                    print(f"  [{case_id}] round {rd.get('roundNumber','?')}:")
                    print(f"    OLD: {path}")
                    print(f"    NEW: {new_path}")
                    rd['referenceParamsPath'] = new_path
                    changed = True

            if changed:
                savepoint = conn.begin_nested()
                try:
                    updated += 1
                    if not dry_run:
                        conn.execute(
                            text("UPDATE test_cases SET config = :cfg WHERE id = :cid"),
                            {'cfg': json.dumps(config, ensure_ascii=False), 'cid': case_id}
                        )
                    savepoint.commit()
                except Exception as e:
                    savepoint.rollback()
                    errors += 1
                    print(f"  [FAIL] {case_id}: {e}")

        if dry_run:
            trans.rollback()
            print(f"\n[DRY-RUN] Would update {updated} cases.")
        else:
            trans.commit()
            print(f"\nUpdated {updated} cases in database.")

        if errors > 0:
            print(f"[WARN] {errors} cases failed to update")

    except Exception as e:
        trans.rollback()
        print(f"\n[ERROR] 迁移失败，已回滚: {e}")
        raise
    finally:
        conn.close()
        eng.dispose()


if __name__ == '__main__':
    main()
