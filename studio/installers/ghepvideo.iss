; Windows installer for Ghép Video (Inno Setup 6). Built by GitHub Actions:
;   set GHEPVIDEO_VERSION=2.3.0 & set GHEPVIDEO_SRC=<unzipped app folder> & ISCC.exe ghepvideo.iss
; Installs for the current user only (no admin prompt) into %USERPROFILE%\Ghép Video, so in-app updates can write
; there and media/output folders sit next to the app. After the wizard, a PowerShell window installs Python, FFmpeg,
; Ollama and the AI models with visible progress, then opens the app.
#define AppVersion GetEnv("GHEPVIDEO_VERSION")
#define SourceDir GetEnv("GHEPVIDEO_SRC")
#define OutDir GetEnv("GHEPVIDEO_OUT")

[Setup]
AppId={{6F0B8B7E-3C1D-4F8E-9D3B-5A7C2E1F9A40}
AppName=Ghép Video
AppVersion={#AppVersion}
AppVerName=Ghép Video {#AppVersion}
AppPublisher=Ghép Video
AppPublisherURL=https://github.com/nguyenlanh282/ghep-video
DefaultDirName={%USERPROFILE}\Ghép Video
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutDir}
OutputBaseFilename=GhepVideo-Setup-{#AppVersion}
SetupIconFile={#SourceDir}\studio\assets\icon.ico
UninstallDisplayIcon={app}\studio\assets\icon.ico
UninstallDisplayName=Ghép Video
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Messages]
WelcomeLabel1=Cài đặt Ghép Video [ver]
WelcomeLabel2=Dựng video dọc 9:16 từ ảnh, video và lời đọc. Mọi xử lý chạy trên máy của bạn.%n%nSau khi cài, một cửa sổ sẽ tải Python, FFmpeg và mô hình AI (khoảng 5 GB lần đầu, 10–30 phút tuỳ mạng). Xong sẽ tự mở app.
FinishedHeadingLabel=Đã cài xong phần app
FinishedLabel=Bấm Kết thúc để tải phần AI và mở Ghép Video. Đừng đóng cửa sổ tải cho tới khi app tự mở.
ClickFinish=Bấm Finish để tiếp tục.

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
Name: "{app}\Video - ảnh"
Name: "{app}\output"

[Icons]
; The launcher installs the AI parts itself if they are missing, then opens the app.
Name: "{userprograms}\Ghép Video"; Filename: "{app}\Ghep Video (Windows).bat"; WorkingDir: "{app}"; IconFilename: "{app}\studio\assets\icon.ico"; Flags: runminimized
Name: "{userdesktop}\Ghép Video"; Filename: "{app}\Ghep Video (Windows).bat"; WorkingDir: "{app}"; IconFilename: "{app}\studio\assets\icon.ico"; Flags: runminimized

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\studio\setup-windows.ps1"""; WorkingDir: "{app}\studio"; Description: "Tải phần AI và mở Ghép Video"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; App files only; the media and output folders (the user's work) are kept.
Type: filesandordirs; Name: "{app}\studio"
Type: filesandordirs; Name: "{app}\Ghép Video.app"
