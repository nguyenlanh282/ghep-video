# Cài đặt Ghép Video trên Windows 10/11. Chạy bằng "Cai dat (Windows).bat" ở thư mục dự án; chạy lại bao nhiêu lần cũng được.
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here
$Data = Join-Path $env:APPDATA 'GhepVideo'
$Venv = Join-Path $Data 'venv'
New-Item -ItemType Directory -Force -Path $Data, (Join-Path $Data 'models') | Out-Null

function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Need($cmd, $wingetId, $label) {
  if (Get-Command $cmd -ErrorAction SilentlyContinue) { return }
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "Cần cài $label. Máy chưa có winget: cài 'App Installer' từ Microsoft Store rồi chạy lại."
  }
  Write-Host "Cài $label…"
  winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements --silent
  Refresh-Path
}

Write-Host '== Ghép Video · cài đặt cho Windows =='
Need 'py' 'Python.Python.3.12' 'Python 3.12'
Need 'ffmpeg' 'Gyan.FFmpeg' 'FFmpeg'
Need 'ollama' 'Ollama.Ollama' 'Ollama (chạy AI xem ảnh)'

if (-not (Test-Path (Join-Path $Venv 'Scripts\python.exe'))) { py -3.12 -m venv $Venv }
$Py = Join-Path $Venv 'Scripts\python.exe'
& $Py -m pip install -q --upgrade pip
Write-Host 'Cài thư viện (lần đầu mất vài phút)…'
& $Py -m pip install -q -r (Join-Path $Here 'requirements-windows.txt')

Write-Host 'Tải mô hình nhận diện khuôn mặt…'
$Yunet = Join-Path $Data 'models\face_detection_yunet_2023mar.onnx'
if (-not (Test-Path $Yunet)) {
  Invoke-WebRequest 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx' -OutFile $Yunet
}

Write-Host 'Tải mô hình nghe lời đọc (khoảng 1,5 GB)…'
& $Py -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')"

Write-Host 'Tải mô hình AI xem ảnh qua Ollama (khoảng 3,3 GB)…'
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) { Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden; Start-Sleep 4 }
ollama pull qwen3-vl:4b

Write-Host 'Tạo biểu tượng trên Desktop…'
$Shell = New-Object -ComObject WScript.Shell
$Link = $Shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Ghép Video.lnk'))
$Link.TargetPath = Join-Path $Venv 'Scripts\pythonw.exe'
$Link.Arguments = '"' + (Join-Path $Here 'app\main.py') + '"'
$Link.WorkingDirectory = $Here
$Link.Save()

Write-Host ''
Write-Host 'Xong. Mở app bằng biểu tượng "Ghép Video" trên Desktop hoặc file "Ghep Video (Windows).bat".'
