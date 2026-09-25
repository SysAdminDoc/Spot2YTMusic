$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$dist = Join-Path $root 'dist'
$build = Join-Path $root 'build'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install .[gui,dev] first.' }
# Keep DLLs from unrelated applications out of the distributable.
$pythonDir = Split-Path $python -Parent
$basePythonDir = & $python -c 'import sys; print(sys.base_prefix)'
$env:PATH = @($pythonDir, $basePythonDir, "$env:SystemRoot\System32", $env:SystemRoot) -join ';'
foreach ($target in @($dist, $build)) {
    $full = [System.IO.Path]::GetFullPath($target)
    if (-not $full.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Build path escaped the repository: $full"
    }
    if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
}
$iconIco = Join-Path $root 'assets\app-icon.ico'
$artwork = Join-Path $root 'src\spot2ytmusic\assets\track-placeholder.png'
& $python -m PyInstaller --clean --noconfirm --onefile --windowed --name Spot2YTMusic --icon $iconIco --add-data "$artwork;spot2ytmusic/assets" --collect-data ytmusicapi --runtime-hook (Join-Path $root 'scripts\runtime_hook_mp.py') (Join-Path $root 'scripts\gui_launcher.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
$env:QT_QPA_PLATFORM = 'offscreen'
$smoke = Start-Process -FilePath (Join-Path $dist 'Spot2YTMusic.exe') -ArgumentList '--smoke-test' -PassThru -WindowStyle Hidden
if (-not $smoke.WaitForExit(30000)) {
    & taskkill.exe /T /F /PID $smoke.Id | Out-Null
    throw 'Frozen app startup check timed out.'
}
if ($smoke.ExitCode -ne 0) { throw "Frozen app startup check failed: $($smoke.ExitCode)" }
Remove-Item Env:QT_QPA_PLATFORM
& $python -m build
if ($LASTEXITCODE -ne 0) { throw 'Package build failed.' }
$version = (& $python -c 'from spot2ytmusic import __version__; print(__version__)').Trim()
$archive = Join-Path $dist "Spot2YTMusic-v$version-windows.zip"
Compress-Archive -LiteralPath @((Join-Path $dist 'Spot2YTMusic.exe'), (Join-Path $root 'LICENSE'), (Join-Path $root 'THIRD_PARTY_NOTICES.md'), (Join-Path $root 'LICENSES')) -DestinationPath $archive
$assets = @((Join-Path $dist 'Spot2YTMusic.exe'), $archive, (Join-Path $dist "spot2ytmusic-$version-py3-none-any.whl"), (Join-Path $dist "spot2ytmusic-$version.tar.gz"))
$checksums = foreach ($asset in $assets) {
    $hash = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $(Split-Path $asset -Leaf)"
}
Set-Content -LiteralPath (Join-Path $dist 'SHA256SUMS.txt') -Value $checksums -Encoding ascii
Write-Output (Join-Path $dist 'Spot2YTMusic.exe')
