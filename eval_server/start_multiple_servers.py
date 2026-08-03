import os
import threading
import subprocess
import sys
import time

def run_server(port):
    print(f"Starting server on port {port}...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run([sys.executable, "-u", "app.py", "--port", str(port)], env=env)

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
