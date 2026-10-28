@echo off
REM ArayHumanNPCTest Launcher - Inicia o servico Python e o Project Zomboid
REM Usar este launcher permite que o mod funcione automaticamente sem PowerShell manual

setlocal enabledelayedexpansion

echo ========================================
echo ArayHumanNPCTest - Launcher
echo ========================================
echo.

REM Diretorio do mod (onde este .bat esta)
set "MOD_DIR=%~dp0"
set "AI_DIR=%MOD_DIR%ai"
set "SERVICE_SCRIPT=%AI_DIR%\ollama_service.py"
set "PID_FILE=%AI_DIR%\service.pid"
set "LOG_FILE=%AI_DIR%\service.log"

REM Diretorio de instalacao do jogo (ajustar se necessario)
set "GAME_DIR=E:\Games\Project.Zomboid.v42.13.1\game"
set "GAME_BAT=%GAME_DIR%\ProjectZomboid64.bat"

REM Verificar se o script Python existe
if not exist "%SERVICE_SCRIPT%" (
    echo ERRO: Servico Python nao encontrado em:
    echo %SERVICE_SCRIPT%
    echo.
    pause
    exit /b 1
)

REM Verificar se o launcher do jogo existe
if not exist "%GAME_BAT%" (
    echo AVISO: Launcher do jogo nao encontrado em:
    echo %GAME_BAT%
    echo.
    echo Ajuste a variavel GAME_DIR no topo deste .bat
    echo ou continue sem iniciar o jogo automaticamente.
    echo.
    set /p "CONTINUE=Continuar apenas com o servico Python? (S/N): "
    if /i not "!CONTINUE!"=="S" exit /b 1
    set "GAME_BAT="
)

REM Tentar encontrar Python
set "PYTHON_EXE="

REM Verificar python no PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :found_python
)

REM Verificar py launcher (Windows 10+)
where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    goto :found_python
)

REM Tentar localizacoes comuns
set "COMMON_PATHS=C:\Python3 C:\Python312 C:\Python311 C:\Python310 %LOCALAPPDATA%\Programs\Python\Python312 %LOCALAPPDATA%\Programs\Python\Python311"
for %%p in (%COMMON_PATHS%) do (
    if exist "%%p\python.exe" (
        set "PYTHON_EXE=%%p\python.exe"
        goto :found_python
    )
)

echo ERRO: Python nao encontrado.
echo.
echo Instale Python 3.10+ de python.org
echo ou adicione Python ao PATH do Windows.
echo.
pause
exit /b 1

:found_python
echo [OK] Python encontrado: %PYTHON_EXE%

REM Verificar se ja existe uma instancia rodando
if exist "%PID_FILE%" (
    echo.
    echo AVISO: Arquivo PID encontrado. O servico pode ja estar rodando.
    echo Se o jogo foi fechado incorretamente, delete: %PID_FILE%
    echo.
    set /p "KILL_OLD=Tentar encerrar servico antigo? (S/N): "
    if /i "!KILL_OLD!"=="S" (
        for /f "tokens=*" %%p in ('type "%PID_FILE%"') do (
            taskkill /PID %%p /F >nul 2>&1
        )
        del "%PID_FILE%" >nul 2>&1
        echo Servico antigo encerrado.
        timeout /t 2 >nul
    )
)

REM Iniciar servico Python em segundo plano
echo.
echo Iniciando servico Python...
echo Log: %LOG_FILE%
echo.

start /B "" "%PYTHON_EXE%" "%SERVICE_SCRIPT%" > "%LOG_FILE%" 2>&1

REM Aguardar 2 segundos para o servico iniciar
timeout /t 2 >nul

REM Verificar se o processo foi iniciado
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I "python.exe" >NUL
if %errorlevel% equ 0 (
    echo [OK] Servico Python iniciado com sucesso.
) else (
    echo [AVISO] Nao foi possivel confirmar inicializacao do servico.
    echo Verifique o log em: %LOG_FILE%
)

REM Iniciar o jogo se encontrado
if defined GAME_BAT (
    echo.
    echo Iniciando Project Zomboid...
    echo Diretorio: %GAME_DIR%
    echo.
    
    REM Mudar para o diretorio do jogo e executar o BAT original
    pushd "%GAME_DIR%"
    call "%GAME_BAT%"
    popd
    
    REM O jogo fechou, encerrar servico Python
    echo.
    echo Jogo fechado. Encerrando servico Python...
    
    if exist "%PID_FILE%" (
        for /f "tokens=*" %%p in ('type "%PID_FILE%"') do (
            taskkill /PID %%p /F >nul 2>&1
        )
        del "%PID_FILE%" >nul 2>&1
        echo [OK] Servico Python encerrado.
    ) else (
        REM PID nao encontrado, tentar matar todos os python.exe rodando ollama_service.py
        echo [AVISO] PID file nao encontrado. Tentando encerrar via nome...
        wmic process where "CommandLine like '%%ollama_service.py%%'" delete >nul 2>&1
    )
) else (
    echo.
    echo Servico Python esta rodando em segundo plano.
    echo Para encerra-lo manualmente, delete: %PID_FILE%
    echo e finalize o processo Python.
    echo.
    pause
)

echo.
echo Launcher finalizado.
timeout /t 3
exit /b 0
