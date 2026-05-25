import requests
import time

# Test creating a task with mock vendor
def test_create_task():
    print("Testing task creation...")
    url = "http://localhost:8000/api/create_task"
    headers = {"Content-Type": "application/json"}
    data = {
        "audio_path": "test_audio.wav",
        "trans_direction": "zh2en",
        "vendor": "mock"
    }
    
    response = requests.post(url, headers=headers, json=data)
    print(f"Create task response: {response.json()}")
    return response.json()

# Test getting task status
def test_get_status(task_id):
    print(f"Testing get status for task {task_id}...")
    url = f"http://localhost:8000/api/get_status/{task_id}"
    response = requests.get(url)
    print(f"Get status response: {response.json()}")
    return response.json()

# Test getting frame results
def test_get_frame_results(task_id):
    print(f"Testing get frame results for task {task_id}...")
    url = f"http://localhost:8000/api/get_frame_results/{task_id}"
    response = requests.get(url)
    print(f"Get frame results response: {response.json()}")
    return response.json()

# Test getting final result
def test_get_final_result(task_id):
    print(f"Testing get final result for task {task_id}...")
    url = f"http://localhost:8000/api/get_final_result/{task_id}"
    response = requests.get(url)
    print(f"Get final result response: {response.json()}")
    return response.json()

# Main test function
def main():
    print("=== Testing Mock Adapter API ===")
    
    # Create task
    create_response = test_create_task()
    task_id = create_response["data"]["task_id"]
    
    # Wait for task to complete
    print(f"\nWaiting for task {task_id} to complete...")
    time.sleep(10)
    
    # Get status
    test_get_status(task_id)
    
    # Get frame results
    test_get_frame_results(task_id)
    
    # Get final result
    test_get_final_result(task_id)
    
    print("\n=== Test completed ===")

if __name__ == "__main__":
    main()
