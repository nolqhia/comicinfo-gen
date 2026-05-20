@echo off
chcp 65001 >nul
python "%~dp0comicinfo_gen.py" "%~1"
