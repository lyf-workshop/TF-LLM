"""
分析 L0 经验的重复情况

帮助诊断去重机制是否有效
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def tokenize(text: str) -> set[str]:
    """Tokenize text for similarity comparison."""
    cleaned = []
    for ch in (text or "").lower():
        cleaned.append(ch if ch.isalnum() else " ")
    return {w for w in "".join(cleaned).split() if w}


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Calculate Jaccard similarity."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def analyze_l0_duplicates(exp_file: Path, similarity_threshold: float = 0.85):
    """Analyze L0 duplicates in an experience file."""
    
    # Fix encoding for Windows console
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("\n" + "="*80)
    print(f"分析文件: {exp_file.name}")
    print("="*80 + "\n")
    
    # Load experiences
    with open(exp_file, encoding='utf-8') as f:
        data = json.load(f)
    
    l0_experiences = data.get('l0_experiences', [])
    
    if not l0_experiences:
        print("⚠️ 没有 L0 经验\n")
        return
    
    print(f"📊 总计 {len(l0_experiences)} 个 L0 经验\n")
    
    # Analyze scope distribution
    scope_counts = defaultdict(int)
    no_scope_count = 0
    
    for exp in l0_experiences:
        scope = exp.get('scope_key')
        if scope:
            scope_counts[scope] += 1
        else:
            no_scope_count += 1
    
    print("📍 Scope 分布:")
    for scope, count in sorted(scope_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {scope}: {count} 个")
    if no_scope_count > 0:
        print(f"  - (无 scope): {no_scope_count} 个 ⚠️")
    print()
    
    # Find duplicates
    print(f"🔍 查找重复（相似度 >= {similarity_threshold}）:\n")
    
    duplicates = []
    checked_pairs = set()
    
    for i, exp_a in enumerate(l0_experiences):
        content_a = exp_a.get('content', '')
        tokens_a = tokenize(content_a)
        scope_a = exp_a.get('scope_key')
        
        for j, exp_b in enumerate(l0_experiences):
            if i >= j:  # Skip self and already checked pairs
                continue
            
            pair_key = (i, j)
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            
            content_b = exp_b.get('content', '')
            tokens_b = tokenize(content_b)
            scope_b = exp_b.get('scope_key')
            
            similarity = jaccard_similarity(tokens_a, tokens_b)
            
            if similarity >= similarity_threshold:
                duplicates.append({
                    'exp_a': exp_a['id'],
                    'exp_b': exp_b['id'],
                    'similarity': similarity,
                    'scope_a': scope_a,
                    'scope_b': scope_b,
                    'same_scope': scope_a == scope_b,
                    'content_a_preview': content_a[:80] + '...' if len(content_a) > 80 else content_a,
                    'content_b_preview': content_b[:80] + '...' if len(content_b) > 80 else content_b,
                })
    
    if duplicates:
        print(f"❌ 发现 {len(duplicates)} 对重复/高度相似的经验:\n")
        
        for dup in duplicates[:10]:  # Show top 10
            print(f"  [{dup['exp_a']}] vs [{dup['exp_b']}]")
            print(f"    相似度: {dup['similarity']:.3f}")
            print(f"    Scope: {dup['scope_a']} vs {dup['scope_b']}")
            if dup['same_scope']:
                print(f"    ⚠️ 同一 scope 内的重复！")
            print(f"    内容 A: {dup['content_a_preview']}")
            print(f"    内容 B: {dup['content_b_preview']}")
            print()
        
        if len(duplicates) > 10:
            print(f"  ... 还有 {len(duplicates) - 10} 对重复（省略显示）\n")
    else:
        print("✅ 未发现重复经验\n")
    
    # Statistics
    print("="*80)
    print("📊 统计总结")
    print("="*80 + "\n")
    
    print(f"总 L0 数量: {len(l0_experiences)}")
    print(f"重复对数: {len(duplicates)}")
    print(f"去重率: {len(duplicates) / len(l0_experiences) * 100:.1f}%")
    print(f"无 scope 的经验: {no_scope_count} ({no_scope_count / len(l0_experiences) * 100:.1f}%)")
    
    if duplicates:
        same_scope_dups = sum(1 for d in duplicates if d['same_scope'])
        diff_scope_dups = len(duplicates) - same_scope_dups
        print(f"  - 同 scope 重复: {same_scope_dups}")
        print(f"  - 跨 scope 重复: {diff_scope_dups}")
    
    print()
    
    # Suggestions
    if duplicates:
        print("💡 建议:")
        if no_scope_count > len(l0_experiences) * 0.3:
            print("  1. ⚠️ 超过 30% 的经验没有 scope_key")
            print("     → 检查 prompt 模板是否包含 game_name/problem 等关键词")
            print()
        
        if same_scope_dups > 0:
            print("  2. ❌ 发现同 scope 内的重复")
            print("     → 去重机制未生效，检查代码逻辑")
            print()
        
        print("  3. 建议增强去重:")
        print("     - 降低相似度阈值（0.95 → 0.85-0.90）")
        print("     - 增加检查窗口（50 → 200 或全部）")
        print("     - 即使无 scope 也做全局去重")
        print()
    else:
        print("✅ 去重机制工作良好！\n")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="分析 L0 经验重复情况")
    parser.add_argument(
        '--exp_id',
        type=str,
        help='实验 ID（例如：wordle_practice_20_l4）'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.85,
        help='相似度阈值（默认 0.85）'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='分析所有分层经验文件'
    )
    
    args = parser.parse_args()
    
    exp_dir = Path(__file__).parent.parent / "workspace" / "hierarchical_experiences"
    
    if not exp_dir.exists():
        print(f"❌ 经验目录不存在: {exp_dir}")
        return
    
    # Get files to analyze
    if args.all:
        files = list(exp_dir.glob("*.json"))
        if not files:
            print(f"⚠️ 没有找到任何经验文件: {exp_dir}")
            return
        print(f"\n📁 找到 {len(files)} 个经验文件\n")
    elif args.exp_id:
        exp_file = exp_dir / f"{args.exp_id}.json"
        if not exp_file.exists():
            print(f"❌ 文件不存在: {exp_file}")
            return
        files = [exp_file]
    else:
        # Default: analyze most recent file
        files = sorted(exp_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not files:
            print(f"⚠️ 没有找到任何经验文件: {exp_dir}")
            return
        print(f"📁 默认分析最新的文件: {files[0].name}\n")
        files = [files[0]]
    
    # Analyze each file
    for exp_file in files:
        analyze_l0_duplicates(exp_file, args.threshold)
    
    print("="*80)
    print("✅ 分析完成")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
