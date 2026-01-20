# GitHub 上传完整指南

本指南帮助你将 Youtu-Agent KORGym 实验项目上传到你自己的 GitHub 仓库。

## 📊 项目情况说明

### 原始项目
- **名称**: Youtu-Agent
- **作者**: Tencent Youtu Lab
- **原始仓库**: https://github.com/TencentCloudADP/youtu-agent
- **许可证**: MIT License（允许自由使用和修改）

### 你的版本
- **基于**: Tencent Youtu-Agent
- **特色**: 添加了完整的 KORGym 文档和实验配置
- **状态**: 已在本地 Git 仓库，准备上传到你的 GitHub

---

## 🚀 上传步骤（完整版）

### 步骤 1: 在 GitHub 创建新仓库

1. **访问**: https://github.com/new

2. **填写仓库信息**:
   ```
   Repository name: youtu-agent-korgym
   Description: KORGym游戏实验框架 - 基于Tencent Youtu-Agent
   
   Public: ○ (如果你想公开分享)
   Private: ○ (如果只是个人使用)
   
   ☐ Add a README file (不要勾选)
   ☐ Add .gitignore (不要勾选)
   ☐ Choose a license (不要勾选)
   ```

3. **点击**: "Create repository"

4. **复制仓库 URL**（在创建后的页面会显示）:
   ```
   https://github.com/你的用户名/youtu-agent-korgym.git
   ```

---

### 步骤 2: 配置远程仓库

在 PowerShell 中执行：

```powershell
# 进入项目目录
cd F:\youtu-agent

# 添加你的 GitHub 仓库（替换成你复制的 URL）
git remote add origin https://github.com/你的用户名/youtu-agent-korgym.git

# 验证配置
git remote -v
```

**应该看到**:
```
origin  https://github.com/你的用户名/youtu-agent-korgym.git (fetch)
origin  https://github.com/你的用户名/youtu-agent-korgym.git (push)
```

---

### 步骤 3: 推送代码

#### 3.1 如果网络正常

```powershell
# 直接推送
git push -u origin main
```

#### 3.2 如果需要配置代理（国内用户）

```powershell
# 配置代理（替换成你的代理端口，通常是 7890 或 7891）
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890

# 推送
git push -u origin main
```

#### 3.3 如果推送时要求身份验证

**使用 Personal Access Token (推荐)**:

1. **创建 Token**:
   - 访问: https://github.com/settings/tokens
   - 点击: "Generate new token" → "Generate new token (classic)"
   - 勾选: `repo` 权限
   - 生成并**复制** token（只显示一次！）

2. **推送时使用 Token**:
   ```
   Username: 你的GitHub用户名
   Password: 粘贴你的Personal Access Token
   ```

---

### 步骤 4: 验证上传成功

推送成功后，访问你的 GitHub 仓库页面:
```
https://github.com/你的用户名/youtu-agent-korgym
```

应该能看到：
- ✅ 所有文件已上传
- ✅ 提交历史显示正确
- ✅ README.md 正常显示

---

## 📝 可选：更新 README

为了说明这是基于原项目的修改版本，建议更新 README.md：

### 选项 A: 在顶部添加说明（推荐）

在 `README.md` 文件顶部添加：

```markdown
> **注**: 本项目基于 [Tencent Youtu-Agent](https://github.com/TencentCloudADP/youtu-agent) 开发，
> 专注于 KORGym 游戏环境的实验和研究。添加了完整的 KORGym 文档、配置和工具。

---

# Youtu-Agent: A simple yet powerful agent framework...
(原有内容)
```

### 选项 B: 使用我创建的 README

我已经创建了一个 `README_KORGYM_FORK.md`，你可以：

```powershell
# 备份原 README
mv README.md README_ORIGINAL.md

# 使用新的 README
mv README_KORGYM_FORK.md README.md

# 提交更新
git add README.md README_ORIGINAL.md
git commit -m "docs: 更新 README 说明这是 KORGym 实验版本"
git push origin main
```

---

## 🔒 重要提醒：遵守 MIT License

由于原项目使用 MIT License，你**必须**：

1. ✅ **保留 LICENSE 文件**（已经有了，不要删除）
2. ✅ **保留原始版权声明**（LICENSE 文件中的 Copyright 声明）
3. ✅ **说明项目来源**（在 README 中注明基于 Tencent Youtu-Agent）

你**可以**：
- ✅ 自由修改和使用代码
- ✅ 商业使用
- ✅ 分发你的版本
- ✅ 添加你自己的版权声明（但不能移除原始声明）

---

## 📋 完整操作命令（复制粘贴）

```powershell
# === 步骤 1: 创建 GitHub 仓库（在网页完成）===
# https://github.com/new
# 仓库名: youtu-agent-korgym
# 其他选项都不勾选

# === 步骤 2: 添加远程仓库 ===
cd F:\youtu-agent
git remote add origin https://github.com/你的用户名/youtu-agent-korgym.git

# === 步骤 3: 验证远程仓库 ===
git remote -v

# === 步骤 4: 配置代理（如果需要）===
# 替换 7890 为你的实际代理端口
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890

# === 步骤 5: 推送代码 ===
git push -u origin main

# === 步骤 6: 验证（访问你的仓库页面）===
# https://github.com/你的用户名/youtu-agent-korgym
```

---

## 🐛 常见问题

### Q1: 推送时提示认证失败

**解决**: 使用 Personal Access Token：
1. 创建 Token: https://github.com/settings/tokens
2. 推送时用 Token 作为密码

### Q2: 连接超时或被重置

**解决**: 配置代理或使用 SSH：
```powershell
# 方法1: 配置代理
git config --global http.proxy http://127.0.0.1:7890

# 方法2: 使用 SSH
git remote set-url origin git@github.com:你的用户名/youtu-agent-korgym.git
git push -u origin main
```

### Q3: 文件太大

**解决**: Git 有文件大小限制（100MB）
```powershell
# 检查大文件
git ls-files | ForEach-Object { 
    $size = (Get-Item $_).Length / 1MB
    if ($size -gt 50) { 
        Write-Host "$_ : $([math]::Round($size, 2)) MB" 
    }
}

# 如果有大文件，添加到 .gitignore
echo "大文件路径" >> .gitignore
git rm --cached 大文件路径
git commit --amend
```

---

## ✅ 检查清单

上传前确认：

- [ ] 已在 GitHub 创建新仓库
- [ ] 已添加远程仓库配置
- [ ] `.env` 等敏感文件已在 `.gitignore` 中
- [ ] LICENSE 文件保持完整
- [ ] （可选）README 中说明了项目来源

上传后确认：

- [ ] GitHub 页面能看到所有文件
- [ ] 提交历史正确
- [ ] README 正常显示
- [ ] （可选）GitHub Actions 正常运行

---

## 🎉 完成后

你将拥有：
- ✅ 完整的 KORGym 实验框架（本地 + GitHub）
- ✅ 详细的文档体系
- ✅ 可以继续改进和分享的代码库

**需要我帮你执行具体的命令吗？** 告诉我你的 GitHub 用户名和仓库名，我可以帮你生成准确的命令。



