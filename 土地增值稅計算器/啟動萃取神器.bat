@echo off
chcp 65001 >nul
echo =========================================
echo         正在啟動資料自動萃取神器...
echo =========================================
echo.
echo 請稍候，正在為您開啟瀏覽器畫面...
echo (如果瀏覽器沒有自動跳出，請注意畫面上的網址)
echo.

cd /d "%~dp0"
python -m streamlit run app.py

pause
