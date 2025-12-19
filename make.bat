call .\venv\Scripts\activate

powershell -command "exit [DateTime]::Today.ToString('yyyyMMdd')"
set VERSION_DATE=%ERRORLEVEL%
echo VERSION_DATE = %VERSION_DATE% > version.py

pyinstaller --onefile --windowed FlowEditor.py

rename dist\FlowEditor.exe FlowEditor_%VERSION_DATE%.exe

copy LICENSE          dist\
copy NOTICE.txt       dist\
copy requirements.txt dist\
copy README.md        dist\

pause
