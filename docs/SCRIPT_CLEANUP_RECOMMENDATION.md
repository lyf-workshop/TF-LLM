# 根目录脚本清理建议

**分析日期**: 2026-03-16  
**总脚本数**: 26个（12个.sh + 11个.bat + 3个.py）

---

## 🔍 脚本分类分析

### ✅ 保留（7个）- 核心功能脚本

#### 安装和环境
1. ✅ `install_all_dependencies.sh` - 依赖安装（Shell）
2. ✅ `install_all_dependencies.bat` - 依赖安装（Windows）
3. ✅ `setup_korgym_wsl.sh` - KORGym WSL环境设置

#### 核心功能
4. ✅ `activate_korgym.sh` - 激活KORGym环境
5. ✅ `Qwen2.5-7B快速命令.sh` - Qwen 7B快速命令
6. ✅ `Qwen优化版完整流程.sh` - Qwen优化流程

#### 修复工具（可选保留）
7. ⚠️ `fix_ipython_jedi.py` - IPython修复（可移到scripts/utils/）
8. ⚠️ `fix_ipython_jedi.sh` - IPython修复脚本

---

### ❌ 建议删除（19个）- 临时测试/一次性脚本

#### 测试脚本（10个）- **全部删除**

**Python测试脚本**（2个）:
1. ❌ `test_zhizengzeng_api.py` - 智增增API测试（一次性测试）
   - 理由：特定API提供商测试，已完成验证
   
2. ❌ `test_practice_config_loading.py` - 配置加载测试（开发调试）
   - 理由：应该在tests/目录下，或已被正式测试替代

**Shell测试脚本**（2个）:
3. ❌ `test_korgym_env.sh` - 环境测试（一次性）
   - 理由：环境设置后的验证脚本，不需要常驻根目录
   
4. ❌ `test_qwen_optimization.sh` - Qwen优化测试（临时）
   - 理由：临时性能测试，非生产必需

5. ❌ `test_view_datasets.sh` - 数据集查看测试（调试用）
   - 理由：功能已集成到scripts/view_dataset.py

**Batch测试脚本**（6个）:
6. ❌ `test_conversation_history_fix.bat` - 对话历史修复测试
   - 理由：特定bug修复的验证脚本，已过时
   
7. ❌ `test_korgym_experience_fix.bat` - 经验修复测试
   - 理由：特定功能测试，已验证完成
   
8. ❌ `test_manual_experiences.bat` - 手动经验测试
   - 理由：开发调试脚本，非生产用途
   
9. ❌ `test_view_datasets.bat` - 数据集查看测试
   - 理由：功能重复，已有正式脚本
   
10. ❌ `test_wordle_compact_history.bat` - Wordle紧凑历史测试
    - 理由：特定优化的验证脚本，功能已稳定
    
11. ❌ `test_zhizengzeng_api.bat` - 智增增API测试
    - 理由：对应Python脚本的启动器，一并删除

---

#### 清理脚本（3个）- **过时/功能重复**

12. ❌ `cleanup_and_rerun_alphabetical_sorting.sh` - 清理重跑（功能重复）
    - 理由：应该在scripts/目录，且功能可被其他脚本替代
    
13. ❌ `cleanup_and_rerun_wordle.sh` - 清理重跑（功能重复）
    - 理由：同上
    
14. ❌ `cleanup_and_rerun_word_puzzle.sh` - 清理重跑（功能重复）
    - 理由：同上

---

#### 组织脚本（4个）- **一次性工具**

15. ❌ `cleanup_root.bat` - 根目录清理（一次性）
    - 理由：项目组织脚本，执行一次后不再需要
    
16. ❌ `organize_scripts.bat` - 脚本组织（一次性）
    - 理由：同上，项目重组工具
    
17. ❌ `analyze_l0_duplicates.bat` - L0去重分析（调试）
    - 理由：开发期间的分析工具，功能已稳定
    
18. ❌ `verify_experience_filtering.bat` - 经验过滤验证（调试）
    - 理由：特定功能验证，已完成

---

## 📊 删除统计

| 类别 | 删除数量 | 保留数量 | 删除率 |
|------|---------|---------|--------|
| **测试脚本** | 10 | 0 | 100% |
| **清理脚本** | 3 | 0 | 100% |
| **组织工具** | 4 | 0 | 100% |
| **修复工具** | 2 | 0 | 100% |
| **总计** | **19** | **7** | **73%** |

---

## 🎯 执行建议

### 立即删除（19个文件）

**分组1: 测试脚本**（10个）
```bash
# Python测试
rm test_zhizengzeng_api.py
rm test_practice_config_loading.py

# Shell测试
rm test_korgym_env.sh
rm test_qwen_optimization.sh
rm test_view_datasets.sh

# Batch测试
rm test_conversation_history_fix.bat
rm test_korgym_experience_fix.bat
rm test_manual_experiences.bat
rm test_view_datasets.bat
rm test_wordle_compact_history.bat
rm test_zhizengzeng_api.bat
```

