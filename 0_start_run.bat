@echo off
REM 检查是否在虚拟环境中
if "%VIRTUAL_ENV%"=="" (
    echo 正在激活Python虚拟环境...
    call .\.venv\Scripts\activate.bat
) else (
    echo 已在Python虚拟环境中
)

REM 启动系统
python run.py

pause