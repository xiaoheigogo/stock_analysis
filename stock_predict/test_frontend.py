#!/usr/bin/env python3
"""
前端集成测试脚本
测试FastAPI服务器和前端功能
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import uvicorn
import threading
import time
import requests
import json

def test_api_endpoints(base_url="http://localhost:8000"):
    """测试API端点"""
    print("=" * 60)
    print("测试API端点")
    print("=" * 60)

    tests_passed = 0
    tests_failed = 0

    # 测试根端点
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            print("[OK] 根端点测试通过")
            tests_passed += 1
        else:
            print(f"[FAIL] 根端点测试失败: 状态码 {response.status_code}")
            tests_failed += 1
    except Exception as e:
        print(f"[FAIL] 根端点测试异常: {e}")
        tests_failed += 1

    # 测试API根端点
    try:
        response = requests.get(f"{base_url}/api/")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] API根端点测试通过: {data.get('service')}")
            tests_passed += 1
        else:
            print(f"[FAIL] API根端点测试失败: 状态码 {response.status_code}")
            tests_failed += 1
    except Exception as e:
        print(f"[FAIL] API根端点测试异常: {e}")
        tests_failed += 1

    # 测试健康检查
    try:
        response = requests.get(f"{base_url}/api/health")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 健康检查测试通过: 数据库状态 = {data.get('database')}")
            tests_passed += 1
        else:
            print(f"[FAIL] 健康检查测试失败: 状态码 {response.status_code}")
            tests_failed += 1
    except Exception as e:
        print(f"[FAIL] 健康检查测试异常: {e}")
        tests_failed += 1

    # 测试推荐端点
    try:
        response = requests.get(f"{base_url}/api/recommend", params={"top_n": 3})
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 推荐端点测试通过: 获取到 {data.get('count')} 个推荐")
            tests_passed += 1
        else:
            print(f"[FAIL] 推荐端点测试失败: 状态码 {response.status_code}")
            tests_failed += 1
    except Exception as e:
        print(f"[FAIL] 推荐端点测试异常: {e}")
        tests_failed += 1

    # 测试预测端点（使用模拟数据）
    try:
        payload = {
            "ts_code": "000001",
            "seq_len": 30,
            "pred_len": 10
        }
        response = requests.post(f"{base_url}/api/predict", json=payload)
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 预测端点测试通过: {data.get('ts_code')} 预期收益 = {data.get('predicted_return'):.4f}")
            tests_passed += 1
        else:
            print(f"[FAIL] 预测端点测试失败: 状态码 {response.status_code}")
            tests_failed += 1
    except Exception as e:
        print(f"[FAIL] 预测端点测试异常: {e}")
        tests_failed += 1

    # 测试股票数据端点
    try:
        response = requests.get(f"{base_url}/api/stock/000001", params={"limit": 5})
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] 股票数据端点测试通过: 获取到 {data.get('count')} 条数据")
            tests_passed += 1
        else:
            print(f"[FAIL] 股票数据端点测试失败: 状态码 {response.status_code}")
            tests_failed += 1
    except Exception as e:
        print(f"[FAIL] 股票数据端点测试异常: {e}")
        tests_failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: 通过 {tests_passed}, 失败 {tests_failed}")
    print("=" * 60)

    return tests_failed == 0

def test_frontend_files():
    """测试前端文件是否存在"""
    print("\n" + "=" * 60)
    print("测试前端文件")
    print("=" * 60)

    files_to_check = [
        "frontend/templates/index.html",
        "frontend/static/css/style.css",
        "frontend/static/js/app.js"
    ]

    all_exist = True
    for file_path in files_to_check:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"[OK] {file_path} 存在")
        else:
            print(f"[FAIL] {file_path} 不存在")
            all_exist = False

    return all_exist

def start_test_server():
    """启动测试服务器"""
    print("\n启动测试服务器...")

    # 导入应用
    from app.main import app

    # 在后台启动服务器
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning"
    )
    server = uvicorn.Server(config)

    # 启动服务器线程
    server_thread = threading.Thread(target=server.run)
    server_thread.daemon = True
    server_thread.start()

    # 等待服务器启动
    time.sleep(3)

    return server_thread

def main():
    """主测试函数"""
    print("股票预测系统前端集成测试")
    print("=" * 60)

    # 测试前端文件
    if not test_frontend_files():
        print("\n前端文件测试失败，停止测试")
        return False

    # 启动测试服务器
    print("\n启动FastAPI服务器进行API测试...")
    server_thread = start_test_server()

    try:
        # 等待服务器完全启动
        time.sleep(2)

        # 测试API端点
        print("\n开始API端点测试...")
        api_success = test_api_endpoints()

        if api_success:
            print("\n[SUCCESS] 所有测试通过！")
            print("\n启动说明:")
            print("1. 启动服务器: python app/main.py")
            print("2. 访问地址: http://localhost:8000")
            print("3. API文档: http://localhost:8000/docs")
            return True
        else:
            print("\n[WARN] API测试失败，但前端文件已创建")
            print("\n手动测试步骤:")
            print("1. 启动服务器: python -m uvicorn app.main:app --reload")
            print("2. 访问 http://localhost:8000 查看前端界面")
            return False

    except Exception as e:
        print(f"\n[ERROR] 测试过程中发生异常: {e}")
        return False
    finally:
        # 服务器线程会自动停止（daemon线程）
        pass

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)