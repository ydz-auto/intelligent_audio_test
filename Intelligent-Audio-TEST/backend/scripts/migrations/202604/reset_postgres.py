# -*- coding: utf-8 -*-
"""
PostgreSQL 数据库集群重置脚本

功能：
1. 停止 PostgreSQL
2. 备份旧数据目录
3. 重新初始化数据库集群
4. 启动 PostgreSQL

使用方法：
    python reset_postgres.py
"""

import subprocess
import os
import shutil
import time

PGSQL_BIN = r"C:\S2TT\environment\pgsql\bin"
PGSQL_DATA = r"C:\S2TT\environment\pgsql\data"


def is_postgres_running():
    """检查 PostgreSQL 是否正在运行"""
    try:
        result = subprocess.run(
            [os.path.join(PGSQL_BIN, "pg_isready.exe"), "-p", "5432"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def stop_postgres():
    """停止 PostgreSQL"""
    print("\n[1/4] 停止 PostgreSQL ...")

    if not is_postgres_running():
        print("      PostgreSQL 未运行")
        return True

    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")

    print("      正在停止 PostgreSQL ...")
    try:
        result = subprocess.run(
            [pg_ctl, "stop", "-D", PGSQL_DATA, "-m", "fast", "-w"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print("      PostgreSQL 已停止")
            return True
        else:
            print(f"      停止失败，尝试强制终止...")
            force_kill()
            return True
    except subprocess.TimeoutExpired:
        print("      停止超时，强制终止进程...")
        force_kill()
        return True
    except Exception as e:
        print(f"      停止失败: {e}，尝试强制终止...")
        force_kill()
        return True


def force_kill():
    """强制终止 PostgreSQL 进程"""
    print("      强制终止 postgres 进程...")
    subprocess.run(["taskkill", "/F", "/IM", "postgres.exe"],
                   capture_output=True, text=True)
    subprocess.run(["taskkill", "/F", "/IM", "pg_ctl.exe"],
                   capture_output=True, text=True)
    time.sleep(2)

    pid_file = os.path.join(PGSQL_DATA, "postmaster.pid")
    if os.path.exists(pid_file):
        print("      删除 postmaster.pid 文件...")
        try:
            os.remove(pid_file)
        except Exception as e:
            print(f"      删除 postmaster.pid 失败: {e}")
    time.sleep(2)


def backup_old_data():
    """备份旧数据目录"""
    print("\n[2/4] 备份旧数据目录 ...")

    pg_version_file = os.path.join(PGSQL_DATA, "PG_VERSION")

    if not os.path.exists(pg_version_file):
        print("      数据目录不存在，无需备份")
        return True

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{PGSQL_DATA}_backup_{timestamp}"

    print(f"      重命名 {PGSQL_DATA} -> {backup_dir}")
    try:
        os.rename(PGSQL_DATA, backup_dir)
        print(f"      备份完成: {backup_dir}")
        return True
    except Exception as e:
        print(f"      备份失败: {e}")
        return False


def init_postgres():
    """初始化 PostgreSQL 集群"""
    print("\n[3/4] 初始化 PostgreSQL 集群 ...")
    print(f"      编码: UTF8")
    print(f"      Locale: C.UTF-8")
    print(f"      目录: {PGSQL_DATA}")

    initdb = os.path.join(PGSQL_BIN, "initdb.exe")

    try:
        result = subprocess.run(
            [initdb, "-D", PGSQL_DATA, "-E", "UTF8"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"      初始化失败: {result.stderr}")
            return False
        print("      初始化成功")
        return True
    except Exception as e:
        print(f"      初始化失败: {e}")
        return False


def start_postgres():
    """启动 PostgreSQL"""
    print("\n[4/4] 启动 PostgreSQL ...")

    if is_postgres_running():
        print("      PostgreSQL 已在运行")
        return True

    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")
    log_file = os.path.join(PGSQL_DATA, "pg_startup.log")

    print("      正在启动 PostgreSQL ...")
    try:
        subprocess.Popen(
            [pg_ctl, "start", "-D", PGSQL_DATA, "-l", log_file, "-w"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        for i in range(30):
            if is_postgres_running():
                print("      PostgreSQL 启动成功")
                return True
            time.sleep(1)

        print(f"      启动失败，请检查日志: {log_file}")
        return False
    except Exception as e:
        print(f"      启动失败: {e}")
        return False


def main():
    print("=" * 50)
    print("PostgreSQL 数据库集群重置")
    print("=" * 50)

    print("\n警告：此操作将删除所有数据！")
    response = input("确认重置? (输入 'yes' 继续): ")
    if response.lower() != 'yes':
        print("已取消")
        return

    if not stop_postgres():
        print("\n停止 PostgreSQL 失败，无法继续")
        return

    if not backup_old_data():
        print("\n备份数据失败，无法继续")
        return

    if not init_postgres():
        print("\n初始化失败")
        return

    if not start_postgres():
        print("\n启动失败")
        return

    print("\n" + "=" * 50)
    print("重置完成！")
    print("=" * 50)
    print("\n现在可以运行迁移脚本:")
    print("  echo yes | python backend\\migrations\\migrate_data.py")


if __name__ == '__main__':
    main()
