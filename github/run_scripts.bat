@echo off
chcp 65001 >nul
echo ========================================
echo 开始执行脚本序列
echo ========================================

echo.
echo [1/2] 正在执行 check_models.py...
python check_models.py
if %errorlevel% neq 0 (
    echo 错误: check_models.py 执行失败，错误代码: %errorlevel%
    pause
    exit /b %errorlevel%
)
echo check_models.py 执行完成！

echo.
echo [2/2] 正在执行 generate_folders.py...
python generate_folders.py
if %errorlevel% neq 0 (
    echo 错误: generate_folders.py 执行失败，错误代码: %errorlevel%
    pause
    exit /b %errorlevel%
)
echo generate_folders.py 执行完成！

echo.
echo ========================================
echo 所有脚本执行完成！
echo ========================================
pause 