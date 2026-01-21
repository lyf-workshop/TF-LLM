"""
测试KORGym游戏服务器
Test KORGym game server connectivity and functionality
"""
import argparse
import json
import requests


def test_server(host: str, port: int, game_name: str):
    """测试游戏服务器"""
    
    base_url = f"http://{host}:{port}"
    
    print("=" * 70)
    print(f"测试 KORGym 游戏服务器: {game_name}")
    print("=" * 70)
    print(f"服务器地址: {base_url}")
    print("")
    
    # 测试1: 检查服务器是否运行
    print("1️⃣  测试服务器连接...")
    try:
        resp = requests.get(f"{base_url}/docs", timeout=5)
        if resp.status_code == 200:
            print("   ✅ 服务器正在运行")
        else:
            print(f"   ⚠️  服务器响应异常: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ 无法连接到服务器: {e}")
        print("")
        print("请确保游戏服务器已启动：")
        print(f"  cd KORGym/game_lib/{game_name}")
        print(f"  python game_lib.py -p {port}")
        return
    
    print("")
    
    # 测试2: 测试生成游戏实例
    print("2️⃣  测试生成游戏实例 (seed=42)...")
    try:
        resp = requests.post(
            f"{base_url}/generate",
            json={"seed": 42},
            timeout=30
        )
        
        if resp.status_code == 200:
            game_state = resp.json()
            print("   ✅ 游戏实例生成成功")
            print(f"   游戏状态键: {list(game_state.keys())}")
            print(f"   分数: {game_state.get('score', 'N/A')}")
            print(f"   是否结束: {game_state.get('is_end', 'N/A')}")
            return game_state
        else:
            print(f"   ❌ 生成失败: HTTP {resp.status_code}")
            print(f"   响应: {resp.text[:200]}")
            
    except Exception as e:
        print(f"   ❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("")
    return None


def test_verify(host: str, port: int, game_state: dict, test_action: str):
    """测试验证功能"""
    
    base_url = f"http://{host}:{port}"
    
    print("3️⃣  测试验证功能...")
    
    if not game_state:
        print("   ⚠️  跳过（游戏状态为空）")
        return
    
    # 添加测试动作
    game_state['action'] = test_action
    
    try:
        resp = requests.post(
            f"{base_url}/verify",
            json=game_state,
            timeout=30
        )
        
        if resp.status_code == 200:
            result = resp.json()
            print("   ✅ 验证成功")
            print(f"   分数: {result.get('score', 'N/A')}")
            print(f"   是否结束: {result.get('is_end', 'N/A')}")
        else:
            print(f"   ❌ 验证失败: HTTP {resp.status_code}")
            print(f"   响应: {resp.text[:200]}")
            
    except Exception as e:
        print(f"   ❌ 验证失败: {e}")
    
    print("")


def main():
    parser = argparse.ArgumentParser(description="测试KORGym游戏服务器")
    parser.add_argument("--host", type=str, default="localhost", help="服务器地址")
    parser.add_argument("--port", type=int, default=8775, help="服务器端口")
    parser.add_argument("--game_name", type=str, default="8-word_puzzle", help="游戏名称")
    parser.add_argument("--test_action", type=str, default='["test", "word"]', help="测试动作")
    
    args = parser.parse_args()
    
    # 测试服务器
    game_state = test_server(args.host, args.port, args.game_name)
    
    # 测试验证
    if game_state:
        test_verify(args.host, args.port, game_state, args.test_action)
    
    print("=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()

