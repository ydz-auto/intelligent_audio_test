import threading
import subprocess
import sys
import time

def run_server(port):
    print(f"Starting server on port {port}...")
    subprocess.run([sys.executable, "app.py", "--port", str(port)])

def main():
    ports = [5000]
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
