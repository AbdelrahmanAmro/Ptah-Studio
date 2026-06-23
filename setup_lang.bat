@echo off
set PYBABEL="C:\Users\musli\AppData\Local\Programs\Python\Python313\Scripts\pybabel.exe"

:MENU
CLS
ECHO ===================================================
ECHO      PTAH STUDIOS TRANSLATION MANAGER
ECHO ===================================================
ECHO 1. UPDATE Translations (Run this after changing HTML)
ECHO 2. COMPILE Translations (Run this after writing Arabic)
ECHO 3. Exit
ECHO ===================================================
SET /P M=Type 1, 2, or 3 then press ENTER: 

IF %M%==1 GOTO UPDATE
IF %M%==2 GOTO COMPILE
IF %M%==3 GOTO EOF

:UPDATE
ECHO.
ECHO --- Extracting texts (Ignoring venv) ---
%PYBABEL% extract -F babel.cfg -k _ -o messages.pot . --ignore-dirs=venv

ECHO.
ECHO --- Updating Arabic File ---
if not exist "translations\ar" (
    %PYBABEL% init -i messages.pot -d translations -l ar
) else (
    %PYBABEL% update -i messages.pot -d translations
)
ECHO.
ECHO [DONE] Now open translations/ar/LC_MESSAGES/messages.po and translate!
PAUSE
GOTO MENU

:COMPILE
ECHO.
ECHO --- Compiling for Website ---
%PYBABEL% compile -d translations
ECHO.
ECHO [DONE] Restart your Flask app to see changes.
PAUSE
GOTO MENU

:EOF
EXIT