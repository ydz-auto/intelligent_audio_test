from app.services.wer_calculator import calculate_wer
from app.models.task import TaskModel
from app.config import config
import json
from datetime import datetime

# 直接测试完整流程
ref = '1'
hyp = '今天天气很好 适合出门散步 你好，世界 音频处理测试 这是一个模拟结果 今天天气很好 适合出门散步 你好，世界 音频处理测试 这是一个模拟结果'
task_type = 'wer'

print("1. 直接测试calculate_wer函数:")
result = calculate_wer(ref, hyp)
print(f"   结果: {result}")
print(f"   结果类型: {type(result)}")
print(f"   JSON序列化结果: {json.dumps(result)}")

print("\n2. 测试TaskModel.create_task:")
task_id = "test_task_123"
task_id = TaskModel.create_task(task_id, ref, hyp, task_type, None, None)
print(f"   创建的任务ID: {task_id}")

print("\n3. 测试TaskModel.update_task_status:")
TaskModel.update_task_status(
    task_id, 
    'completed', 
    started_at=datetime.now().isoformat(), 
    completed_at=datetime.now().isoformat(), 
    result=result
)
print(f"   更新任务状态完成")

print("\n4. 测试TaskModel.get_task:")
task = TaskModel.get_task(task_id)
print(f"   任务状态: {task['status']}")
print(f"   数据库中的result: {task['result']}")
print(f"   result类型: {type(task['result'])}")

print("\n5. 测试JSON反序列化:")
if task['result']:
    deserialized_result = json.loads(task['result'])
    print(f"   反序列化结果: {deserialized_result}")
    print(f"   反序列化结果类型: {type(deserialized_result)}")
else:
    print(f"   数据库中的result为空")

print("\n6. 直接测试calculate_ser函数:")
ser_result = calculate_ser(ref, hyp)
print(f"   SER结果: {ser_result}")
print(f"   SER结果类型: {type(ser_result)}")
print(f"   SER JSON序列化结果: {json.dumps(ser_result)}")
