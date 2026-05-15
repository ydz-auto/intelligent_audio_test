import subprocess
import os

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

def stop_postgres():
    if not is_postgres_running():
        print("PostgreSQL is not running")
        return True

    pg_ctl = os.path.join(PGSQL_BIN, "pg_ctl.exe")

    print("Stopping PostgreSQL ...")
    try:
        subprocess.run(
            [pg_ctl, "stop", "-D", PGSQL_DATA, "-m", "fast", "-w"],
            capture_output=True,
            text=True
        )
        print("PostgreSQL stopped")
        return True
    except Exception as e:
        print(f"Failed to stop PostgreSQL: {e}")
        return False

if __name__ == "__main__":
    stop_postgres()
