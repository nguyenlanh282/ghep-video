# Cài AI xem ảnh chạy ngay trên máy (Ollama + Qwen3-VL Instruct, ~5 GB) cho Ghép Video trên Windows.
# Không bắt buộc: có thể dùng gói Claude / ChatGPT qua Claude Code / Codex thay thế. Mở từ nút "Cài AI trên máy" trong app.
# Tự cài: Python 3.12 (qua uv), FFmpeg, Ollama, thư viện, mô hình AI; tạo biểu tượng Desktop; mở app.
# Chạy lại bao nhiêu lần cũng được. Tham số: -NoOpen (không mở app khi xong).
param([switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is many times faster without the progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here
$Data = Join-Path $env:APPDATA 'GhepVideo'
$Bin = Join-Path $Data 'bin'
$Venv = Join-Path $Data 'venv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Data 'python'
New-Item -ItemType Directory -Force -Path $Data, $Bin, (Join-Path $Data 'models') | Out-Null

function Step($t) { Write-Host "`n>> $t" -ForegroundColor Cyan }
function Fail($t) { Write-Host "`nLOI: $t" -ForegroundColor Red; Write-Host 'Chup man hinh cua so nay gui nguoi ho tro.'; exit 1 }
# curl.exe ships with Windows 10/11: fast, resumable and shows a progress bar; Invoke-WebRequest is the fallback.
$Curl = Join-Path $env:SystemRoot 'System32\curl.exe'
function Download($url, $dest) {
  if (Test-Path $Curl) { & $Curl -fL --retry 3 --progress-bar -o $dest $url; if ($LASTEXITCODE) { Fail "Không tải được $url. Kiểm tra mạng rồi chạy lại." } }
  else { try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest } catch { Fail "Không tải được $url. Kiểm tra mạng rồi chạy lại." } }
}

Write-Host '== Ghép Video · cài AI xem ảnh trên máy ==' -ForegroundColor Green

Step 'Ollama + Qwen3-VL Instruct (~5 GB)'
$Ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $Ollama) { $Ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe' }
if (-not (Test-Path $Ollama)) {
  $setup = Join-Path $env:TEMP 'OllamaSetup.exe'
  Write-Host 'Đang tải Ollama (~1,5 GB)…'
  Download 'https://ollama.com/download/OllamaSetup.exe' $setup
  # Wait for the installer process only: Start-Process -Wait would also wait for the Ollama app it launches (forever).
  $p = Start-Process $setup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -PassThru
  $p.WaitForExit()
  Remove-Item $setup -ErrorAction SilentlyContinue
}
if (-not (Test-Path $Ollama)) { Fail 'Chưa cài được Ollama. Cài tay tại ollama.com rồi chạy lại.' }
# Make sure the Ollama service answers before pulling the model (the installer may already have started it).
function OllamaUp { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:11434/api/tags' | Out-Null; $true } catch { $false } }
if (-not (OllamaUp)) { Start-Process $Ollama -ArgumentList 'serve' -WindowStyle Hidden; foreach ($i in 1..30) { if (OllamaUp) { break }; Start-Sleep 1 } }
if (-not (OllamaUp)) { Fail 'Không khởi động được Ollama.' }
& $Ollama pull qwen3-vl:4b-instruct
if ($LASTEXITCODE) { Fail 'Tải mô hình xem ảnh chưa xong. Chạy lại để tải tiếp.' }

Write-Host "`nĐã cài AI trên máy. Quay lại app Ghép Video và chọn Trên máy." -ForegroundColor Green
if (-not $env:GHEPVIDEO_CI) { Read-Host 'Bấm Enter để đóng' | Out-Null }
