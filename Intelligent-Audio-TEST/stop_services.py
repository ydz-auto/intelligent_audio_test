"""
停止前后端服务的脚本

停止以下服务:
- 后端 Flask + SocketIO 服务 (端口 5000, run.py)
- 前端 Vite 开发服务器 (端口 5173)
- API 适配器服务 (api_adapter_service)

使用方式: python stop_services.py
"""

import os
import subprocess
import sys


def run_powershell(command):
    """执行 PowerShell 命令并返回标准输出"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="ignore",
        )
        return result.stdout
    except Exception as e:
        print(f"   执行 PowerShell 命令时出错: {e}")
        return ""


def find_pids_by_port(port):
    """通过端口号查找占用该端口的进程 PID (使用 PowerShell)"""
    try:
        output = run_powershell(
            "Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue"
            " | Select-Object -ExpandProperty OwningProcess -Unique" % port
        )
        pids = set()
        for line in output.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
        return pids
    except Exception as e:
        print(f"   查找端口 {port} 时出错: {e}")
        return set()


def find_pids_by_command(pattern):
    """通过命令行匹配查找进程 PID (使用 PowerShell, 替代已废弃的 wmic)"""
    try:
        escaped = pattern.replace("'", "''")
        output = run_powershell(
            "Get-CimInstance Win32_Process"
            " | Where-Object { $_.CommandLine -match '%s' }"
            " | Select-Object -ExpandProperty ProcessId" % escaped
        )
        pids = set()
        for line in output.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
        return pids
    except Exception as e:
        print(f"   查找命令行模式 '{pattern}' 时出错: {e}")
        return set()


def stop_pid(pid, service_name):
    """停止指定 PID 的进程"""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        print(f"   停止 {service_name} - PID: {pid}")
        return 1
    except Exception as e:
        print(f"   停止 PID {pid} 时出错: {e}")
        return 0


def stop_service(service_name, pids):
    """停止一组 PID 对应的服务"""
    if pids:
        print(f"[INFO] 正在停止 {service_name}...")
        count = 0
        for pid in pids:
            count += stop_pid(pid, service_name)
        return count
    else:
        print(f"[INFO] 未发现 {service_name} 进程")
        return 0


def main():
    stopped_count = 0

    print("=" * 40)
    print("    前后端服务停止脚本")
    print("=" * 40)
    print()

    # 1. 停止后端 Flask + SocketIO 服务 (端口 5000)
    print("[INFO] 正在查找占用端口 5000 的进程 (后端 Flask 服务)...")
    pids = find_pids_by_port(5000)
    stopped_count += stop_service("后端 Flask 服务", pids)

    # 2. 通过命令行匹配停止后端服务 (python run.py)
    print()
    print("[INFO] 正在查找后端 Python 服务 (run.py)...")
    pids = find_pids_by_command(r"run\.py")
    stopped_count += stop_service("后端 Python 服务", pids)

    # 3. 停止前端 Vite 开发服务器 (端口 5173)
    print()
    print("[INFO] 正在查找占用端口 5173 的进程 (前端 Vite 开发服务器)...")
    pids = find_pids_by_port(5173)
    stopped_count += stop_service("前端 Vite 开发服务器", pids)

    # 4. 停止 API 适配器服务 (api_adapter_service)
    print()
    print("[INFO] 正在查找 API 适配器服务 (api_adapter_service)...")
    pids = find_pids_by_command(r"api_adapter_service")
    stopped_count += stop_service("API 适配器服务", pids)

    print()
    print("=" * 40)
    print(f"  停止完成，共停止 {stopped_count} 个进程")
    print("=" * 40)


if __name__ == "__main__":
    main()
