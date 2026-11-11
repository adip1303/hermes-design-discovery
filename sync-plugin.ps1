param(
  # The workspace sandbox redirects LOCALAPPDATA; use the user's real local profile by default.
  [string]$HermesHome = (Join-Path $env:USERPROFILE 'AppData\Local\hermes')
)

$pluginId = 'design-discovery'
$repo = $PSScriptRoot
$pluginTarget = Join-Path $HermesHome "plugins\$pluginId"
$desktopTarget = Join-Path $HermesHome "desktop-plugins\$pluginId"
$python = Get-ChildItem -LiteralPath (Join-Path $HermesHome 'tools') -Filter 'python.exe' -Recurse -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
$node = Get-ChildItem -LiteralPath (Join-Path $HermesHome 'tools') -Filter 'node.exe' -Recurse -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if (-not $python -or -not $node) {
  throw 'Hermes runtime not found; refusing to sync without running plugin checks.'
}

& $node.FullName (Join-Path $repo 'scripts\check_desktop_plugin.mjs') (Join-Path $repo 'desktop\plugin.js')
if ($LASTEXITCODE -ne 0) {
  throw 'Desktop plugin runtime check failed; refusing to sync the plugin.'
}

& $python.FullName (Join-Path $repo 'tests\smoke_tools.py')
if ($LASTEXITCODE -ne 0) {
  throw 'Tool smoke test failed; refusing to sync the plugin.'
}

New-Item -ItemType Directory -Force -Path $pluginTarget, $desktopTarget | Out-Null
Get-ChildItem -LiteralPath $pluginTarget -Directory -Recurse -Filter '__pycache__' -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $repo -Force | Where-Object { $_.Name -ne '.git' } | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $pluginTarget -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $repo 'desktop\plugin.js') -Destination (Join-Path $desktopTarget 'plugin.js') -Force
$gitSha = (git -C $repo rev-parse --short HEAD).Trim()
$dirty = [bool](git -C $repo status --porcelain)
$stamp = @{ git_sha = $gitSha; built_at = (Get-Date).ToUniversalTime().ToString('o'); dirty = $dirty } | ConvertTo-Json -Compress
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText((Join-Path $pluginTarget '.build-stamp.json'), $stamp, $utf8NoBom)
hermes plugins enable $pluginId
Write-Host 'Python changes need a full Desktop restart: quit from Task Manager, reopen, start a new chat. Pane-only changes hot-reload.'
