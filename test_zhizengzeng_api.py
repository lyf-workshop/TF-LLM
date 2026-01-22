"""
测试智增增 API 连接

快速验证 API Key 和模型名称是否正确
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_api():
    """测试智增增 API"""
    
    print("\n" + "="*80)
    print("智增增 API 配置测试")
    print("="*80 + "\n")
    
    # 读取配置
    api_type = os.getenv('UTU_LLM_TYPE')
    model = os.getenv('UTU_LLM_MODEL')
    base_url = os.getenv('UTU_LLM_BASE_URL')
    api_key = os.getenv('UTU_LLM_API_KEY')
    
    print("当前配置：")
    print(f"  LLM Type: {api_type}")
    print(f"  Model: {model}")
    print(f"  Base URL: {base_url}")
    print(f"  API Key: {api_key[:20]}...{api_key[-10:] if api_key else 'None'}")
    print()
    
    # 验证配置
    errors = []
    
    if not base_url or 'zhizengzeng.com' not in base_url:
        errors.append("❌ Base URL 未设置为智增增 (应该是 https://api.zhizengzeng.com/v1)")
    else:
        print("✅ Base URL 正确（智增增）")
    
    if not model:
        errors.append("❌ 模型名称未设置")
    elif model == 'qwen2.5-72B-Instruct':
        errors.append("⚠️ 模型名称使用了大写 B，应该改为 qwen2.5-72b-instruct（全小写）")
    elif model == 'qwen2.5-72b-instruct':
        print("✅ 模型名称正确（qwen2.5-72b-instruct）")
    elif 'Qwen/' in model:
        errors.append(f"⚠️ 模型名称使用了 'Qwen/' 前缀（硅基流动格式），智增增应该去掉前缀")
        errors.append(f"   当前：{model}")
        errors.append(f"   建议：{model.replace('Qwen/', '').replace('72B', '72b').lower()}")
    else:
        print(f"✅ 模型名称：{model}")
    
    if not api_key or not api_key.startswith('sk-'):
        errors.append("❌ API Key 未设置或格式错误")
    else:
        print("✅ API Key 格式正确")
    
    print()
    
    if errors:
        print("发现问题：")
        for error in errors:
            print(f"  {error}")
        print()
        return False
    
    # 测试 API 调用
    print("测试 API 连接...")
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        print(f"  发送测试请求到：{model}")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "请用一句话回答：1+1等于几？"}
            ],
            max_tokens=50,
            temperature=0.3
        )
        
        answer = response.choices[0].message.content
        usage = response.usage
        
        print(f"\n✅ API 测试成功！")
        print(f"  响应内容: {answer}")
        print(f"  Token 使用: 输入 {usage.prompt_tokens}, 输出 {usage.completion_tokens}")
        print(f"  预估费用: ￥{(usage.prompt_tokens * 0.004 + usage.completion_tokens * 0.012) / 1000:.6f}")
        print()
        print("="*80)
        print("✅ 智增增 API 配置正确，可以正常使用！")
        print("="*80)
        return True
        
    except Exception as e:
        print(f"\n❌ API 测试失败：{e}")
        print()
        print("可能的原因：")
        print("  1. API Key 无效或余额不足")
        print("  2. 模型名称错误")
        print("  3. 网络连接问题")
        print("  4. Base URL 错误")
        print()
        print("请检查：")
        print("  - 登录 https://api.zhizengzeng.com/ 查看余额")
        print("  - 确认模型名称为：qwen2.5-72b-instruct（全小写）")
        print("  - 尝试重新生成 API Key")
        return False


if __name__ == "__main__":
    success = test_api()
    sys.exit(0 if success else 1)
