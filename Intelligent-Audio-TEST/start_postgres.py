import subprocess
import sys
import os
import time

PGSQL_BIN = r"C:\S2TT\environment\pgsql\bin"
PGSQL_DATA = r"C:\S2TT\environment\pgsql\data"
PGSQL_PORT = 5432

def is_postgres_running():
    try:
        result = subprocess.run(
            [os.path.join(PGSQL_BIN, "pg_isready.exe"), "-p", str(PGSQL_PORT)],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
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

def force_kill():
    print("Force killing postgres processes...")
    subprocess.run(["taskkill", "/F", "/IM", "postgres.exe"],
                   capture_output=True, text=True)
    subprocess.run(["taskkill", "/F", "/IM", "pg_ctl.exe"],
                   capture_output=True, text=True)
    time.sleep(2)
    pid_file = os.path.join(PGSQL_DATA, "postmaster.pid")
    if os.path.exists(pid_file):
        try:
            os.remove(pid_file)
            print("Removed postmaster.pid after force kill")
        except Exception as e:
            print(f"Failed to remove postmaster.pid: {e}")

def start_postgres():
    if is_postgres_running():
        print(f"PostgreSQL is already running on port {PGSQL_PORT}")
        return True

    if not is_postgres_running():
        pid_file = os.path.join(PGSQL_DATA, "postmaster.pid")
        if os.path.exists(pid_file):
            print("Found stale postmaster.pid, cleaning up...")
            if not cleanup_stale_pid():
                print("PID file references a live process, force killing...")
                force_kill()

    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")
    log_file = os.path.join(PGSQL_DATA, "pg_startup.log")

    print(f"Starting PostgreSQL from {PGSQL_DATA} ...")

    try:
        result = subprocess.run(
            [pg_ctl, "start", "-D", PGSQL_DATA, "-l", log_file, "-w"],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"pg_ctl start failed (rc={result.returncode}): {result.stderr.strip()}")
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    tail = f.readlines()[-20:]
                print("--- Last 20 lines of pg_startup.log ---")
                for line in tail:
                    print(line.rstrip())
            return False

        for i in range(30):
            if is_postgres_running():
                print(f"PostgreSQL started successfully on port {PGSQL_PORT}")
                return True
            time.sleep(1)

        print("PostgreSQL failed to start within 30 seconds. Check log file:", log_file)
        return False
    except subprocess.TimeoutExpired:
        print("pg_ctl start timed out")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-20:]
            print("--- Last 20 lines of pg_startup.log ---")
            for line in tail:
                print(line.rstrip())
        return False
    except Exception as e:
        print(f"Failed to start PostgreSQL: {e}")
        return False

def stop_postgres():
    if not is_postgres_running():
        print("PostgreSQL is not accepting connections")
        if cleanup_stale_pid():
            print("Cleaned up stale PID file, PostgreSQL is now fully stopped")
        else:
            print("PID file references a live process, attempting force kill...")
            force_kill()
        return True

    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")

    print("Stopping PostgreSQL ...")
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
            print("Attempting force kill...")
            force_kill()
            return not is_postgres_running()
    except subprocess.TimeoutExpired:
        print("pg_ctl stop timed out, force killing...")
        force_kill()
        return not is_postgres_running()
    except Exception as e:
        print(f"Failed to stop PostgreSQL: {e}")
        print("Attempting force kill...")
        force_kill()
        return not is_postgres_running()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        stop_postgres()
    else:
        start_postgres()
