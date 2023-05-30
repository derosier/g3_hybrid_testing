
EVLKST8500GH FIRMWARE UPGRADE TOOL


*********************************************************************************************************************
IMPORTANT NOTE: it is MANDATORY to install STM32 Cube Programmer to upgrade the NUCLEO-G070RB board (from www.st.com)
*********************************************************************************************************************

The firmware upgrade tool is provided in the \EVLKST8500GH_FW_upgrade folder.
The structure of this folder is the following:
•	\imgs folder with image files of PE and RTE protocol firmware and ST8500_SPI_Loader.img for flash programming
•	image_loader_st8500.exe executable file for ST8500 programming
•	ST8500_get_protocol.bat script that gets the protocol/version of the FW running on the ST8500
•	ST8500_<protocol>_PE_RTE_upload.bat script that executes the full procedure for firmware download/upgrade
•	NUCLEO-programmer_Coordinator_868.bat for programming the NUCLEO-G070RB as G3-PLC PAN Coordinator (RF type 868)
•	NUCLEO-programmer_Coordinator_915.bat for programming the NUCLEO-G070RB as G3-PLC PAN Coordinator (RF type 915)
•	NUCLEO-programmer_Device_868.bat for programming the NUCLEO-G070RB as G3-PLC PAN Device (RF type 868)
•	NUCLEO-programmer_Device_915.bat for programming the NUCLEO-G070RB as G3-PLC PAN Device (RF type 915)


STM32 PROGRAMMING
After installing the STM32 Cube Programmer, connect the USB cable to the NUCLEO-G070RB USB connector and launch the Coordinator or Device .bat file.
There is a version for the 868 RF module and a version for the 915 RF module for both Coordinator and Device. 
Please select the proper image depending on the RF module you are using.
Please connect only one EVLKST8500GH at a time

ST8500 PROGRAMMING
The correlated COM port can be found into Windows Device Manager tool (standard COM port) and is requested at the begin 
of ST8500_<protocol>_PE_RTE_upload.bat execution. The target image file names, if different from the default, must be modified in this file.

NOTE: Before proceeding with the FW download, the position of STM32 MODE and PLC BOOT1 switches must be set according 
to indications shown into ST8500_<protocol>_PE_RTE_upload.bat to operate on ST8500 with boot from ST8500 SPI flash: 
please ensure that STM32 MODE switch position is "1" (DOWN) and PLC BOOT1 is "1" (DOWN).

The major content of ST8500_<protocol>_PE_RTE_upload.bat is shown below.
•	set DEFAULT_COMM=COM9
Set the default COM port (COM9 in this example)

•	set PE_image_dl="imgs\<PE_image>.img"
•	set RTE_image_dl="imgs\<RTE_image>.img"
Sets the relative paths of the PE and RTE images for the ST8500 to program

With these instruction, if the COM port number is not indicated, the executable file will prompt the user for it

•	.\image_loader_st8500.exe --port %DEFAULT_COMM% --baudrate 460800 --program_SPI_Flash --pe %PE_image_dl% --rte %RTE_image_dl%
Write FW images into ST8500 SPI flash with the selected baudrate

The image files <PE_image>.img, <RTE_image>.img are provided in the package. 
Please note that the actual file names shall be different with different release versions. 
Please refer to the README.txt in each release package.
