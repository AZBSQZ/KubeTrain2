"""
KubeTrain2 端到端训练测试脚本
1. 登录获取JWT token
2. 创建训练任务（指向 test_scripts/train_simple.py）
3. 提交任务
4. 轮询监控状态转换直到完成/失败
"""
import json
import os
import sys
import time
import requests

BASE_URL = 'http://localhost:8010/api'
SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'test_scripts', 'train_simple.py'))


def login():
    """登录获取 JWT token"""
    resp = requests.post(f'{BASE_URL}/auth/login', json={
        'username': 'admin',
        'password': 'admin123'
    }, timeout=10)
    data = resp.json()
    if data.get('code') == 200:
        token = data['data']['access_token']
        print(f"[OK] Login successful, token={token[:30]}...")
        return token
    else:
        print(f"[FAIL] Login failed: {data}")
        sys.exit(1)


def create_task(token):
    """创建训练任务"""
    headers = {'Authorization': f'Bearer {token}'}
    
    task_data = {
        'name': '测试训练-线性回归',
        'description': 'KubeTrain2 端到端测试：纯CPU线性回归训练',
        'training_script': SCRIPT_PATH,
        'execution_mode': 'auto',
        'parallel_mode': 'single',
        'num_nodes': 1,
        'gpus_per_node': 0,
        'gpu_limit': 0,
        'cpu_request': '1',
        'memory_request': '512Mi',
        'training_args': {
            'epochs': '5',
            'lr': '0.01',
            'data-size': '200',
        },
        'priority': 5,
        'max_retries': 1,
    }
    
    resp = requests.post(f'{BASE_URL}/tasks', json=task_data, headers=headers, timeout=10)
    data = resp.json()
    if data.get('code') == 200:
        task = data['data']
        print(f"[OK] Task created: id={task['id']}, name={task['name']}, status={task['status']}")
        return task['id']
    else:
        print(f"[FAIL] Create task failed: {data}")
        sys.exit(1)


def submit_task(token, task_id):
    """提交任务到调度器"""
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.post(f'{BASE_URL}/tasks/{task_id}/submit', headers=headers, timeout=10)
    data = resp.json()
    if data.get('code') == 200:
        task = data['data']
        print(f"[OK] Task submitted: status={task['status']}")
        return True
    else:
        print(f"[FAIL] Submit task failed: {data}")
        return False


def monitor_task(token, task_id, timeout=120):
    """轮询监控任务状态转换"""
    headers = {'Authorization': f'Bearer {token}'}
    last_status = None
    start_time = time.time()
    transitions = []
    
    print(f"\n{'='*60}")
    print(f"  Monitoring task: {task_id}")
    print(f"{'='*60}")
    
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(f'{BASE_URL}/tasks/{task_id}', headers=headers, timeout=10)
            data = resp.json()
            if data.get('code') != 200:
                print(f"[WARN] Get task failed: {data.get('message')}")
                time.sleep(2)
                continue
            
            task = data['data']
            status = task['status']
            progress = task.get('progress_percent', 0) or 0
            current_epoch = task.get('current_epoch', 0) or 0
            total_epochs = task.get('total_epochs', 0) or 0
            
            if status != last_status:
                elapsed = round(time.time() - start_time, 1)
                transition = f"{last_status or 'init'} → {status}"
                transitions.append((elapsed, transition))
                print(f"  [{elapsed:6.1f}s] Status: {transition}")
                last_status = status
            
            # 终态检查
            if status in ('completed', 'failed', 'cancelled'):
                elapsed = round(time.time() - start_time, 1)
                print(f"\n{'='*60}")
                print(f"  Task finished: {status}")
                print(f"  Duration: {task.get('duration', 'N/A')}s")
                print(f"  Progress: {progress}%")
                if task.get('final_loss') is not None:
                    print(f"  Final Loss: {task['final_loss']}")
                if task.get('final_accuracy') is not None:
                    print(f"  Final Accuracy: {task['final_accuracy']}")
                if task.get('error_message'):
                    print(f"  Error: {task['error_message']}")
                print(f"\n  Status Transitions:")
                for t, tr in transitions:
                    print(f"    [{t:6.1f}s] {tr}")
                print(f"{'='*60}")
                return status == 'completed'
            
            # 运行中显示进度
            if status == 'running' and (current_epoch > 0 or progress > 0):
                epoch_str = f"epoch {current_epoch}/{total_epochs}" if total_epochs else f"epoch {current_epoch}"
                sys.stdout.write(f"\r  [{round(time.time()-start_time,1):6.1f}s] Running: {epoch_str}, progress={progress}%  ")
                sys.stdout.flush()
            
        except Exception as e:
            print(f"[WARN] Monitor error: {e}")
        
        time.sleep(2)
    
    print(f"\n[TIMEOUT] Task did not complete within {timeout}s")
    return False


def main():
    print("=" * 60)
    print("  KubeTrain2 End-to-End Training Test")
    print("=" * 60)
    print(f"  Script: {SCRIPT_PATH}")
    print(f"  Exists: {os.path.exists(SCRIPT_PATH)}")
    print()
    
    # Step 1: Login
    token = login()
    
    # Step 2: Create task
    task_id = create_task(token)
    
    # Step 3: Submit task
    if not submit_task(token, task_id):
        sys.exit(1)
    
    # Step 4: Monitor
    success = monitor_task(token, task_id, timeout=120)
    
    if success:
        print("\n[SUCCESS] Training completed successfully!")
    else:
        print("\n[FAILED] Training did not complete successfully")
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
