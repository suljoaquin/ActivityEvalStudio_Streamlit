$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PYTHONPATH = $root
$py = "C:\Users\fromp\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
    $py = "python"
}
Write-Host "Activity Eval Studio -> http://127.0.0.1:5051"
& $py "$root\app.py"
