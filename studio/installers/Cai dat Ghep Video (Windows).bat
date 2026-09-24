<# : batch part (cmd runs these lines; PowerShell treats them as a comment)
@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%~f0'; Invoke-Expression ([IO.File]::ReadAllText($f, [Text.Encoding]::UTF8))"
if errorlevel 1 pause
exit /b
#>
# Cài Ghép Video bằng 1 lần bấm (Windows 10/11 64-bit).
# Tải bản mới nhất từ GitHub -> kiểm tra SHA-256 -> đặt vào %USERPROFILE%\Ghép Video -> cài mọi thứ -> tạo biểu tượng -> mở app.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Manifest = if ($env:GHEPVIDEO_MANIFEST) { $env:GHEPVIDEO_MANIFEST } else { 'https://github.com/nguyenlanh282/ghep-video/releases/latest/download/latest.json' }
$Dest = if ($env:GHEPVIDEO_DIR) { $env:GHEPVIDEO_DIR } else { Join-Path $env:USERPROFILE 'Ghép Video' }
function Fail($t) { Write-Host "`nLOI: $t" -ForegroundColor Red; Write-Host 'Chup man hinh cua so nay gui nguoi ho tro.'; exit 1 }

Write-Host '== Cài đặt Ghép Video ==' -ForegroundColor Green
try { $m = Invoke-RestMethod -UseBasicParsing -Uri $Manifest } catch { Fail 'Không kết nối được máy chủ cập nhật. Kiểm tra mạng rồi chạy lại.' }
$url = if ($m.url -match '^https?://') { $m.url } else { ($Manifest -replace '[^/]+$', '') + $m.url }

Write-Host "Đang tải Ghép Video $($m.version)…"
$zip = Join-Path $env:TEMP "GhepVideo-$($m.version).zip"
try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip } catch { Fail 'Tải gói cài đặt chưa được.' }
if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $m.sha256.ToLower()) { Remove-Item $zip; Fail 'Gói tải về bị lỗi (sai mã SHA-256). Hãy chạy lại.' }

Write-Host "Đang đặt app vào: $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
# Only app files are in the zip: an existing install keeps its media, output and settings.
Expand-Archive -Force $zip $Dest
Remove-Item $zip
Get-ChildItem -Recurse $Dest | Unblock-File -ErrorAction SilentlyContinue

& (Join-Path $Dest 'studio\setup-windows.ps1')
