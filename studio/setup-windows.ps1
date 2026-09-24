# Cài đặt Ghép Video trên Windows 10/11 (64-bit). Không cần cài Python hay FFmpeg trước.
# Tự cài: Python 3.12 (qua uv), FFmpeg, thư viện, mô hình nghe lời đọc; tạo biểu tượng Desktop; mở app.
# AI xem ảnh: dùng gói Claude / ChatGPT của khách (Claude Code / Codex), hoặc AI trên máy qua setup-local-ai.ps1 (nút trong app).
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

Write-Host '== Ghép Video · cài đặt cho Windows ==' -ForegroundColor Green
if (-not [Environment]::Is64BitOperatingSystem) { Fail 'Cần Windows 64-bit.' }

Step '1/5 FFmpeg (xử lý video)'
if ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue)) { Write-Host 'Đã có sẵn.' }
elseif ((Test-Path "$Bin\ffmpeg.exe") -and (Test-Path "$Bin\ffprobe.exe")) { Write-Host 'Đã có sẵn trong thư mục cài đặt.' }
else {
  $zip = Join-Path $env:TEMP 'ghepvideo-ffmpeg.zip'
  Write-Host 'Đang tải FFmpeg (~190 MB)…'
  Download 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' $zip
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $z = [IO.Compression.ZipFile]::OpenRead($zip)
  foreach ($e in $z.Entries) { if ($e.Name -in 'ffmpeg.exe', 'ffprobe.exe') { [IO.Compression.ZipFileExtensions]::ExtractToFile($e, (Join-Path $Bin $e.Name), $true) } }
  $z.Dispose(); Remove-Item $zip
}

Step '2/5 Python 3.12'
$Uv = Join-Path $Bin 'uv.exe'
if (-not (Test-Path $Uv)) {
  $zip = Join-Path $env:TEMP 'ghepvideo-uv.zip'
  Download 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' $zip
  Expand-Archive -Force $zip (Join-Path $env:TEMP 'ghepvideo-uv'); Copy-Item (Join-Path $env:TEMP 'ghepvideo-uv\uv.exe') $Uv; Remove-Item $zip
}
$Py = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $Py)) { & $Uv venv --seed --python 3.12 $Venv; if ($LASTEXITCODE) { Fail 'Không tạo được môi trường Python.' } }

Step '3/5 Thư viện (lần đầu mất vài phút)'
& $Uv pip install --python $Py -q -r (Join-Path $Here 'requirements-windows.txt')
if ($LASTEXITCODE) { Fail 'Cài thư viện chưa được.' }

Step '4/5 Nhận diện khuôn mặt + nghe lời đọc (~1,5 GB)'
$Yunet = Join-Path $Data 'models\face_detection_yunet_2023mar.onnx'
if (-not (Test-Path $Yunet)) { Download 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx' $Yunet }
& $Py -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')"
if ($LASTEXITCODE) { Fail 'Tải mô hình nghe lời đọc chưa xong. Chạy lại để tải tiếp.' }

Step '5/5 Biểu tượng trên Desktop'
$Shell = New-Object -ComObject WScript.Shell
$Link = $Shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Ghép Video.lnk'))
$Link.TargetPath = Join-Path $Venv 'Scripts\pythonw.exe'
$Link.Arguments = '"' + (Join-Path $Here 'app\main.py') + '"'
$Link.WorkingDirectory = $Here
$Link.IconLocation = Join-Path $Here 'assets\icon.ico'
$Link.Save()

Write-Host "`nCài đặt xong." -ForegroundColor Green
if (-not $NoOpen) {
  Write-Host 'Đang mở Ghép Video…'
  $env:PYTHONUTF8 = '1'
  Start-Process (Join-Path $Venv 'Scripts\pythonw.exe') -ArgumentList ('"' + (Join-Path $Here 'app\main.py') + '"') -WorkingDirectory $Here
}
