"""
检查模型配置
Check model configuration
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.config import ConfigLoader


def check_env_vars():
    """检查环境变量"""
    print("\n" + "=" * 70)
    print("环境变量配置")
    print("=" * 70 + "\n")
    
    env_vars = [
        "UTU_LLM_TYPE",
        "UTU_LLM_MODEL",
        "UTU_LLM_BASE_URL",
        "UTU_LLM_API_KEY",
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if var == "UTU_LLM_API_KEY" and value:
            # 隐藏 API key
            value = value[:10] + "..." if len(value) > 10 else "***"
        print(f"  {var}: {value if value else '(未设置)'}")
    
    print("\n" + "=" * 70 + "\n")


def check_agent_config():
    """检查 agent 配置"""
    print("=" * 70)
    print("Agent 配置")
    print("=" * 70 + "\n")
    
    try:
        # 加载 ZebraLogic agent 配置
        config = ConfigLoader.load_eval_config("eval/logic/logic_zebralogic_test")
        
        print(f"Agent 名称: {config.agent.name}")
        print(f"最大轮次: {config.max_turns}")
        print(f"\n模型提供商配置:")
        print(f"  类型: {config.model.model_provider.type}")
        print(f"  模型: {config.model.model_provider.model}")
        print(f"  Base URL: {config.model.model_provider.base_url if hasattr(config.model.model_provider, 'base_url') else '(默认)'}")
        
        print(f"\n模型设置:")
        if hasattr(config.model, 'model_settings'):
            settings = config.model.model_settings
            if hasattr(settings, 'temperature'):
                print(f"  Temperature: {settings.temperature}")
            if hasattr(settings, 'top_p'):
                print(f"  Top P: {settings.top_p}")
            if hasattr(settings, 'max_tokens'):
                print(f"  Max Tokens: {settings.max_tokens}")
        
        print(f"\nInstructions (前200字符):")
        instructions = config.agent.instructions[:200] if config.agent.instructions else "None"
        print(f"  {instructions}...")
        
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70 + "\n")


def test_model_call():
    """测试模型调用"""
    print("=" * 70)
    print("测试模型调用")
    print("=" * 70 + "\n")
    
    try:
        from utu.utils import SimplifiedAsyncOpenAI
        
        # 从环境变量获取配置
        llm_type = os.getenv("UTU_LLM_TYPE", "openai")
        llm_model = os.getenv("UTU_LLM_MODEL", "gpt-4")
        base_url = os.getenv("UTU_LLM_BASE_URL")
        api_key = os.getenv("UTU_LLM_API_KEY")
        
        print(f"使用配置:")
        print(f"  Type: {llm_type}")
        print(f"  Model: {llm_model}")
        print(f"  Base URL: {base_url if base_url else '(默认)'}")
        print(f"  API Key: {'已设置' if api_key else '未设置'}")
        
        if not api_key:
            print("\n⚠️  API Key 未设置，跳过测试调用")
            return
        
        print("\n发送测试请求...")
        
        import asyncio
        
        async def test():
            # SimplifiedAsyncOpenAI 会自动从环境变量读取配置
            # type 默认是 "chat.completions"
            client = SimplifiedAsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=llm_model,  # 作为默认配置
            )
            
            # 使用 query_one 方法发送请求
            response = await client.query_one(
                messages=[{"role": "user", "content": "Say 'Hello, World!' in exactly 3 words."}],
                temperature=0.3,
            )
            
            return response
        
        response = asyncio.run(test())
        
        print(f"\n✅ 测试成功！")
        print(f"模型响应: {response}")
        
        # 检查响应是否是乱码
        if any(ord(c) > 127 for c in response[:50]):
            print("\n⚠️  警告: 响应包含非ASCII字符，可能有编码问题")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    check_env_vars()
    check_agent_config()
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-call", action="store_true", help="测试模型调用")
    args = parser.parse_args()
    
    if args.test_call:
        test_model_call()

