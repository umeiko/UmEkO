"""PyInstaller 打包入口：python -m umeko.server 的等价物。

用法（打包后）：umeko-server.exe [--port 8000] [--admin-port 9000] [--no-admin]
"""

if __name__ == "__main__":
    import sys

    if len(sys.argv) == 4 and sys.argv[1] == "--run-skill-script":
        # A frozen executable has no separate Python interpreter. Its child process
        # runs an installed library script after applying the usual path checks.
        import runpy
        from umeko.skills.script_runner import _resolve_script

        target = _resolve_script(sys.argv[2], sys.argv[3])
        sys.argv = [str(target)]
        runpy.run_path(str(target), run_name="__main__")
    else:
        from umeko.server.__main__ import main

        main()
