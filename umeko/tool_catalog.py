"""Platform tool identities and administration labels; no session handlers or domain rules."""
from __future__ import annotations

TOOL_CATALOG = (
    ("read_document", "读取文档", "Read documents", "files"),
    ("list_dir", "列出目录", "List directories", "files"),
    ("find_files", "查找文件", "Find files", "files"),
    ("grep_files", "搜索文件内容", "Search file contents", "files"),
    ("write_file", "写入文件", "Write files", "files"),
    ("replace_in_file", "替换文件内容", "Replace file contents", "files"),
    ("file_operate", "文件与目录管理", "Manage files and directories", "files"),
    ("archive_tool", "压缩与解压", "Create and extract archives", "files"),
    ("download_url", "网址下载文件", "Download files from URLs", "files"),
    ("read_image", "读取图片", "Read images", "vision"),
    ("image_reasoning", "图像推理", "Image reasoning", "vision"),
    ("list_skill_packs", "列出技能包", "List skill packs", "skills"),
    ("use_skill", "加载技能", "Load skills", "skills"),
    ("read_pack_file", "读取技能附属文件", "Read skill resources", "skills"),
    ("list_skill_script", "查看技能脚本", "Inspect skill scripts", "skills"),
    ("run_skill_script", "执行技能脚本", "Run skill scripts", "skills"),
    ("create_skill", "创建技能", "Create skills", "skills"),
    ("read_working_doc", "读取工作文档", "Read working notes", "coordination"),
    ("write_working_doc", "写入工作文档", "Write working notes", "coordination"),
    ("delegate_task", "委派子 Agent", "Delegate to a subagent", "coordination"),
    ("run_command", "执行命令", "Run commands", "coordination"),
    ("submit_results", "提交机器任务答案", "Submit machine task results", "protocol"),
)
REQUIRED_TOOLS = frozenset({"submit_results"})
CONFIGURABLE_TOOLS = frozenset(name for name, *_ in TOOL_CATALOG) - REQUIRED_TOOLS


def tool_catalog() -> list[dict]:
    return [{"name": name, "title": title, "title_en": english, "group": group,
             "required": name in REQUIRED_TOOLS,
             "max_bytes": 20 * 1024 * 1024 if name == "download_url" else None}
            for name, title, english, group in TOOL_CATALOG]
