#!/usr/bin/env python3
"""
调试 KORGym 游戏服务器启动问题

Usage:
    python scripts/debug_game_server.py
"""

import subprocess
import sys
import time
import requests
from pathlib import Path


def main():
    print("=" * 70)
    print("  KORGym 游戏服务器启动调试")
    print("=" * 70)
    
    # 查找游戏文件
    project_root = Path(__file__).parent.parent
    game_lib_path = project_root / "KORGym" / "game_lib"
    game_2048_path = game_lib_path / "3-2048" / "game_lib.py"
    
    print(f"\n1. 检查文件路径:")
    print(f"   项目根目录: {project_root}")
    print(f"   游戏库目录: {game_lib_path}")
    print(f"   2048 游戏文件: {game_2048_path}")
    
    if not game_lib_path.exists():
        print(f"   ✗ 游戏库目录不存在: {game_lib_path}")
        print("\n   请确保 KORGym 文件夹在项目根目录下")
        return 1
    else:
        print(f"   ✓ 游戏库目录存在")
    
    if not game_2048_path.exists():
        print(f"   ✗ 2048 游戏文件不存在: {game_2048_path}")
        
        # 列出可用游戏
        print(f"\n   可用游戏:")
        for game_dir in sorted(game_lib_path.iterdir()):
            if game_dir.is_dir() and not game_dir.name.startswith('.'):
                game_file = game_dir / "game_lib.py"
                if game_file.exists():
                    print(f"     ✓ {game_dir.name}")
                else:
                    print(f"     ✗ {game_dir.name} (缺少 game_lib.py)")
        return 1
    else:
        print(f"   ✓ 2048 游戏文件存在")
    
    # 测试 Python 运行
    print(f"\n2. 测试 Python 环境:")
    print(f"   Python 可执行文件: {sys.executable}")
    print(f"   Python 版本: {sys.version}")
    
    # 测试导入
    print(f"\n3. 测试依赖包:")
    required_packages = ['fastapi', 'uvicorn', 'gymnasium', 'requests']
    all_ok = True
    
    for pkg in required_packages:
        try:
            __import__(pkg)
            print(f"   ✓ {pkg}")
        except ImportError:
            print(f"   ✗ {pkg} (未安装)")
            all_ok = False
    
    if not all_ok:
        print("\n   请先安装依赖: bash setup_korgym_wsl.sh")
        return 1
    
    # 尝试启动服务器
    print(f"\n4. 尝试启动游戏服务器...")
    port = 8775
    game_dir = game_2048_path.parent
    
    print(f"   工作目录: {game_dir}")
    print(f"   命令: {sys.executable} game_lib.py -p {port} -H 0.0.0.0")
    print(f"   端口: {port}")
    
    try:
        process = subprocess.Popen(
            [sys.executable, "game_lib.py", "-p", str(port), "-H", "0.0.0.0"],
            cwd=game_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print(f"   ✓ 进程已启动 (PID: {process.pid})")
        
        # 等待并检查健康状态
        print(f"\n5. 等待服务器就绪...")
        
        for i in range(15):
            time.sleep(1)
            
            # 检查进程是否还在运行
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                print(f"   ✗ 服务器进程意外退出 (退出码: {process.returncode})")
                
                if stdout:
                    print(f"\n   标准输出:")
                    print("   " + "\n   ".join(stdout.split("\n")[:20]))
                
                if stderr:
                    print(f"\n   标准错误:")
                    print("   " + "\n   ".join(stderr.split("\n")[:20]))
                
                return 1
            
            # 尝试连接
            try:
                response = requests.get(f"http://localhost:{port}/docs", timeout=2)
                if response.status_code == 200:
                    print(f"   ✓ 服务器已就绪 ({i+1}秒)")
                    print(f"\n6. 测试 API 端点...")
                    
                    # 测试 generate 端点
                    try:
                        gen_response = requests.post(
                            f"http://localhost:{port}/generate",
                            json={"seed": 42, "level": 4},
                            timeout=5
                        )
                        
                        if gen_response.status_code == 200:
                            print(f"   ✓ /generate 端点正常")
                            data = gen_response.json()
                            print(f"   ✓ 游戏实例 ID: {data.get('instance_id', 'N/A')}")
                        else:
                            print(f"   ⚠ /generate 返回状态码: {gen_response.status_code}")
                            print(f"   响应: {gen_response.text[:200]}")
                    
                    except Exception as e:
                        print(f"   ✗ /generate 测试失败: {e}")
                    
                    print(f"\n" + "=" * 70)
                    print("  ✅ 服务器启动成功！")
                    print("=" * 70)
                    print(f"\n  API 文档: http://localhost:{port}/docs")
                    print(f"  可以运行: uv run python scripts/test_korgym_adapter.py")
                    print(f"\n  按 Ctrl+C 停止服务器...")
                    
                    try:
                        process.wait()
                    except KeyboardInterrupt:
                        print("\n\n  停止服务器...")
                        process.terminate()
                        process.wait(timeout=5)
                        print("  ✓ 服务器已停止")
                    
                    return 0
            
            except requests.exceptions.RequestException:
                print(f"   等待中... ({i+1}/15秒)")
        
        # 超时
        print(f"   ✗ 服务器未在 15 秒内就绪")
        
        # 获取输出
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        
        if stdout:
            print(f"\n   标准输出:")
            print("   " + "\n   ".join(stdout.split("\n")[:30]))
        
        if stderr:
            print(f"\n   标准错误:")
            print("   " + "\n   ".join(stderr.split("\n")[:30]))
        
        return 1
    
    except Exception as e:
        print(f"   ✗ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())











