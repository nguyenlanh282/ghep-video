"""Puts FFmpeg + ffprobe in place when a computer has none the app can find (run by the app before the first task)."""
import json, sys
import platform_tools

def emit(progress, message, **extra):
    print(json.dumps(dict(progress=progress, message=message, **extra), ensure_ascii=False), flush=True)

if __name__ == '__main__':
    platform_tools.utf8_stdio()
    try:
        if platform_tools.missing_tools(): platform_tools.install_tools(emit)
        emit(100, 'Đã cài xong FFmpeg. Bấm lại nút bạn vừa bấm để tiếp tục.', done=True)
    except Exception as e: emit(-1, str(e), error=True); sys.exit(1)
