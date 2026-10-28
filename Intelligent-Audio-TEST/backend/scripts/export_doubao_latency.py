# -*- coding: utf-8 -*-
"""
一键导出豆包合成音频 / 时延分析所需的数据。

导出内容（按 task_id）：
  1. 每个 test_result 的 result_data.json（含 raw_results_list[*].raw_results.latency_ms）
  2. 同目录下的 *_user_synth.wav / *_ai_aligned.wav / *_ai.wav 等所有 wav
  3. manifest.json          —— 结果清单、文件清单、缺失项
  4. latency_summary.json   —— 逐轮时延 + 均值/最小/最大
  5. logs.txt（可选）        —— task 相关日志

用法（在 Intelligent-Audio-TEST 根目录执行）：
  python backend/scripts/export_doubao_latency.py --task-id 123
  python backend/scripts/export_doubao_latency.py --task-id 123 --case-id tc-xxx
  python backend/scripts/export_doubao_latency.py --task-id 123 --device-sn EP0110...
  python backend/scripts/export_doubao_latency.py --task-id 123 --with-logs
  python backend/scripts/export_doubao_latency.py --task-id 123 --db-uri "postgresql://..."
  python backend/scripts/export_doubao_latency.py --task-id 123 --output D:/tmp/doubao_123.zip

说明：
  - result_data_path 是相对 STATIC_BASE_PATH 的路径；脚本会自动拼绝对路径。
  - 如果 result_data_path 为空/文件不存在，会尝试
    STATIC_BASE_PATH/case_result/<task_id>/<case_id>/<device_sn>/result_data.json，
    再退化为把数据库里的 result_data 存成 result_data_db.json。
  - 不改数据库、不改任务，只读 + 复制。
"""

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

from sqlalchemy import create_engine, text  # noqa: E402

try:
    from backend.config.config import Config

    _DEFAULT_DB_URI = Config.SQLALCHEMY_DATABASE_URI
    _DEFAULT_STATIC_BASE = Path(Config.STATIC_BASE_PATH)
except Exception:
    _DEFAULT_DB_URI = os.environ.get(
        "DATABASE_URI",
        "postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test",
    )
    _DEFAULT_STATIC_BASE = Path(os.environ.get("STATIC_BASE_PATH", r"D:\00_static\static"))

_CST = timezone(timedelta(hours=8))


def _now_cst():
    return datetime.now(_CST)


def _safe_name(value):
    text_value = str(value if value is not None else "unknown")
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", text_value).strip("_") or "unknown"


def _mask_uri(uri):
    return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", str(uri))


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _extract_rounds(data):
    """从 result_data.json 里取 raw_results_list；兼容不同层级。"""
    if not isinstance(data, dict):
        if isinstance(data, list):
            return data
        return []

    for key in ("raw_results_list", "raw_results", "rounds"):
        value = data.get(key)
        if isinstance(value, list):
            return value

    # 有些历史结果把单轮 raw_results 直接放在顶层
    if isinstance(data.get("latency_ms"), dict) or data.get("first_frame_ms"):
        return [data]
    return []


def _extract_round_latency(item, index):
    """把一轮结果里的 latency_ms / first_frame_ms 归一化。"""
    if not isinstance(item, dict):
        item = {"raw_results": item}

    raw = item.get("raw_results") if isinstance(item.get("raw_results"), dict) else item
    latency = raw.get("latency_ms") if isinstance(raw.get("latency_ms"), dict) else {}
    if not latency and isinstance(item.get("latency_ms"), dict):
        latency = item["latency_ms"]

    first_frame_ms = _to_int(
        raw.get("first_frame_ms")
        or item.get("first_frame_ms")
        or latency.get("ai_start_ms")
    )
    start_ms = _to_int(
        raw.get("start_ms")
        or item.get("start_ms")
        or latency.get("question_start_ms")
    )
    end_ms = _to_int(
        raw.get("end_ms")
        or item.get("end_ms")
        or latency.get("question_end_ms")
    )

    question_to_ai_ms = _to_int(latency.get("question_to_ai_ms"))
    question_end_to_ai_ms = _to_int(latency.get("question_end_to_ai_ms"))

    # 兼容旧结果：没有 latency_ms 时用 first_frame_ms/start_ms/end_ms 现算
    if question_to_ai_ms is None and first_frame_ms and start_ms:
        question_to_ai_ms = first_frame_ms - start_ms
    if question_end_to_ai_ms is None and first_frame_ms and end_ms:
        question_end_to_ai_ms = first_frame_ms - end_ms

    return {
        "round": item.get("round_number") or item.get("_round") or index + 1,
        "question_start_ms": start_ms,
        "question_end_ms": end_ms,
        "ai_start_ms": first_frame_ms,
        "question_to_ai_ms": question_to_ai_ms,
        "question_end_to_ai_ms": question_end_to_ai_ms,
        "played_count": _to_int(latency.get("played_count")),
        "has_latency_ms": bool(latency),
    }


