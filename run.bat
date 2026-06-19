@echo off
title Instant Translator
echo Instant Translator — запуск без консоли
echo Выход: Ctrl+Shift+Q
start /b /min pythonw.exe "%~dp0instant_translator.py"
exit
