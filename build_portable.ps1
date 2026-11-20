param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = "C:\Users\fromp\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }

if (-not $SkipBuild) {
    & $py -m PyInstaller --noconfirm --clean ActivityEvalStudio.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
}

$dist = Join-Path $root "dist\ActivityEvalStudio"
if (-not (Test-Path -LiteralPath (Join-Path $dist "ActivityEvalStudio.exe"))) {
    throw "Build output not found: $dist"
}
Copy-Item -LiteralPath (Join-Path $root "README_FIRST.txt") -Destination $dist -Force
Copy-Item -LiteralPath (Join-Path $root "SAMPLE_AUDIT.md") -Destination $dist -Force

$zip = Join-Path $root "dist\ActivityEvalStudio_Windows.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $dist "*") -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Built: $zip"
