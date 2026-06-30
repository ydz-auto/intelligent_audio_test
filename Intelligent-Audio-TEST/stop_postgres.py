import subprocess
import os
import time
import ctypes

PGSQL_BIN = r"C:\S2TT\environment\pgsql\bin"
PGSQL_DATA = r"C:\S2TT\environment\pgsql\data"
PGSQL_PORTS = [5432]

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def is_postgres_running():
    for port in PGSQL_PORTS:
        try:
            result = subprocess.run(
                [os.path.join(PGSQL_BIN, "pg_isready.exe"), "-p", str(port)],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False

def find_pids_by_port(port):
    pids = set()
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        pids.add(int(parts[-1]))
                    except ValueError:
                        continue
    except Exception:
        pass
    return pids

def stop_postgres_services():
    result = subprocess.run(
        ["sc", "query", "type=", "service", "state=", "all"],
        capture_output=True, text=True
    )
    services = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("SERVICE_NAME:") and "postgres" in line.lower():
            svc_name = line.split(":", 1)[1].strip()
            services.append(svc_name)
    for svc in services:
        print(f"Stopping service: {svc}")
        r = subprocess.run(["net", "stop", svc], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  Failed: {r.stderr.strip() or r.stdout.strip()}")
            if not is_admin():
                print("  -> Requires Administrator privileges!")
    return services

def force_kill():
    svcs = stop_postgres_services()
    if svcs:
        time.sleep(2)
        if not is_postgres_running():
            return True

    for attempt in range(3):
        print(f"Force killing (attempt {attempt + 1}/3)...")
        for img in ["postgres.exe", "pg_ctl.exe"]:
            r = subprocess.run(["taskkill", "/F", "/T", "/IM", img],
                               capture_output=True, text=True)
            if r.returncode != 0 and "not found" not in r.stderr.lower() and "没有" not in r.stderr:
                print(f"  taskkill {img}: {r.stderr.strip()}")
        for port in PGSQL_PORTS:
            for pid in find_pids_by_port(port):
                if pid == 0:
                    continue
                print(f"Killing PID {pid} on port {port}")
                r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    print(f"  Failed: {r.stderr.strip()}")
                    if not is_admin():
                        print("  -> Requires Administrator privileges!")
        time.sleep(3)
        if not is_postgres_running():
            return True
    return False

def stop_postgres():
    if not is_admin():
        print("WARNING: Not running as Administrator! Force kill may fail.")

    pid_file = os.path.join(PGSQL_DATA, "postmaster.pid")

    if not os.path.exists(pid_file) and not is_postgres_running():
        print("PostgreSQL is not running")
        return True

    if os.path.exists(pid_file):
        print("Stopping PostgreSQL via pg_ctl ...")
        try:
            result = subprocess.run(
                [os.path.join(PGSQL_BIN, "pg_ctl.exe"), "stop", "-D", PGSQL_DATA, "-m", "fast", "-w"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print("PostgreSQL stopped successfully")
                return True
            print(f"pg_ctl stop failed: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            print("pg_ctl stop timed out")
        except Exception as e:
            print(f"pg_ctl stop error: {e}")

    print("Attempting force kill...")
    if force_kill():
        print("PostgreSQL stopped after force kill")
        return True
    else:
        print("PostgreSQL still running after force kill!")
        return False

if __name__ == "__main__":
    stop_postgres()
