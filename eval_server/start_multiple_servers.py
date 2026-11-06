import os
import threading
import subprocess
import sys
import time

def run_server(port):
    print(f"Starting server on port {port}...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    server_dir = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, "-u", "app.py", "--port", str(port)],
                   env=env, cwd=server_dir)

def main():
    ports = [8888]
    threads = []
    
    for port in ports:
        thread = threading.Thread(target=run_server, args=(port,))
        thread.start()
        threads.append(thread)
        time.sleep(1) # Give some time between starts
        
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    main()
