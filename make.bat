call .\venv\Scripts\activate

powershell -command "exit [DateTime]::Today.ToString('yyyyMMdd')"
set VERSION_DATE=%ERRORLEVEL%
echo VERSION_DATE = %VERSION_DATE% > _version.py

pyinstaller --onefile --windowed HoshinoNe.py

rename dist\HoshinoNe.exe HoshinoNe_%VERSION_DATE%.exe

copy config.py        dist\
copy LICENSE          dist\
copy NOTICE.txt       dist\
copy requirements.txt dist\
copy README.md        dist\

pause
