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

def start_postgres():
    if is_postgres_running():
        print(f"PostgreSQL is already running on port {PGSQL_PORT}")
        return True

    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")
    log_file = os.path.join(PGSQL_DATA, "pg_startup.log")

    print(f"Starting PostgreSQL from {PGSQL_DATA} ...")

    try:
        subprocess.Popen(
            [pg_ctl, "start", "-D", PGSQL_DATA, "-l", log_file, "-w"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        for i in range(30):
            if is_postgres_running():
                print(f"PostgreSQL started successfully on port {PGSQL_PORT}")
                return True
            time.sleep(1)

        print("PostgreSQL failed to start within 30 seconds. Check log file:", log_file)
        return False
    except Exception as e:
        print(f"Failed to start PostgreSQL: {e}")
        return False

def stop_postgres():
    if not is_postgres_running():
        print("PostgreSQL is not running")
        return True

    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")

    print("Stopping PostgreSQL ...")
    try:
        subprocess.run(
            [pg_ctl, "stop", "-D", PGSQL_DATA, "-m", "fast", "-w"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("PostgreSQL stopped")
        return True
    except Exception as e:
        print(f"Failed to stop PostgreSQL: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        stop_postgres()
    else:
        start_postgres()
