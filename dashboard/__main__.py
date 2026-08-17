"""以 `python3 -m dashboard` 啟動本機儀表板。"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("dashboard.server:app", host="127.0.0.1", port=8000)
