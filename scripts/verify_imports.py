#!/usr/bin/env python3
"""Quick script to verify all imports are working."""

print("Testing imports...")

try:
    from utu.config import ExperienceFilterConfig
    print("✅ ExperienceFilterConfig imported successfully")
except ImportError as e:
    print(f"❌ Failed to import ExperienceFilterConfig: {e}")
    exit(1)

try:
    from utu.eval.experience_filter import ExperienceFilter
    print("✅ ExperienceFilter imported successfully")
except ImportError as e:
    print(f"❌ Failed to import ExperienceFilter: {e}")
    exit(1)

try:
    from utu.eval import BaseBenchmark
    print("✅ BaseBenchmark imported successfully")
except ImportError as e:
    print(f"❌ Failed to import BaseBenchmark: {e}")
    exit(1)

try:
    from utu.config import ConfigLoader
    config = ConfigLoader.load_eval_config("korgym/wordle_practice_20_eval")
    print(f"✅ Config loaded successfully: {config.exp_id}")
    print(f"   Experience filter enabled: {config.experience_filter.enabled}")
    if config.experience_filter.enabled:
        print(f"   max_l2={config.experience_filter.max_l2}, max_l1={config.experience_filter.max_l1}, max_l0={config.experience_filter.max_l0}")
except Exception as e:
    print(f"❌ Failed to load config: {e}")
    exit(1)

print("\n🎉 All imports working correctly!")
