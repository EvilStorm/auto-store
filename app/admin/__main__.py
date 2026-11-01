import os
import sys

import uvicorn


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    host = os.getenv("ADMIN_HOST", "127.0.0.1")   # 로컬 전용. 다른 기기에서 열려면 명시적으로 바꾼다
    port = int(os.getenv("ADMIN_PORT", "8000"))
    uvicorn.run("app.admin.main:app", host=host, port=port, reload=False, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
