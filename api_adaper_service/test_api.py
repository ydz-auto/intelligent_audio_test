import sys
import os
import time
import requests
import argparse

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Test audio file
test_audio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio.wav")

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run API tests on multiple ports')
parser.add_argument('--ports', type=str, default='8000', help='Comma-separated list of ports to test (default: 8000)')
args = parser.parse_args()

# Convert ports string to list
ports = [int(port.strip()) for port in args.ports.split(',')]

def test_health_check(base_url):
    """Test health check API"""
    print("\n=== Testing Health Check ===")
    url = f"{base_url}/health"
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("✓ Health check passed")

def test_create_task(base_url):
    """Test create task API"""
    print("\n=== Testing Create Task ===")
    url = f"{base_url}/api/create_task"
    payload = {
        "audio_path": test_audio_path,
        "trans_direction": "zh2en",
        "vendor": "mock"  # Use mock vendor for testing
    }
    
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert "task_id" in response.json()["data"]
    
    task_id = response.json()["data"]["task_id"]
    print(f"✓ Create task passed, task_id: {task_id}")
    return task_id

def test_get_status(base_url, task_id):
    """Test get task status API"""
    print(f"\n=== Testing Get Status for task {task_id} ===")
    url = f"{base_url}/api/get_status/{task_id}"
    
    # Wait a bit for the task to start processing
    time.sleep(1)
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["task_id"] == task_id
    print("✓ Get status passed")

def test_get_frame_results(base_url, task_id):
    """Test get frame results API"""
    print(f"\n=== Testing Get Frame Results for task {task_id} ===")
    url = f"{base_url}/api/get_frame_results/{task_id}?all=true"
    
    # Wait for the task to process some frames
    time.sleep(3)
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert "frame_results" in response.json()["data"]
    assert isinstance(response.json()["data"]["frame_results"], list)
    print(f"✓ Get frame results passed, found {len(response.json()['data']['frame_results'])} frames")

def test_get_final_result(base_url, task_id):
    """Test get final result API"""
    print(f"\n=== Testing Get Final Result for task {task_id} ===")
    url = f"{base_url}/api/get_final_result/{task_id}"
    
    # Wait for the task to complete
    time.sleep(10)
    
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert "final_asr_result" in response.json()["data"]
    assert "final_trans_result" in response.json()["data"]
    print("✓ Get final result passed")

def test_delete_task(base_url, task_id):
    """Test delete task API"""
    print(f"\n=== Testing Delete Task {task_id} ===")
    url = f"{base_url}/api/delete_task/{task_id}"
    
    response = requests.delete(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["code"] == 0
    print("✓ Delete task passed")

def test_invalid_task_id(base_url):
    """Test API with invalid task ID"""
    print("\n=== Testing Invalid Task ID ===")
    invalid_task_id = "invalid-task-id-123"
    
    # Test get_status with invalid task ID
    url = f"{base_url}/api/get_status/{invalid_task_id}"
    response = requests.get(url)
    print(f"get_status with invalid ID - Status Code: {response.status_code}")
    assert response.status_code == 404
    
    # Test get_frame_results with invalid task ID
    url = f"{base_url}/api/get_frame_results/{invalid_task_id}"
    response = requests.get(url)
    print(f"get_frame_results with invalid ID - Status Code: {response.status_code}")
    assert response.status_code == 404
    
    # Test get_final_result with invalid task ID
    url = f"{base_url}/api/get_final_result/{invalid_task_id}"
    response = requests.get(url)
    print(f"get_final_result with invalid ID - Status Code: {response.status_code}")
    assert response.status_code == 404
    
    # Test delete_task with invalid task ID
    url = f"{base_url}/api/delete_task/{invalid_task_id}"
    response = requests.delete(url)
    print(f"delete_task with invalid ID - Status Code: {response.status_code}")
    assert response.status_code == 404
    
    print("✓ Invalid task ID tests passed")

def test_create_task_missing_fields(base_url):
    """Test create task with missing required fields"""
    print("\n=== Testing Create Task with Missing Fields ===")
    url = f"{base_url}/api/create_task"
    
    # Test with missing audio_path
    payload = {
        "trans_direction": "zh2en",
        "vendor": "mock"
    }
    response = requests.post(url, json=payload)
    print(f"Missing audio_path - Status Code: {response.status_code}")
    assert response.status_code == 400
    
    # Test with missing trans_direction
    payload = {
        "audio_path": test_audio_path,
        "vendor": "mock"
    }
    response = requests.post(url, json=payload)
    print(f"Missing trans_direction - Status Code: {response.status_code}")
    assert response.status_code == 400
    
    print("✓ Missing fields tests passed")

if __name__ == "__main__":
    print("Starting API tests...")
    
    all_passed = True
    
    for port in ports:
        base_url = f"http://localhost:{port}"
        print(f"\n" + "="*60)
        print(f"Testing on port {port}...")
        print("="*60)
        
        try:
            # Test health check first to ensure server is running
            test_health_check(base_url)
            
            # Test with missing fields
            test_create_task_missing_fields(base_url)
            
            # Test with invalid task ID
            test_invalid_task_id(base_url)
            
            # Create a task for testing other APIs
            task_id = test_create_task(base_url)
            
            # Test other APIs with the created task ID
            test_get_status(base_url, task_id)
            test_get_frame_results(base_url, task_id)
            test_get_final_result(base_url, task_id)
            test_delete_task(base_url, task_id)
            
            print(f"\n🎉 All tests passed successfully on port {port}!")
            
        except Exception as e:
            print(f"\n❌ Test failed on port {port} with error: {str(e)}")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 All tests passed on all ports!")
    else:
        print("❌ Some tests failed on one or more ports!")
    print("="*60)
    
    sys.exit(0 if all_passed else 1)
