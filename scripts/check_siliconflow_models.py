#!/usr/bin/env python3
"""检查硅基流动可用的模型列表"""

import os
import asyncio
from openai import AsyncOpenAI


async def list_models():
    """列出硅基流动可用的模型"""
    api_key = os.getenv("UTU_LLM_API_KEY")
    base_url = os.getenv("UTU_LLM_BASE_URL", "https://api.siliconflow.cn/v1")
    
    if not api_key:
        print("❌ 未设置 UTU_LLM_API_KEY")
        return
    
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    try:
        print("\n" + "="*70)
        print("硅基流动可用模型列表")
        print("="*70 + "\n")
        
        models = await client.models.list()
        
        # 筛选 DeepSeek 相关模型
        deepseek_models = [m for m in models.data if "deepseek" in m.id.lower()]
        
        print("📋 DeepSeek 系列模型:\n")
        for model in deepseek_models:
            print(f"  • {model.id}")
        
        print(f"\n共找到 {len(deepseek_models)} 个 DeepSeek 模型")
        print(f"所有模型总数: {len(models.data)}")
        
        print("\n" + "="*70)
        print("推荐配置")
        print("="*70 + "\n")
        
        if deepseek_models:
            # 找最新的 DeepSeek-V3 模型
            v3_models = [m for m in deepseek_models if "v3" in m.id.lower()]
            if v3_models:
                recommended = v3_models[0].id
            else:
                recommended = deepseek_models[0].id
            
            print(f"推荐使用: {recommended}")
            print(f"\n在 .env 文件中设置:")
            print(f"  UTU_LLM_MODEL={recommended}")
        
    except Exception as e:
        print(f"❌ 获取模型列表失败: {e}")
        print("\n可能的原因:")
        print("  1. API Key 无效")
        print("  2. 网络连接问题")
        print("  3. 硅基流动 API 不支持列出模型")


if __name__ == "__main__":
    asyncio.run(list_models())

