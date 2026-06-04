import subprocess
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
            if not is_postgres_running():
                print("PostgreSQL stopped after force kill")
                return True
            else:
                print("PostgreSQL still running after force kill")
                return False
    except subprocess.TimeoutExpired:
        print("pg_ctl stop timed out, force killing...")
        force_kill()
        if not is_postgres_running():
            print("PostgreSQL stopped after force kill")
            return True
        else:
            print("PostgreSQL still running after force kill")
            return False
    except Exception as e:
        print(f"Failed to stop PostgreSQL: {e}")
        print("Attempting force kill...")
        force_kill()
        return not is_postgres_running()

if __name__ == "__main__":
    stop_postgres()
