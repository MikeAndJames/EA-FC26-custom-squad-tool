@echo off
setlocal EnableDelayedExpansion
title FC 26 Moneyball Squad Deployer

rem ============================================================
rem  deploy_squads.bat
rem  Manages ONLY squad-data files:  Squads*  MatchDay*  SquadOnline*
rem  (never touches other EA settings/saves).
rem  Backups live on E: next to this script:
rem    backup\        original Squads* (taken on first ever run)
rem    backup\cache\  original MatchDay*/SquadOnline* (taken on first
rem                   cache deploy)
rem  Patched files come from:
rem    output\settings_patched\ patched squad SAVES from patch_squads.py
rem                             (the zero-touch route -- main path)
rem    output\                  optional loadable moneyball Squads files
rem                             (swap_players.py; needs in-game Load+Save)
rem  Caches (MatchDay/SquadOnline) are backed up + restored but NEVER
rem  deployed patched -- online modes read them (see CLAUDE.md hard rules).
rem ============================================================

set "SETTINGS=C:\Users\james\AppData\Local\EA SPORTS FC 26\settings"
set "OUTPUT=%~dp0output"
set "PATCHED=%~dp0output\settings_patched"
set "BACKUP=%~dp0backup"

if not exist "%SETTINGS%" (
    echo  ERROR: EA settings folder not found:
    echo    %SETTINGS%
    echo  Has FC 26 been run at least once on this machine?
    pause
    exit /b 1
)

