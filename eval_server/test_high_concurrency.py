import asyncio
import aiohttp
import time
import json

# 测试配置
BASE_URL = "http://localhost:5001"
CONCURRENT_REQUESTS = 20  # 并发请求数
REQUESTS_PER_TYPE = 10   # 每种任务类型的请求数
TASK_TYPES = ["wer", "ser"]  # 测试的任务类型

# 测试数据
TEST_DATA = {
    "wer": {
        "asr_ref": "这是一个参考文本，用于测试WER计算。",
        "asr_result": "这是一个识别结果，用于测试WER计算。"
    },
    "ser": {
        "asr_ref": "这是第一句话。这是第二句话。这是第三句话。",
        "asr_result": "这是第一句话。这是第二个句子。这是第三句话。"
    }
}

async def create_task(session, task_type, request_id):
    """创建单个任务"""
    url = f"{BASE_URL}/api/create_task"
    data = {
        "asr_ref": TEST_DATA[task_type]["asr_ref"],
        "asr_result": TEST_DATA[task_type]["asr_result"],
        "task_type": task_type
    }
    
    try:
        start_time = time.time()
        async with session.post(url, json=data) as response:
            response_time = time.time() - start_time
            result = await response.json()
            
            # 获取任务ID和状态URL
            task_id = result.get("data", {}).get("task_id")
            status_url = result.get("data", {}).get("status_url")
            final_result_url = result.get("data", {}).get("final_result_url")
            
            return {
                "request_id": request_id,
                "task_type": task_type,
                "status_code": response.status,
                "response_time": response_time,
                "task_id": task_id,
                "status_url": status_url,
                "final_result_url": final_result_url,
                "success": result.get("code") == 0
            }
    except Exception as e:
        return {
            "request_id": request_id,
            "task_type": task_type,
            "status_code": 500,
            "response_time": time.time() - start_time,
            "error": str(e),
            "success": False
        }

async def get_task_result(session, task_info):
    """获取任务结果"""
    if not task_info.get("final_result_url"):
        return {
            "task_id": task_info.get("task_id"),
            "success": False,
            "error": "No final result URL"
        }
    
    try:
        async with session.get(task_info["final_result_url"]) as response:
            result = await response.json()
            return {
                "task_id": task_info.get("task_id"),
                "status_code": response.status,
                "result": result,
                "success": result.get("code") == 0
            }
    except Exception as e:
        return {
            "task_id": task_info.get("task_id"),
            "status_code": 500,
            "error": str(e),
            "success": False
        }

async def main():
    """主测试函数"""
    print(f"开始高并发测试: {CONCURRENT_REQUESTS} 并发请求")
    print(f"测试任务类型: {TASK_TYPES}")
    print(f"每种任务类型请求数: {REQUESTS_PER_TYPE}")
    print(f"测试URL: {BASE_URL}")
    print("=" * 60)
    
    # 创建所有测试任务
    all_tasks = []
    for task_type in TASK_TYPES:
        for i in range(REQUESTS_PER_TYPE):
            all_tasks.append((task_type, f"{task_type}_{i}"))
    
    total_tasks = len(all_tasks)
    print(f"总测试任务数: {total_tasks}")
    
    # 执行并发请求
    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        # 并发创建任务
        print("\n1. 并发创建任务...")
        create_tasks = [create_task(session, task_type, request_id) for task_type, request_id in all_tasks]
        results = await asyncio.gather(*create_tasks)
        
        # 统计创建结果
        success_count = sum(1 for r in results if r["success"])
        error_count = total_tasks - success_count
        avg_response_time = sum(r["response_time"] for r in results) / total_tasks if total_tasks > 0 else 0
        
        print(f"任务创建完成: {success_count} 成功, {error_count} 失败")
        print(f"平均响应时间: {avg_response_time:.2f} 秒")
        
        # 检查是否有成功创建的任务
        successful_tasks = [r for r in results if r["success"]]
        if not successful_tasks:
            print("没有成功创建的任务，无法继续测试")
            return
        
        # 等待一段时间，让任务有时间处理
        print(f"\n2. 等待5秒，让任务处理...")
        await asyncio.sleep(5)
        
        # 获取任务结果
        print("\n3. 获取任务结果...")
        result_tasks = [get_task_result(session, task) for task in successful_tasks]
        task_results = await asyncio.gather(*result_tasks)
        
        # 统计结果
        result_success_count = sum(1 for r in task_results if r["success"])
        result_error_count = len(task_results) - result_success_count
        
        print(f"任务结果获取完成: {result_success_count} 成功, {result_error_count} 失败")
        
        # 检查完成状态的任务
        completed_tasks = [r for r in task_results if r["success"] and r["result"].get("data", {}).get("status") == "completed"]
        processing_tasks = [r for r in task_results if r["success"] and r["result"].get("data", {}).get("status") in ["pending", "processing"]]
        failed_tasks = [r for r in task_results if r["success"] and r["result"].get("data", {}).get("status") == "failed"]
        
        print(f"\n任务状态统计:")
        print(f"- 已完成: {len(completed_tasks)}")
        print(f"- 处理中: {len(processing_tasks)}")
        print(f"- 失败: {len(failed_tasks)}")
        
        # 打印一些详细信息
        if completed_tasks:
            print(f"\n部分已完成任务示例:")
            for i, task in enumerate(completed_tasks[:3]):  # 只显示前3个
                task_data = task["result"]["data"]
                print(f"  任务ID: {task_data['task_id']}")
                print(f"  任务类型: {task_data['task_type']}")
                print(f"  状态: {task_data['status']}")
                if "result" in task_data and task_data["result"]:
                    print(f"  结果: {json.dumps(task_data['result'], ensure_ascii=False)}")
                print()
    
    total_time = time.time() - start_time
    print("=" * 60)
    print(f"测试完成")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"每秒处理请求数: {total_tasks / total_time:.2f} QPS")

if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())
