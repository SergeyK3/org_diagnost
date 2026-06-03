# Запуск orgdiag из корня проекта
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
& $python -m orgdiag @args
