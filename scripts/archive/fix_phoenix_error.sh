#!/bin/bash
# 修复Phoenix tracing连接错误的脚本

echo "=========================================================================="
echo "修复Phoenix Tracing连接错误"
echo "Fix Phoenix Tracing Connection Error"
echo "=========================================================================="
echo ""

# 检查.env文件
if [[ ! -f ".env" ]]; then
    echo "未找到.env文件，从模板创建..."
    cp env.template .env
    echo "✓ .env文件已创建"
    echo ""
    echo "请编辑.env文件，填写你的API密钥："
    echo "  LLM_API_KEY=your-api-key-here"
    echo ""
    exit 0
fi

echo "检查到.env文件存在"
echo ""
echo "选择修复方式："
echo ""
echo "[1] 禁用Phoenix Tracing（推荐，不影响实验）"
echo "    - 会注释掉.env中的PHOENIX配置"
echo "    - 实验可以正常运行，只是没有详细trace"
echo ""
echo "[2] 启动Phoenix服务器（需要在另一个终端）"
echo "    - 显示如何启动Phoenix"
echo "    - 保留.env中的PHOENIX配置"
echo ""
echo "[3] 查看当前.env配置"
echo ""

read -p "请选择 [1/2/3]: " choice

case $choice in
    1)
        echo ""
        echo "正在禁用Phoenix Tracing..."
        
        # 备份.env文件
        cp .env .env.backup
        echo "✓ 已备份.env为.env.backup"
        
        # 注释掉PHOENIX配置
        sed -i 's/^PHOENIX_ENDPOINT=/#PHOENIX_ENDPOINT=/' .env
        sed -i 's/^PHOENIX_PROJECT_NAME=/#PHOENIX_PROJECT_NAME=/' .env
        
        echo "✓ 已禁用Phoenix配置"
        echo ""
        echo "现在可以重新运行实验了！"
        echo ""
        ;;
    2)
        echo ""
        echo "=========================================================================="
        echo "启动Phoenix服务器"
        echo "=========================================================================="
        echo ""
        echo "在另一个终端窗口中运行以下命令："
        echo ""
        echo "  # 安装Phoenix（如果还没安装）"
        echo "  pip install arize-phoenix"
        echo ""
        echo "  # 启动Phoenix服务器"
        echo "  phoenix serve"
        echo ""
        echo "Phoenix启动后，在浏览器访问: http://127.0.0.1:6006"
        echo ""
        echo "确保.env文件中有以下配置："
        echo "  PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces"
        echo "  PHOENIX_PROJECT_NAME=Youtu-Agent-Paper-Exp"
        echo ""
        ;;
    3)
        echo ""
        echo "=========================================================================="
        echo ".env文件内容（Phoenix相关配置）："
        echo "=========================================================================="
        echo ""
        grep -E "PHOENIX|phoenix" .env || echo "未找到Phoenix配置"
        echo ""
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo ""
echo "提示：这个错误不会影响实验运行，只会影响trace记录。"
echo "      如果不需要详细的运行监控，选择禁用即可。"
echo ""

