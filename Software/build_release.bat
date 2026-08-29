@echo off

cd /d "%~dp0"

pyinstaller ^
    --clean ^
    --noconfirm ^
    --onedir ^
    --distpath "..\Distribution" ^
    --workpath ".\build" ^
    --specpath ".\build" ^
    src\JvS_Data_Acquisition.py

copy /Y "src\config.json" "..\Distribution\JvS_Data_Acquisition\"
mkdir "..\Distribution\JvS_Data_Acquisition\layouts\"
copy /Y "src\layouts\layout.json" "..\Distribution\JvS_Data_Acquisition\layouts\"
mkdir "..\Distribution\JvS_Data_Acquisition\vehicle_config\"
copy /Y "src\vehicle_config\config.json" "..\Distribution\JvS_Data_Acquisition\vehicle_config\"

pause