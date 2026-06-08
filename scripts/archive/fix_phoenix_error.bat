@echo off
REM 修复Phoenix tracing连接错误的Windows批处理脚本

echo ==========================================================================
echo 修复Phoenix Tracing连接错误
echo Fix Phoenix Tracing Connection Error
echo ==========================================================================
echo.

if not exist .env (
    echo 未找到.env文件，从模板创建...
    copy env.template .env
    echo [Y] .env文件已创建
    echo.
    echo 请编辑.env文件，填写你的API密钥：
    echo   LLM_API_KEY=your-api-key-here
    echo.
    echo 关于Phoenix配置：
    echo   如果不需要详细监控，请确保Phoenix配置是注释掉的（行首有#号）
    echo   PHOENIX_ENDPOINT和PHOENIX_PROJECT_NAME应该被注释
    echo.
    pause
    exit /b 0
)

echo 检查到.env文件存在
echo.
echo 这个错误的原因：
echo   代码尝试连接Phoenix服务器(http://127.0.0.1:6006)
echo   但Phoenix服务器没有运行
echo.
echo 解决方案：
echo.
echo [1] 禁用Phoenix Tracing（推荐）
echo     - 在.env文件中注释掉PHOENIX_ENDPOINT和PHOENIX_PROJECT_NAME
echo     - 实验可以正常运行，只是没有详细trace
echo.
echo [2] 启动Phoenix服务器
echo     - 在另一个PowerShell/命令行窗口运行: phoenix serve
echo     - 需要先安装: pip install arize-phoenix
echo.
echo [3] 手动编辑.env文件
echo.

choice /C 123 /N /M "请选择 [1/2/3]: "

if errorlevel 3 goto manual_edit
if errorlevel 2 goto start_phoenix
if errorlevel 1 goto disable_phoenix

:disable_phoenix
echo.
echo 正在准备禁用Phoenix...
echo.
echo 请手动编辑.env文件，在以下行前面添加 # 号：
echo   PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
echo   PHOENIX_PROJECT_NAME=Youtu-Agent
echo.
echo 改为：
echo   # PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
echo   # PHOENIX_PROJECT_NAME=Youtu-Agent
echo.
notepad .env
echo.
echo 保存后重新运行实验即可。
goto end

:start_phoenix
echo.
echo ==========================================================================
echo 启动Phoenix服务器
echo ==========================================================================
echo.
echo 在另一个PowerShell或命令行窗口中运行：
echo.
echo   # 安装Phoenix（如果还没安装）
echo   pip install arize-phoenix
echo.
echo   # 启动Phoenix服务器
echo   phoenix serve
echo.
echo Phoenix启动后，在浏览器访问: http://127.0.0.1:6006
echo.
echo 确保.env文件中有以下配置（去掉#号）：
echo   PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
echo   PHOENIX_PROJECT_NAME=Youtu-Agent-Paper-Exp
echo.
goto end

:manual_edit
echo.
echo 正在打开.env文件...
notepad .env
echo.
echo 提示：
echo   - 不需要Phoenix：在PHOENIX配置行前加 # 号
echo   - 需要Phoenix：去掉PHOENIX配置行前的 # 号，并确保Phoenix服务器运行
echo.
goto end

:end
echo.
echo ==========================================================================
echo 重要提示
echo ==========================================================================
echo.
echo 这个错误不会影响实验运行，只会影响trace记录。
echo 如果不需要详细的运行监控和可视化，直接禁用Phoenix即可。
echo.
echo Phoenix的作用：
echo   - 提供Web UI查看详细的运行trace
echo   - 可视化agent的决策过程
echo   - 对于复现论文实验不是必需的
echo.
pause