rem ---------- first run: back up original Squads* automatically ----------
if exist "%BACKUP%\backup_done.txt" goto :cachebackup
echo(
echo  No backup found -- backing up original EA squad files now...
mkdir "%BACKUP%" 2>nul
copy /y "%SETTINGS%\Squads*" "%BACKUP%\" >nul 2>&1
echo Backup taken %date% %time% of %SETTINGS%\Squads* > "%BACKUP%\backup_done.txt"
echo  Backed up the following original files to %BACKUP%:
dir /b "%BACKUP%\Squads*" 2>nul
if errorlevel 1 echo    (settings folder had no Squads* files -- empty backup is OK)
echo(
echo  Backup complete.
pause

rem ---------- every run: back up any never-seen game-created files ----------
rem The game creates caches (MatchDay/SquadOnline) and in-game squad saves
rem (Squads<timestamp>) with fresh names. Any name we have not backed up yet
rem and did not build ourselves is a pristine game file -- snapshot it before
rem we ever touch the folder. Names already in a backup are skipped, so
rem patched files we deploy can never overwrite an original.
:cachebackup
if not exist "%BACKUP%\cache" mkdir "%BACKUP%\cache"
set "NEWBK="
for %%P in (MatchDay SquadOnline) do (
    for /f "delims=" %%F in ('dir /b "%SETTINGS%\%%P*" 2^>nul') do (
        if not exist "%BACKUP%\cache\%%F" (
            copy /y "%SETTINGS%\%%F" "%BACKUP%\cache\" >nul
            echo  Backed up new cache file: %%F
            set "NEWBK=1"
        )
    )
)
rem game-created squad saves (skip files that exist in output\ -- those are ours)
for /f "delims=" %%F in ('dir /b "%SETTINGS%\Squads*" 2^>nul') do (
    if not exist "%OUTPUT%\%%F" if not exist "%BACKUP%\%%F" (
        copy /y "%SETTINGS%\%%F" "%BACKUP%\" >nul
        echo  Backed up new in-game squad save: %%F
        set "NEWBK=1"
    )
)
if defined NEWBK (
    echo(
    pause
)

:menu
cls
echo  ==========================================
echo   FC 26 MONEYBALL SQUAD DEPLOYER
echo  ==========================================
echo(
echo  --- CURRENT STATUS ------------------------------------------
echo(
echo  [GAME]  Squad files the game sees now  (C: settings folder):
dir /o-d "%SETTINGS%\Squads*" 2>nul | findstr /i "Squads"
if errorlevel 1 echo          (none)
dir /o-d "%SETTINGS%\MatchDay*" "%SETTINGS%\SquadOnline*" 2>nul | findstr /i "MatchDay SquadOnline"
if errorlevel 1 echo          (no MatchDay / SquadOnline caches)
echo(
echo  [SAFE]  Originals backed up here on E:
type "%BACKUP%\backup_done.txt" 2>nul
dir /o-d "%BACKUP%\Squads*" 2>nul | findstr /i "Squads"
if errorlevel 1 echo          (backup is empty)
dir /o-d "%BACKUP%\cache\*" 2>nul | findstr /i "MatchDay SquadOnline"
if errorlevel 1 echo          (no MatchDay/SquadOnline caches backed up yet)
echo(
echo  [MODS]  Patched files built here on E:  (newest first):
dir /o-d "%PATCHED%\Squads*" 2>nul | findstr /i "Squads"
if errorlevel 1 echo          (no patched saves -- run patch_squads.py first)
echo(
echo  --------------------------------------------------------------
echo(
echo   1. Deploy currently patched files     [E: output -> C: settings]
echo   2. Pick ^& Patch a squad PRESET        [e.g. Liverpool, Big Guys]
echo   3. Restore original EA squad files     [undo everything]
echo   4. Quit
echo(
set "CHOICE="
set /p CHOICE="  Pick 1, 2, 3 or 4: "
if "!CHOICE:~0,1!"=="1" goto :deploy
if "!CHOICE:~0,1!"=="2" goto :preset_menu
if "!CHOICE:~0,1!"=="3" goto :restore
if "!CHOICE:~0,1!"=="4" exit /b 0
goto :menu

rem ============================================================
:preset_menu
set "PRESET_DIR=%OUTPUT%\presets"
if not exist "%PRESET_DIR%" mkdir "%PRESET_DIR%" 2>nul

cls
echo  ==========================================
echo   SELECT A SQUAD PRESET TO PATCH ^& DEPLOY
echo  ==========================================
echo(

set count=0
for /f "delims=" %%F in ('dir /b "%PRESET_DIR%\*.json" 2^>nul') do (
    set /a count+=1
    set "preset[!count!]=%%F"
    echo   !count!. %%~nF
)

if %count%==0 (
    echo  No saved presets found in %PRESET_DIR%.
    echo  Build a squad and click 'Save Preset' in app.py first!
    echo(
    pause
    goto :menu
)

echo(
set "PCHOICE="
set /p PCHOICE="  Select preset number (1-%count%) or press Enter to cancel: "
if not defined PCHOICE goto :menu

for /f "delims=0123456789" %%i in ("%PCHOICE%") do goto :preset_invalid

if %PCHOICE% LSS 1 goto :preset_invalid
if %PCHOICE% GTR %count% goto :preset_invalid

set "CHOSEN_PRESET=!preset[%PCHOICE%]!"
echo(
echo  Selected Preset: %CHOSEN_PRESET%
echo  Patching squad files with: python patch_squads.py --preset "%PRESET_DIR%\%CHOSEN_PRESET%"
echo(

python "%~dp0patch_squads.py" --preset "%PRESET_DIR%\%CHOSEN_PRESET%"
if errorlevel 1 (
    echo(
    echo  ERROR: patch_squads.py failed for %CHOSEN_PRESET%.
    pause
    goto :menu
)

echo(
echo  Patch complete! Proceeding to deploy...
goto :deploy_confirmed

:preset_invalid
echo  Invalid selection.
pause
goto :preset_menu

rem ============================================================
:deploy
rem The main route is ZERO-TOUCH: patch_squads.py patches the game's own
rem squad saves in place (output\settings_patched\Squads*); we copy them
rem back over the originals. Kick Off reads the active save directly --
rem no in-game menu steps needed.
set "HAVEPATCHED="
for /f "delims=" %%F in ('dir /b "%PATCHED%\Squads*" 2^>nul') do set "HAVEPATCHED=1"

rem optional extra: a loadable moneyball file in output\ (GUID=0 -- only
rem works via in-game Load Squads + Save Squads; kept as the fallback route)
set "NEWEST="
for /f "delims=" %%F in ('dir /b /o-d "%OUTPUT%\Squads*" 2^>nul') do (
    if not defined NEWEST set "NEWEST=%%F"
)

if not defined HAVEPATCHED if not defined NEWEST (
    echo(
    echo  ERROR: nothing to deploy.
    echo  Run:  python patch_squads.py --swap PLAYER,FROM,TO,JERSEY
    pause
    goto :menu
)

rem SAFETY: never deploy caches. Online modes (Seasons) and 'live form'
rem read MatchDay*/SquadOnline* -- patched caches put modded players into
rem online play (discovered 2026-07-15, nearly played Messi in Seasons).
set "BADCACHE="
for /f "delims=" %%F in ('dir /b "%PATCHED%\MatchDay*" "%PATCHED%\SquadOnline*" 2^>nul') do set "BADCACHE=%%F"
if defined BADCACHE (
    echo(
    echo  WARNING: "!BADCACHE!" found in settings_patched. Caches are NEVER
    echo  deployed - online modes read them [ban risk]. Skipping all caches.
    echo  Delete them and re-run patch_squads.py WITHOUT --include-caches.
    echo(
)

echo(
set "CONFIRM="
set /p CONFIRM="  Deploy patched squad saves into the EA settings folder? (y/n): "
if /i not "!CONFIRM:~0,1!"=="y" (
    echo  Nothing copied.
    pause
    goto :menu
)

:deploy_confirmed
if defined HAVEPATCHED (
    for /f "delims=" %%F in ('dir /b "%PATCHED%\Squads*" 2^>nul') do (
        copy /y "%PATCHED%\%%F" "%SETTINGS%\" >nul
        if errorlevel 1 (
            echo  ERROR: copy of %%F failed. Is the game running? Close it and retry.
            pause
            goto :menu
        )
        echo  Deployed patched save: %%F
    )
)
if defined NEWEST (
    copy /y "%OUTPUT%\%NEWEST%" "%SETTINGS%\" >nul
    echo  Deployed loadable file: %NEWEST%
)

echo(
echo  ##########################################################
echo  #                                                        #
echo  #   NOW GO OFFLINE !!!                                   #
echo  #   Turn off Wi-Fi / unplug ethernet BEFORE launching    #
echo  #   FC 26. Modified squads are for OFFLINE play only.    #
echo  #                                                        #
echo  ##########################################################
echo(
echo  Then just launch the game and go STRAIGHT TO KICK OFF.
echo  (Zero-touch: the active squad save already has the edits.)
echo(
echo  Fallback if a player is missing: Settings cog -- Customize --
echo  Profile -- Load Squads (pick our file) -- Save Squads -- Kick Off.
echo(
echo  BEFORE GOING BACK ONLINE: run this script, option 2 (restore),
echo  then check with:  python audit_squads.py
echo(
pause
goto :menu

rem ============================================================
:restore
echo(
echo  This will DELETE the Squads*/MatchDay*/SquadOnline* files currently
echo  in the EA settings folder (including anything we deployed) and put
echo  back the originals from the backups.
echo(
set "CONFIRM="
set /p CONFIRM="  Restore original EA squad files? (y/n): "
if /i not "!CONFIRM:~0,1!"=="y" (
    echo  Nothing restored.
    pause
    goto :menu
)

del /q "%SETTINGS%\Squads*" 2>nul
copy /y "%BACKUP%\Squads*" "%SETTINGS%\" >nul 2>&1
if exist "%BACKUP%\cache" (
    del /q "%SETTINGS%\MatchDay*" 2>nul
    del /q "%SETTINGS%\SquadOnline*" 2>nul
    copy /y "%BACKUP%\cache\*" "%SETTINGS%\" >nul 2>&1
)
echo(
echo  Restored. Squad files now in the EA settings folder:
dir /o-d "%SETTINGS%\Squads*" "%SETTINGS%\MatchDay*" "%SETTINGS%\SquadOnline*" 2>nul | findstr /i "Squads MatchDay SquadOnline"
if errorlevel 1 echo    (none -- the backup was empty, which matches first-run state)
echo(
pause
goto :menu
