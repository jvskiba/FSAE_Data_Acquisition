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
copy /Y "src\layout.json" "..\Distribution\JvS_Data_Acquisition\"

pause