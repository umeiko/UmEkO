"""PyInstaller 打包入口：python -m umeko.server 的等价物。

用法（打包后）：umeko-server.exe [--port 8000] [--admin-port 9000] [--no-admin]
"""

from umeko.server.__main__ import main

if __name__ == "__main__":
    main()
