@echo off
::Sets localization of variables.
setlocal enableExtensions disableDelayedExpansion

::Sets the default COM port
set DEFAULT_COMM=%1

::Sets the default images and gets arguments
set PE_image_dl="imgs\ST8500_G3_v17a1a45a_6.3.4.img"
set RTE_image_dl="imgs\STARCOM_G3_RT_FW_r1_15_rc2_BA_key0.img"

echo PE Image  : %PE_image_dl%
echo RTE image : %RTE_image_dl%
echo.

mode %DEFAULT_COMM% BAUD=115200 PARITY=n DATA=8
echo g3_pass_through > %DEFAULT_COMM%
.\image_loader_st8500.exe --port %DEFAULT_COMM% --baudrate 115200 --program_SPI_Flash --pe %PE_image_dl% --rte %RTE_image_dl%

echo.
pause

