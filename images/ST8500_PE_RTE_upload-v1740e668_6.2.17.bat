@echo off
::Sets localization of variables.
setlocal enableExtensions disableDelayedExpansion

::Sets the default COM port
set DEFAULT_COMM=%1

::Sets the default images and gets arguments
set PE_image_dl="imgs\ST8500_G3_v1740e668_6.2.17.img"
set RTE_image_dl="imgs\STARCOM_G3_RT_FW_r1_15_rc2_BA_key0.img"

echo PE Image  : %PE_image_dl%
echo RTE image : %RTE_image_dl%
echo.
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

.\image_loader_st8500.exe --port %DEFAULT_COMM% --baudrate 115200 --program_SPI_Flash --pe %PE_image_dl% --rte %RTE_image_dl%

echo.
pause

