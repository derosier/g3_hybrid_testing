@echo off
::Sets localization of variables.
setlocal enableExtensions disableDelayedExpansion

::Sets the default COM port
set DEFAULT_COMM=%1

echo ################################################################
echo Before proceeding with FW upload, please ensure that STM32 MODE  
echo switch position is "1" (DOWN) and PLC BOOT1 is "1" (DOWN)
echo ################################################################
echo.
echo ###############################
echo Press RESET on EVALKITST8500-1
echo ###############################
echo.
pause
echo.

.\image_loader_st8500.exe --port %DEFAULT_COMM% --get_protocol

echo.
pause

