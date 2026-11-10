"""Install Claude Code or Codex for the picture AI (the app's "Cài" button)."""
import json, sys
import platform_tools

def emit(progress, message, **extra):
    print(json.dumps(dict(progress=progress, message=message, **extra), ensure_ascii=False), flush=True)

if __name__ == '__main__':
    platform_tools.utf8_stdio()
    try:
        platform_tools.install_ai(sys.argv[1], emit)
        emit(100, f'Đã cài {platform_tools.AI_NAMES[sys.argv[1]]}. Bấm “Đăng nhập” để dùng gói của bạn.', done=True)
    except Exception as e: emit(-1, str(e), error=True); sys.exit(1)
