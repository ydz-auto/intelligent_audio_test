import sys
import os
import time
import requests
import threading
import concurrent.futures
from datetime import datetime

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Test audio file
test_audio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio.wav")

# Configuration
BASE_URL = "http://localhost:8000"
CONCURRENT_REQUESTS = 200  # Number of concurrent requests
TEST_DURATION = 30         # Test duration in seconds
MAX_WORKERS = 100          # Maximum number of threads in pool

def make_request(request_id):
    """Make a single request to the create_task API"""
    start_time = time.time()
    try:
        url = f"{BASE_URL}/api/create_task"
        payload = {
            "audio_path": test_audio_path,
            "trans_direction": "zh2en",
            "vendor": "mock"  # Use mock vendor for testing
        }
        
        response = requests.post(url, json=payload, timeout=30)
        end_time = time.time()
        latency = end_time - start_time
        
        if response.status_code == 200:
            task_id = response.json()["data"]["task_id"]
            return {
                "request_id": request_id,
                "success": True,
                "status_code": response.status_code,
                "task_id": task_id,
                "latency": latency,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "request_id": request_id,
                "success": False,
                "status_code": response.status_code,
                "latency": latency,
                "error": response.text,
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        end_time = time.time()
        latency = end_time - start_time
        return {
            "request_id": request_id,
            "success": False,
            "status_code": 0,
            "latency": latency,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def run_concurrent_tests():
    """Run concurrent tests"""
    print(f"Starting high concurrency test...")
    print(f"- Concurrent requests: {CONCURRENT_REQUESTS}")
    print(f"- Test duration: {TEST_DURATION} seconds")
    print(f"- Maximum workers: {MAX_WORKERS}")
    print(f"- Base URL: {BASE_URL}")
    print("=" * 60)
    
    results = []
    start_time = time.time()
    request_count = 0
    
    # Create a thread pool executor
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Run tests for the specified duration
        while time.time() - start_time < TEST_DURATION:
            # Submit multiple requests
            future_to_request = {
                executor.submit(make_request, request_count + i): request_count + i 
                for i in range(CONCURRENT_REQUESTS)
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_request):
                result = future.result()
                results.append(result)
                
                # Print progress every 100 requests
                if len(results) % 100 == 0:
                    print(f"Processed {len(results)} requests...")
            
            request_count += CONCURRENT_REQUESTS
    
    end_time = time.time()
    total_duration = end_time - start_time
    
    # Calculate statistics
    total_requests = len(results)
    successful_requests = sum(1 for r in results if r["success"])
    failed_requests = total_requests - successful_requests
    
    latencies = [r["latency"] for r in results]
    avg_latency = sum(latencies) / total_requests if total_requests > 0 else 0
    min_latency = min(latencies) if total_requests > 0 else 0
    max_latency = max(latencies) if total_requests > 0 else 0
    
    throughput = total_requests / total_duration if total_duration > 0 else 0
    
    # Print summary
    print("\n" + "=" * 60)
    print("High Concurrency Test Results")
    print("=" * 60)
    print(f"Total Duration: {total_duration:.2f} seconds")
    print(f"Total Requests: {total_requests}")
    print(f"Successful Requests: {successful_requests} ({successful_requests/total_requests*100:.2f}%)")
    print(f"Failed Requests: {failed_requests} ({failed_requests/total_requests*100:.2f}%)")
    print(f"Throughput: {throughput:.2f} requests/second")
    print(f"Average Latency: {avg_latency:.2f} seconds")
    print(f"Minimum Latency: {min_latency:.2f} seconds")
    print(f"Maximum Latency: {max_latency:.2f} seconds")
    print("=" * 60)
    
    # Print failure details if any
    if failed_requests > 0:
        print(f"\nFailure Details:")
        print("-" * 40)
        error_types = {}
        for result in results:
            if not result["success"]:
                error_msg = result["error"] if result["status_code"] == 0 else f"HTTP {result['status_code']}"
                error_types[error_msg] = error_types.get(error_msg, 0) + 1
        
        for error, count in error_types.items():
            print(f"{error}: {count} occurrences")
    
    return {
        "total_duration": total_duration,
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "throughput": throughput,
        "avg_latency": avg_latency,
        "min_latency": min_latency,
        "max_latency": max_latency
    }

def test_health_check():
    """Test health check API before running concurrency tests"""
    print("Checking server health...")
    url = f"{BASE_URL}/health"
    response = requests.get(url)
    if response.status_code == 200 and response.json()["status"] == "healthy":
        print("✓ Server is healthy")
        return True
    else:
        print(f"✗ Server health check failed: {response.status_code} - {response.text}")
        return False

if __name__ == "__main__":
    # Check server health first
    if not test_health_check():
        sys.exit(1)
    
    # Run concurrent tests
    run_concurrent_tests()