def _stats(values):
    clean = [v for v in values if isinstance(v, int)]
    if not clean:
        return {"count": 0, "avg_ms": None, "min_ms": None, "max_ms": None}
    return {
        "count": len(clean),
        "avg_ms": round(sum(clean) / len(clean), 1),
        "min_ms": min(clean),
        "max_ms": max(clean),
    }


def _resolve_result_path(row, static_base):
    result_data_path = row.get("result_data_path")
    if result_data_path:
        p = Path(result_data_path)
        if not p.is_absolute():
            p = static_base / result_data_path
        if p.is_file():
            return p, "file"

    fallback = (
        static_base
        / "case_result"
        / _safe_name(row.get("task_id"))
        / _safe_name(row.get("test_case_id"))
        / _safe_name(row.get("device_sn"))
        / "result_data.json"
    )
    if fallback.is_file():
        return fallback, "fallback"

    return None, "missing"


def _copy_result_files(src_path, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []

    if src_path and src_path.is_file():
        target = dest_dir / "result_data.json"
        shutil.copy2(src_path, target)
        copied.append(target.name)

        for wav in sorted(src_path.parent.glob("*.wav")):
            target_wav = dest_dir / wav.name
            shutil.copy2(wav, target_wav)
            copied.append(target_wav.name)

    return copied


def _query_results(conn, args):
    where = ["tr.task_id = :task_id", "COALESCE(tr.deleted, false) = false"]
    params = {"task_id": args.task_id}

    if args.case_id:
        where.append("tr.test_case_id = :case_id")
        params["case_id"] = args.case_id
    if args.device_sn:
        where.append("d.serial_number = :device_sn")
        params["device_sn"] = args.device_sn

    sql = text(
        f"""
        SELECT tr.id AS result_id,
               tr.task_id,
               tr.test_case_id,
               tr.device_id,
               d.serial_number AS device_sn,
               d.name AS device_name,
               tr.result_data_path,
               tr.result_data,
               tr.algorithm_result,
               tr.response_time,
               tr.created_at
        FROM test_results tr
        LEFT JOIN devices d ON d.id = tr.device_id
        WHERE {' AND '.join(where)}
        ORDER BY tr.created_at ASC, tr.id ASC
        """
    )
    return [dict(r._mapping) for r in conn.execute(sql, params).fetchall()]


def _query_logs(conn, args):
    where = ["task_id = :task_id"]
    params = {"task_id": args.task_id}
    if args.case_id:
        where.append("test_case_id = :case_id")
        params["case_id"] = args.case_id

    sql = text(
        f"""
        SELECT time, level, module, test_case_id, content
        FROM logs
        WHERE {' AND '.join(where)}
        ORDER BY time ASC, id ASC
        """
    )
    return conn.execute(sql, params).fetchall()


def main():
    parser = argparse.ArgumentParser(description="导出豆包合成音频与时延分析数据")
    parser.add_argument("--task-id", type=int, required=True, help="任务 ID")
    parser.add_argument("--case-id", default=None, help="只导出指定用例（可选）")
    parser.add_argument("--device-sn", default=None, help="只导出指定设备 SN（可选）")
    parser.add_argument("--db-uri", default=_DEFAULT_DB_URI, help="数据库连接串，默认取 Config")
    parser.add_argument("--static-base", default=str(_DEFAULT_STATIC_BASE),
                        help="STATIC_BASE_PATH，默认取 Config")
    parser.add_argument("--output", default=None,
                        help="输出 zip 路径；默认 exports/doubao_latency_<task>_<时间>.zip")
    parser.add_argument("--with-logs", action="store_true", help="同时导出该任务的 logs.txt")
    args = parser.parse_args()

    static_base = Path(args.static_base).expanduser().resolve()
    if not static_base.exists():
        print(f"[ERROR] STATIC_BASE_PATH 不存在: {static_base}")
        return 1

    stamp = _now_cst().strftime("%Y%m%d_%H%M%S")
    if args.output:
        zip_path = Path(args.output).expanduser().resolve()
        if zip_path.suffix.lower() != ".zip":
            zip_path = zip_path.with_suffix(".zip")
    else:
        zip_path = Path.cwd() / "exports" / f"doubao_latency_{args.task_id}_{stamp}.zip"
    out_dir = zip_path.with_suffix("")

    engine = create_engine(args.db_uri)
    with engine.connect() as conn:
        rows = _query_results(conn, args)
        logs = _query_logs(conn, args) if args.with_logs else None

    if not rows:
        print(f"[ERROR] task_id={args.task_id} 没有可导出的 test_results")
        return 1

    manifest = {
        "task_id": args.task_id,
        "case_id": args.case_id,
        "device_sn": args.device_sn,
        "exported_at": _now_cst().isoformat(),
        "static_base": str(static_base),
        "db_uri": _mask_uri(args.db_uri),
        "results": [],
        "warnings": [],
    }
    latency_entries = []

    for row in rows:
        result_id = row.get("result_id")
        case_id = row.get("test_case_id")
        device_sn = row.get("device_sn")
        result_dir = out_dir / f"case_{_safe_name(case_id)}" / f"result_{result_id}"

        src_path, src_kind = _resolve_result_path(row, static_base)
        copied = _copy_result_files(src_path, result_dir)

        result_data = None
        if src_path:
            result_data = _read_json(src_path)
        if result_data is None and isinstance(row.get("result_data"), (dict, list)):
            result_data = row.get("result_data")
            _write_json(result_dir / "result_data_db.json", result_data)
            copied.append("result_data_db.json")
            src_kind = "database"

        if result_data is None and isinstance(row.get("algorithm_result"), (dict, list)):
            result_data = {"algorithm_result": row.get("algorithm_result")}
            _write_json(result_dir / "algorithm_result_db.json", result_data)
            copied.append("algorithm_result_db.json")
            src_kind = "database_algorithm_result"

        entry = {
            "result_id": result_id,
            "case_id": case_id,
            "device_id": row.get("device_id"),
            "device_sn": device_sn,
            "device_name": row.get("device_name"),
            "response_time": row.get("response_time"),
            "created_at": row.get("created_at"),
            "result_data_path": row.get("result_data_path"),
            "result_data_source": src_kind,
            "copied_files": copied,
            "rounds": [],
        }

        if result_data is None:
            entry["error"] = "result_data.json 不存在，数据库也无 result_data"
            manifest["warnings"].append(f"result_id={result_id}: result_data 缺失")
            manifest["results"].append(entry)
            continue

        for idx, item in enumerate(_extract_rounds(result_data)):
            round_info = _extract_round_latency(item, idx)
            entry["rounds"].append(round_info)
            latency_entries.append({
                "result_id": result_id,
                "case_id": case_id,
                "device_sn": device_sn,
                **round_info,
            })

        manifest["results"].append(entry)

    summary = {
        "task_id": args.task_id,
        "exported_at": manifest["exported_at"],
        "sample_count": len(latency_entries),
        "question_end_to_ai_ms": _stats([x["question_end_to_ai_ms"] for x in latency_entries]),
        "question_to_ai_ms": _stats([x["question_to_ai_ms"] for x in latency_entries]),
        "samples": latency_entries,
        "notes": [
            "question_end_to_ai_ms = ai_start_ms - question_end_ms，问题播完到 AI 起声",
            "question_to_ai_ms = ai_start_ms - question_start_ms，问题开始到 AI 起声",
            "时间戳来自服务器 sounddevice 播放调用，不是扬声器实际出声；真实声学时延需 loopback/参考麦",
            "没有 latency_ms 的旧结果会尝试用 first_frame_ms/start_ms/end_ms 现算",
        ],
    }

    _write_json(out_dir / "manifest.json", manifest)
    _write_json(out_dir / "latency_summary.json", summary)

    if logs is not None:
        log_path = out_dir / "logs.txt"
        with open(log_path, "w", encoding="utf-8") as f:
            for log in logs:
                f.write(
                    f"{log.time}\t{log.level}\t{log.module}\t"
                    f"{log.test_case_id or '-'}\t{log.content}\n"
                )
        manifest["log_file"] = log_path.name
        _write_json(out_dir / "manifest.json", manifest)

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out_dir.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(out_dir))

    stats = summary["question_end_to_ai_ms"]
    print("=" * 72)
    print(f"导出完成: {zip_path}")
    print(f"解压目录: {out_dir}")
    print(f"结果行数: {len(rows)}  时延样本: {summary['sample_count']}")
    if stats["count"]:
        print(f"问题播完→AI起声: 均值 {stats['avg_ms']} ms  "
              f"最小 {stats['min_ms']} ms  最大 {stats['max_ms']} ms  "
              f"({stats['count']} 轮)")
    else:
        print("没有可计算的 question_end_to_ai_ms（检查 latency_ms / AI 是否回复）")
    if manifest["warnings"]:
        print("警告:")
        for w in manifest["warnings"]:
            print("  -", w)
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
