call .\venv\Scripts\activate

powershell -command "exit [DateTime]::Today.ToString('yyyyMMdd')"
set VERSION_DATE=%ERRORLEVEL%
echo VERSION_DATE = %VERSION_DATE% > _version.py

pyinstaller HoshinoNe.spec

rename dist\HoshinoNe.exe HoshinoNe_%VERSION_DATE%.exe

pip-licenses --with-license-file --no-license-path --output-file=THIRD-PARTY-LICENSES

copy config.py            dist\
copy requirements.txt     dist\
copy THIRD-PARTY-LICENSES dist\
copy LICENSE              dist\
copy README.md            dist\

pause
