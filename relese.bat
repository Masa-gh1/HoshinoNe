powershell -command "exit [DateTime]::Today.ToString('yyyyMMdd')"
set VERSION_DATE=%ERRORLEVEL%


echo venv            > EXCLUDE.lst
echo __pycache__    >> EXCLUDE.lst
echo .vscode        >> EXCLUDE.lst
echo .amazonq       >> EXCLUDE.lst
echo debug          >> EXCLUDE.lst
echo build          >> EXCLUDE.lst
echo dist           >> EXCLUDE.lst
echo HoshinoNe.spec >> EXCLUDE.lst
echo .CR2           >> EXCLUDE.lst
echo sample         >> EXCLUDE.lst
echo Thumbs.db      >> EXCLUDE.lst
xcopy /E /S /EXCLUDE:EXCLUDE.lst .             ..\HoshinoNe_%VERSION_DATE%_src
xcopy /E /S                      .\dist        ..\HoshinoNe_%VERSION_DATE%
xcopy /E /S                      .\subFlow     ..\HoshinoNe_%VERSION_DATE%\subFlow
xcopy /E /S                      .\sample\raw  ..\HoshinoNe_%VERSION_DATE%_sample_raw
xcopy /E /S                      .\sample\fits ..\HoshinoNe_%VERSION_DATE%_sample_ftis

del EXCLUDE.lst
pause
