import requests
import time
import threading

BASE_URL = "http://localhost:5001"

def create_task(i):
    payload = {
        "asr_ref": f"参考文本 {i}",
        "asr_hyp": f"结果文本 {i}",
        "task_type": "wer"
    }
    response = requests.post(f"{BASE_URL}/create_task", json=payload)
    print(f"Task {i} created: {response.json()['data']['task_id']}")

def check_health():
    for _ in range(10):
        response = requests.get(f"{BASE_URL}/")
        data = response.json()["data"]["concurrency"]
        print(f"Health check - WER: {data['wer']['current']}/{data['wer']['max']}, SER: {data['ser']['current']}/{data['ser']['max']}")
        time.sleep(1)

if __name__ == "__main__":
    # Create 3 WER tasks (Max 2)
    for i in range(3):
        create_task(i)
    
    # Create 2 SER tasks (Max 1)
    for i in range(2):
        payload = {
            "asr_ref": f"参考文本 SER {i}",
            "asr_hyp": f"结果文本 SER {i}",
            "task_type": "ser"
        }
        response = requests.post(f"{BASE_URL}/create_task", json=payload)
        print(f"SER Task {i} created: {response.json()['data']['task_id']}")
    
    check_health()
