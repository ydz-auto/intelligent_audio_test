# -*- coding: utf-8 -*-
"""临时脚本：探测并清空鸿蒙设备上的所有闹钟/提醒。

使用方式:
    python scripts/clear_alarms_test.py                  # 自动选择第一台设备
    python scripts/clear_alarms_test.py <device_sn>      # 指定设备 SN
"""
import subprocess
import sys


CLOCK_BUNDLE = 'com.huawei.hmos.clock'
NOTIFICATION_DB = '/data/service/el1/public/notification/notification.db'


def run_hdc(device_sn: str, args: list[str], check: bool = False) -> str:
    """执行 hdc 命令并返回输出。"""
    cmd = ['hdc', '-t', device_sn, 'shell'] + args
    print(f"\n>>> {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, encoding='utf-8', check=check,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        output = (result.stdout or '') + (result.stderr or '')
        print(output)
        return output
    except subprocess.CalledProcessError as e:
        print(f"[命令失败] {e.output}")
        return e.output or ''
    except FileNotFoundError:
        print("[错误] 未找到 hdc 命令，请确认 hdc 已加入 PATH")
        sys.exit(1)


def list_devices() -> list[str]:
    """列出所有在线设备 SN。"""
    try:
        output = subprocess.check_output(
            ['hdc', 'list', 'targets'], encoding='utf-8', stderr=subprocess.STDOUT
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[错误] 获取设备列表失败: {e}")
        return []
    devices = []
    for line in output.strip().splitlines():
        line = line.strip()
        if line and '[Empty]' not in line:
            devices.append(line)
    return devices


def show_clock_data(device_sn: str):
    """查看时钟 App 数据目录现状。"""
    print("\n" + "=" * 60)
    print("步骤 1: 查看时钟 App 数据现状")
    print("=" * 60)
    run_hdc(device_sn, ['ls', '-lR', f'/data/app/el2/100/base/{CLOCK_BUNDLE}'])


def clear_clock_app_data(device_sn: str):
    """使用 bm clean 清除时钟 App 数据。"""
    print("\n" + "=" * 60)
    print(f"步骤 2: 清除时钟 App 数据 (bm clean -n {CLOCK_BUNDLE} -d)")
    print("=" * 60)
    run_hdc(device_sn, ['bm', 'clean', '-n', CLOCK_BUNDLE, '-d'])
    # 也清 cache
    run_hdc(device_sn, ['bm', 'clean', '-n', CLOCK_BUNDLE, '-c'])


def query_notification_db(device_sn: str):
    """查看 notification.db 中的 reminder 相关表。"""
    print("\n" + "=" * 60)
    print("步骤 3: 查看 notification.db 中的提醒数据")
    print("=" * 60)

    # 检查 sqlite3 是否可用
    out = run_hdc(device_sn, ['which', 'sqlite3'])
    if 'not found' in out or not out.strip():
        print("[跳过] 设备上无 sqlite3 命令，无法直接查询数据库")
        print("  将尝试直接删除 notification.db 的 WAL/SHM 并重启服务")
        return False

    # 列出所有表
    print("\n--- notification.db 所有表 ---")
    run_hdc(device_sn, [
        'sqlite3', NOTIFICATION_DB, '.tables'
    ])

    # 查找包含 reminder/alarm 的表
    print("\n--- 查找 reminder 相关表结构 ---")
    run_hdc(device_sn, [
        'sqlite3', NOTIFICATION_DB,
        "SELECT name FROM sqlite_master WHERE type='table' AND "
        "(name LIKE '%reminder%' OR name LIKE '%alarm%');"
    ])

    # 查看各 reminder 表记录数
    tables = ['reminder_base', 'reminder_alarm', 'reminder_calendar',
              'reminder_timer', 'reminder_state']
    for table in tables:
        print(f"\n--- {table} 记录数 ---")
        run_hdc(device_sn, [
            'sqlite3', NOTIFICATION_DB,
            f"SELECT count(*) FROM {table};"
        ])
    return True


def clear_reminder_from_db(device_sn: str, has_sqlite: bool):
    """清空 notification.db 中的提醒记录。"""
    print("\n" + "=" * 60)
    print("步骤 4: 清空 notification.db 中的提醒记录")
    print("=" * 60)

    if has_sqlite:
        # 清空所有 reminder 相关表
        tables = ['reminder_base', 'reminder_alarm', 'reminder_calendar',
                  'reminder_timer', 'reminder_state']
        for table in tables:
            print(f"\n--- 清空 {table} 表 ---")
            run_hdc(device_sn, [
                'sqlite3', NOTIFICATION_DB,
                f"DELETE FROM {table};"
            ])
            # 确认清空
            run_hdc(device_sn, [
                'sqlite3', NOTIFICATION_DB,
                f"SELECT count(*) FROM {table};"
            ])
    else:
        # 无 sqlite3，直接删 db 文件让服务重建
        print("[备选] 直接删除 notification.db 及相关文件")
        run_hdc(device_sn, ['rm', '-f', NOTIFICATION_DB])
        run_hdc(device_sn, ['rm', '-f', NOTIFICATION_DB + '-wal'])
        run_hdc(device_sn, ['rm', '-f', NOTIFICATION_DB + '-shm'])
        run_hdc(device_sn, ['rm', '-f', NOTIFICATION_DB + '-dwr'])
        run_hdc(device_sn, ['rm', '-f', NOTIFICATION_DB + '-compare'])


def restart_notification_service(device_sn: str):
    """重启通知服务使清理生效。"""
    print("\n" + "=" * 60)
    print("步骤 5: 重启通知服务")
    print("=" * 60)

    # 鸿蒙通知服务由 foundation 进程管理，无法直接 kill
    # 用 sacmds 重启 ans (Advanced Notification Service)
    run_hdc(device_sn, ['sa-cmd', 'list'])
    # 尝试 kill notification 相关进程（精准匹配）
    out = run_hdc(device_sn, ['ps', '-ef'])
    for line in out.splitlines():
        low = line.lower()
        if 'notification' in low and 'foundation' not in low:
            # 提取进程名
            parts = line.split()
            if len(parts) > 8:
                proc_name = parts[7]
                print(f"  发现通知进程: {proc_name}，尝试 kill")
                run_hdc(device_sn, ['killall', proc_name])

    # 强制停止时钟 App 让它重新加载
    run_hdc(device_sn, ['aa', 'force-stop', CLOCK_BUNDLE])


def main():
    args = sys.argv[1:]
    if args:
        device_sn = args[0]
    else:
        devices = list_devices()
        if not devices:
            print("[错误] 未找到在线鸿蒙设备，请检查 hdc list targets")
            return
        device_sn = devices[0]
        print(f"自动选择设备: {device_sn}")

    print(f"\n目标设备: {device_sn}")

    # 1. 查看现状
    show_clock_data(device_sn)

    # 2. 清除时钟 App 数据
    clear_clock_app_data(device_sn)

    # 3. 查看 notification.db
    has_sqlite = query_notification_db(device_sn)

    # 4. 清空提醒记录
    clear_reminder_from_db(device_sn, has_sqlite)

    # 5. 重启服务
    restart_notification_service(device_sn)

    # 6. 再次查看时钟 App 数据确认
    print("\n" + "=" * 60)
    print("步骤 6: 清理后确认")
    print("=" * 60)
    run_hdc(device_sn, ['ls', '-lR', f'/data/app/el2/100/base/{CLOCK_BUNDLE}'])

    print("\n" + "=" * 60)
    print("完成。请到设备的「时钟」App 检查闹钟是否已清空。")
    print("=" * 60)


if __name__ == '__main__':
    main()