**分组2: 清理脚本**（3个）
```bash
rm cleanup_and_rerun_alphabetical_sorting.sh
rm cleanup_and_rerun_wordle.sh
rm cleanup_and_rerun_word_puzzle.sh
```

**分组3: 组织工具**（4个）
```bash
rm cleanup_root.bat
rm organize_scripts.bat
rm analyze_l0_duplicates.bat
rm verify_experience_filtering.bat
```

**分组4: 修复工具**（2个）
```bash
rm fix_ipython_jedi.py
rm fix_ipython_jedi.sh
```

---

### 保留（7个文件）

**核心安装和环境**:
- `install_all_dependencies.sh`
- `install_all_dependencies.bat`
- `setup_korgym_wsl.sh`
- `activate_korgym.sh`

**快速命令**:
- `Qwen2.5-7B快速命令.sh`
- `Qwen优化版完整流程.sh`

---

## ✅ 删除理由总结

### 1. 测试脚本（10个）
- **特点**: 文件名以 `test_` 开头
- **用途**: 开发和调试阶段的临时验证
- **理由**: 
  - ✓ 功能已验证完成
  - ✓ 不是生产环境必需
  - ✓ 应该在 `tests/` 目录或完全移除

### 2. 清理重跑脚本（3个）
- **特点**: `cleanup_and_rerun_*.sh`
- **用途**: 清理缓存并重新运行实验
- **理由**:
  - ✓ 功能可被 `scripts/` 下的脚本替代
  - ✓ 不应该在根目录
  - ✓ 三个脚本高度重复

### 3. 组织工具（4个）
- **特点**: 一次性项目整理工具
- **用途**: 重组项目结构、分析代码
- **理由**:
  - ✓ 已完成使命（项目已整理）
  - ✓ 不会再次使用
  - ✓ 保留会造成混淆

### 4. 修复工具（2个）
- **特点**: 修复特定依赖问题
- **用途**: 解决 IPython/jedi 冲突
- **理由**:
  - ✓ 如果问题已解决，不再需要
  - ✓ 如果需要保留，应移到 `scripts/utils/`
  - ✓ 根目录不应该有修复脚本

---

## 🔒 安全确认

### 为什么可以安全删除？

1. **不影响核心功能**: 所有删除的脚本都是辅助性质
2. **有Git保护**: 可以随时从历史恢复
3. **保留了关键脚本**: 安装、环境设置、核心流程都保留
4. **遵循最佳实践**: 测试应该在tests/，工具应该在scripts/

### 删除前检查

- [ ] 确认这些脚本没有在CI/CD中使用
- [ ] 确认文档中没有引用这些脚本
- [ ] 确认其他脚本没有调用这些文件
- [ ] 创建Git提交点以便回滚

---

## 📈 预期效果

### 根目录文件统计

| 项目 | 删除前 | 删除后 | 改善 |
|------|--------|--------|------|
| **总文件数** | 56 | 37 | **-34%** |
| **脚本文件** | 26 | 7 | **-73%** |
| **Shell脚本** | 12 | 2 | **-83%** |
| **Batch脚本** | 11 | 2 | **-82%** |
| **Python脚本** | 3 | 3 | 0% |

### 根目录清晰度

**删除前**: 
```
56个文件 = 4个核心文档 + 13个配置 + 26个脚本 + 13个其他
         ❌ 混乱，难以导航
```

**删除后**:
```
37个文件 = 4个核心文档 + 13个配置 + 7个脚本 + 13个其他
         ✅ 清晰，易于理解
```

---

## 🚀 立即执行

**一键删除命令**（PowerShell）:
```powershell
# 删除所有建议删除的脚本（19个）
$filesToDelete = @(
    "test_zhizengzeng_api.py",
    "test_practice_config_loading.py",
    "test_korgym_env.sh",
    "test_qwen_optimization.sh",
    "test_view_datasets.sh",
    "test_conversation_history_fix.bat",
    "test_korgym_experience_fix.bat",
    "test_manual_experiences.bat",
    "test_view_datasets.bat",
    "test_wordle_compact_history.bat",
    "test_zhizengzeng_api.bat",
    "cleanup_and_rerun_alphabetical_sorting.sh",
    "cleanup_and_rerun_wordle.sh",
    "cleanup_and_rerun_word_puzzle.sh",
    "cleanup_root.bat",
    "organize_scripts.bat",
    "analyze_l0_duplicates.bat",
    "verify_experience_filtering.bat",
    "fix_ipython_jedi.py",
    "fix_ipython_jedi.sh"
)

foreach ($file in $filesToDelete) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "✓ 已删除: $file"
    }
}

Write-Host "`n完成！已删除 19 个脚本文件"
```

---

*分析完成时间: 2026-03-16*  
*建议删除: 19个文件（73%的脚本）*  
*风险评估: 低（都是临时/测试脚本）*
