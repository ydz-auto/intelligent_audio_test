import subprocess
import os
import time

PGSQL_BIN = r"C:\S2TT\environment\pgsql\bin"
PGSQL_DATA = r"C:\S2TT\environment\pgsql\data"
PGSQL_PORTS = [5432, 5423]

def is_postgres_running():
    for port in PGSQL_PORTS:
        try:
            result = subprocess.run(
                [os.path.join(PGSQL_BIN, "pg_isready.exe"), "-p", str(port)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False

def cleanup_stale_pid():
    pid_file = os.path.join(PGSQL_DATA, "postmaster.pid")
    if not os.path.exists(pid_file):
        return False
    try:
        with open(pid_file, "r") as f:
            pid_str = f.readline().strip()
        if not pid_str:
            os.remove(pid_file)
            print(f"Removed empty postmaster.pid")
            return True
        pid = int(pid_str)
        check = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True
        )
        if str(pid) not in check.stdout or "postgres" not in check.stdout.lower():
            os.remove(pid_file)
            print(f"Removed stale postmaster.pid (PID {pid} not running)")
            return True
        else:
            print(f"postmaster.pid exists and PID {pid} is still a running process")
            return False
    except Exception as e:
        print(f"Error checking postmaster.pid: {e}")
        try:
            os.remove(pid_file)
            print(f"Force removed postmaster.pid")
            return True
        except Exception as e2:
            print(f"Failed to remove postmaster.pid: {e2}")
            return False

def find_pids_by_port(port):
    pids = set()
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        pids.add(int(parts[-1]))
                    except ValueError:
                        continue
    except Exception as e:
        print(f"Error finding PIDs by port {port}: {e}")
    return pids

def stop_postgres_services():
    print("Trying to stop PostgreSQL Windows services...")
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
        subprocess.run(["net", "stop", svc], capture_output=True, text=True)
    if not services:
        print("No PostgreSQL Windows services found")

def force_kill():
    stop_postgres_services()
    for attempt in range(3):
        print(f"Force killing postgres processes (attempt {attempt + 1}/3)...")
        subprocess.run(["taskkill", "/F", "/T", "/IM", "postgres.exe"],
                       capture_output=True, text=True)
        subprocess.run(["taskkill", "/F", "/T", "/IM", "pg_ctl.exe"],
                       capture_output=True, text=True)
        for port in PGSQL_PORTS:
            pids = find_pids_by_port(port)
            for pid in pids:
                if pid == 0:
                    continue
                print(f"Killing PID {pid} listening on port {port}")
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, text=True)
        time.sleep(3)
        if not is_postgres_running():
            break
    pid_file = os.path.join(PGSQL_DATA, "postmaster.pid")
    if os.path.exists(pid_file):
        try:
            os.remove(pid_file)
            print("Removed postmaster.pid after force kill")
        except Exception as e:
            print(f"Failed to remove postmaster.pid: {e}")

def stop_postgres():
    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")
    pid_file = os.path.join(PGSQL_DATA, "postmaster.pid")
    has_pid_file = os.path.exists(pid_file)

    if not has_pid_file and not is_postgres_running():
        print("PostgreSQL is not running (no PID file, no connections)")
        return True

    if has_pid_file:
        print("Stopping PostgreSQL via pg_ctl ...")
        try:
            result = subprocess.run(
                [pg_ctl, "stop", "-D", PGSQL_DATA, "-m", "fast", "-w"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print("PostgreSQL stopped successfully")
                return True
            else:
                print(f"pg_ctl stop failed (rc={result.returncode}): {result.stderr.strip()}")
                if not is_postgres_running():
                    print("PostgreSQL is not accepting connections after pg_ctl failure")
                    cleanup_stale_pid()
                    return True
        except subprocess.TimeoutExpired:
            print("pg_ctl stop timed out")
        except Exception as e:
            print(f"pg_ctl stop error: {e}")

    print("Attempting force kill...")
    force_kill()
    if not is_postgres_running():
        print("PostgreSQL stopped after force kill")
        return True
    else:
        print("PostgreSQL still running after force kill")
        return False

if __name__ == "__main__":
    stop_postgres()
