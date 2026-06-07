@echo off
chcp 65001 >nul
echo ========================================
echo  Content Agent Windows 依赖准备脚本
echo ========================================
echo.

REM 检查是否已有 Node.js
where node >nul 2>nul
if %errorlevel% == 0 (
    echo [✓] 检测到系统 Node.js
    node --version
) else (
    echo [!] 未检测到系统 Node.js，将使用内置的 node.exe
)

echo.
echo [→] 正在安装 kuaifa 及其依赖（含 Windows 版 sharp）...
echo.

cd /d "%~dp0\..\bin"

REM 如果没有 node.exe，下载 Windows 版 Node.js
if not exist "node.exe" (
    echo [→] 未发现 node.exe，正在下载 Node.js v20.x 中文镜像...
    powershell -Command "Invoke-WebRequest -Uri 'https://npmmirror.com/mirrors/node/v20.18.1/win-x64/node.exe' -OutFile 'node.exe' -UseBasicParsing"
    if not exist "node.exe" (
        echo [✗] node.exe 下载失败，请手动下载并放置到 bin/ 目录
        pause
        exit /b 1
    )
    echo [✓] node.exe 下载完成
    echo.
)

REM 清理旧的 macOS/Linux 版本依赖（如果存在）
if exist "node_modules\@img\sharp-darwin-arm64" (
    echo [→] 清理 macOS 版 sharp 依赖...
    rmdir /s /q "node_modules\@img\sharp-darwin-arm64" 2>nul
    rmdir /s /q "node_modules\@img\sharp-libvips-darwin-arm64" 2>nul
    rmdir /s /q "node_modules\@img\sharp-darwin-x64" 2>nul
    rmdir /s /q "node_modules\@img\sharp-libvips-darwin-x64" 2>nul
)
if exist "node_modules\@img\sharp-linux-x64" (
    echo [→] 清理 Linux 版 sharp 依赖...
    rmdir /s /q "node_modules\@img\sharp-linux-x64" 2>nul
    rmdir /s /q "node_modules\@img\sharp-libvips-linux-x64" 2>nul
)

REM 重新安装以获取 Windows 版本的原生模块
if exist "node.exe" (
    echo [→] 使用内置 node.exe 运行 npm install...
    call node.exe "%~dp0\..\bin\node_modules\npm\bin\npm-cli.js" install --registry https://registry.npmmirror.com
    if %errorlevel% neq 0 (
        echo [✗] npm install 失败，尝试使用系统 npm...
        call npm install --registry https://registry.npmmirror.com
    )
) else (
    echo [→] 使用系统 npm install...
    call npm install --registry https://registry.npmmirror.com
)

if %errorlevel% neq 0 (
    echo.
    echo [✗] 依赖安装失败，请检查网络连接或更换 npm 源。
    pause
    exit /b 1
)

echo.
echo [✓] 依赖安装完成！
echo [✓] Windows 版 sharp 已就绪。
echo.
pause
