# -*- coding: utf-8 -*-
"""
迁移脚本：将 audios.file_path 中的 Windows 反斜杠 (\\) 统一替换为正斜杠 (/)

背景：
    os.path.join / os.path.normpath 在 Windows 上会生成反斜杠路径，
    导致 PostgreSQL LIKE 查询、前端路径拼接等场景需要额外处理。
    本脚本将存量数据统一为正斜杠，后续新上传的音频也应在写入时规范化。

用法：
    cd backend/scripts/migrations/202607
    python normalize_file_paths.py           # 预览（dry-run）
    python normalize_file_paths.py --apply   # 实际执行
"""
import os
import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)


def main():
    apply = '--apply' in sys.argv

    print("=" * 60)
    print("audios.file_path 斜杠规范化迁移")
    print(f"模式: {'实际执行 (--apply)' if apply else '预览 (dry-run)'}")
    print("=" * 60)

    engine = create_engine(POSTGRES_URI)

    with engine.connect() as conn:
        # 1. 统计需要修复的记录数
        #    用 position() 函数检测反斜杠，避免 LIKE 转义歧义
        result = conn.execute(text(
            "SELECT COUNT(*) FROM audios WHERE POSITION('\\' IN file_path) > 0"
        ))
        affected = result.scalar()

        result = conn.execute(text("SELECT COUNT(*) FROM audios"))
        total = result.scalar()

        print(f"总记录数: {total}")
        print(f"含反斜杠的记录数: {affected}")

        if affected == 0:
            print("无需修复，所有 file_path 已使用正斜杠。")
            return

        # 2. 抽样展示待修复数据
        result = conn.execute(text(
            "SELECT id, file_path FROM audios "
            "WHERE POSITION('\\' IN file_path) > 0 LIMIT 5"
        ))
        samples = result.fetchall()
        print("\n待修复样本（前 5 条）:")
        for row in samples:
            print(f"  id={row[0]}  file_path={row[1]}")

        if not apply:
            print(f"\n[dry-run] 将修复 {affected} 条记录，加 --apply 参数实际执行。")
            return

    # 3. 执行修复：用 replace() 函数统一为正斜杠
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE audios SET file_path = REPLACE(file_path, '\\', '/') "
            "WHERE POSITION('\\' IN file_path) > 0"
        ))
        updated = result.rowcount
        print(f"\n已修复 {updated} 条记录")

    # 4. 验证
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM audios WHERE POSITION('\\' IN file_path) > 0"
        ))
        remaining = result.scalar()
        print(f"验证：剩余含反斜杠的记录数: {remaining}")

    print("\n迁移完成!")


if __name__ == '__main__':
    main()
