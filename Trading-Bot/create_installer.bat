@echo off
echo Creating Trading Bot Installer...

REM Check if the build exists
if not exist "dist\TradingBot" (
    echo Error: Build directory not found. Please run build_desktop_app.bat first.
    exit /b 1
)

REM Install NSIS if it's not already installed
where makensis >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo NSIS not found. Attempting to install via Chocolatey...
    where choco >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo Chocolatey not found. Please install NSIS manually from https://nsis.sourceforge.io/Download
        echo After installing, add the NSIS directory to your PATH environment variable.
        exit /b 1
    ) else (
        echo Installing NSIS via Chocolatey...
        choco install nsis -y
    )
)

REM Create NSIS installer script
echo Creating installer script...
echo !define APP_NAME "MT5 Trading Bot" > installer.nsi
echo !define COMP_NAME "TradingBot" >> installer.nsi
echo !define VERSION "1.0.0" >> installer.nsi
echo !define COPYRIGHT "Copyright (c) 2023" >> installer.nsi
echo !define DESCRIPTION "MT5 Multi-Instance Trading Bot" >> installer.nsi
echo !define LICENSE_TXT "LICENSE.txt" >> installer.nsi
echo !define INSTALLER_NAME "TradingBot_Setup.exe" >> installer.nsi
echo !define MAIN_APP_EXE "TradingBot.exe" >> installer.nsi
echo !define INSTALL_TYPE "SetShellVarContext current" >> installer.nsi
echo !define REG_ROOT "HKCU" >> installer.nsi
echo !define REG_APP_PATH "Software\Microsoft\Windows\CurrentVersion\App Paths\${MAIN_APP_EXE}" >> installer.nsi
echo !define UNINSTALL_PATH "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" >> installer.nsi
echo !define REG_START_MENU "Start Menu Folder" >> installer.nsi
echo >> installer.nsi
echo !include "MUI2.nsh" >> installer.nsi
echo >> installer.nsi
echo Name "${APP_NAME}" >> installer.nsi
echo Caption "${APP_NAME}" >> installer.nsi
echo OutFile "${INSTALLER_NAME}" >> installer.nsi
echo BrandingText "${APP_NAME}" >> installer.nsi
echo XPStyle on >> installer.nsi
echo InstallDirRegKey "${REG_ROOT}" "${REG_APP_PATH}" "" >> installer.nsi
echo InstallDir "$PROGRAMFILES64\${APP_NAME}" >> installer.nsi
echo >> installer.nsi
echo !define MUI_ABORTWARNING >> installer.nsi
echo !define MUI_UNABORTWARNING >> installer.nsi
echo !define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP_NAME} Setup" >> installer.nsi
echo !define MUI_WELCOMEPAGE_TEXT "This will install ${APP_NAME} on your computer.$\r$\n$\r$\nIt is recommended that you close all other applications before starting Setup." >> installer.nsi
echo !define MUI_ICON "static\favicon.ico" >> installer.nsi
echo !define MUI_UNICON "static\favicon.ico" >> installer.nsi
echo >> installer.nsi
echo !insertmacro MUI_PAGE_WELCOME >> installer.nsi
echo !insertmacro MUI_PAGE_DIRECTORY >> installer.nsi
echo !insertmacro MUI_PAGE_INSTFILES >> installer.nsi
echo !insertmacro MUI_PAGE_FINISH >> installer.nsi
echo >> installer.nsi
echo !insertmacro MUI_UNPAGE_CONFIRM >> installer.nsi
echo !insertmacro MUI_UNPAGE_INSTFILES >> installer.nsi
echo >> installer.nsi
echo !insertmacro MUI_LANGUAGE "English" >> installer.nsi
echo >> installer.nsi
echo Section -MainProgram >> installer.nsi
echo ${INSTALL_TYPE} >> installer.nsi
echo SetOverwrite ifnewer >> installer.nsi
echo SetOutPath "$INSTDIR" >> installer.nsi
echo File /r "dist\TradingBot\*.*" >> installer.nsi
echo SectionEnd >> installer.nsi
echo >> installer.nsi
echo Section -Icons_Reg >> installer.nsi
echo SetOutPath "$INSTDIR" >> installer.nsi
echo CreateDirectory "$SMPROGRAMS\${APP_NAME}" >> installer.nsi
echo CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${MAIN_APP_EXE}" >> installer.nsi
echo CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${MAIN_APP_EXE}" >> installer.nsi
echo CreateShortCut "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe" >> installer.nsi
echo WriteRegStr ${REG_ROOT} "${REG_APP_PATH}" "" "$INSTDIR\${MAIN_APP_EXE}" >> installer.nsi
echo WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}" "DisplayName" "${APP_NAME}" >> installer.nsi
echo WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}" "UninstallString" "$INSTDIR\uninstall.exe" >> installer.nsi
echo WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}" "DisplayIcon" "$INSTDIR\${MAIN_APP_EXE}" >> installer.nsi
echo WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}" "DisplayVersion" "${VERSION}" >> installer.nsi
echo WriteRegStr ${REG_ROOT} "${UNINSTALL_PATH}" "Publisher" "${COMP_NAME}" >> installer.nsi
echo SectionEnd >> installer.nsi
echo >> installer.nsi
echo Section Uninstall >> installer.nsi
echo ${INSTALL_TYPE} >> installer.nsi
echo Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" >> installer.nsi
echo Delete "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" >> installer.nsi
echo Delete "$DESKTOP\${APP_NAME}.lnk" >> installer.nsi
echo RMDir "$SMPROGRAMS\${APP_NAME}" >> installer.nsi
echo RMDir /r "$INSTDIR" >> installer.nsi
echo DeleteRegKey ${REG_ROOT} "${REG_APP_PATH}" >> installer.nsi
echo DeleteRegKey ${REG_ROOT} "${UNINSTALL_PATH}" >> installer.nsi
echo SectionEnd >> installer.nsi

REM Create a blank license file if it doesn't exist
if not exist "LICENSE.txt" (
    echo MT5 Trading Bot License > LICENSE.txt
    echo ------------------------ >> LICENSE.txt
    echo This software is provided as-is, without warranty of any kind. >> LICENSE.txt
)

REM Build the installer
echo Building installer...
makensis installer.nsi

REM Check if installer was created successfully
if exist "TradingBot_Setup.exe" (
    echo Installer created successfully: TradingBot_Setup.exe
) else (
    echo Error: Failed to create installer.
    exit /b 1
)

echo Installer creation complete!
echo You can distribute TradingBot_Setup.exe to your users. 