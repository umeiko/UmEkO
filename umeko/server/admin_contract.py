"""Runtime and generated documentation share the administrator API contract."""
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from .. import __version__

# Endpoint names are stable identifiers; schema coverage tests catch undocumented additions.
OPERATIONS = {
    "health": ("服务状态", "读取管理服务健康状态，不表示模型调用可用。"),
    "login": ("管理员登录", "验证管理员账号密码，设置 umeko_admin Cookie，有效期最长 7 天；登录响应不返回模型密钥。"),
    "logout": ("退出管理员登录", "撤销当前 Cookie 对应的服务端登录令牌，并按相同管理前缀删除 Cookie。"),
    "me": ("当前管理员", "读取当前登录管理员的身份。普通用户和未登录请求均返回 401。"),
    "admin_schema": ("管理接口规范", "读取当前运行版本的完整 OpenAPI，包括参数、请求模型、认证与操作影响；需要管理员登录。"),
    "resources": ("资源监控", "读取主机、进程、任务队列、模型队列和历史采样；不发起模型调用。"),
    "service_accounts": ("服务账号列表", "返回账号、权限选项与接入方式；不返回已有账号的原始凭据。"),
    "service_access": ("读取机器接入方式", "读取凭据鉴权或共享匿名模式。此设置不改变管理员 API 鉴权。"),
    "update_service_access": ("设置机器接入方式", "required 为凭据鉴权，anonymous 为共享免鉴权；匿名调用不按 IP 隔离身份。管理 API 始终需要管理员。"),
    "agents": ("智能体目录与配置选项", "返回智能体、可选模型和技能目录；endpoints 指向用户服务，不是管理服务。"),
    "create_agent": ("创建智能体", "设置介绍、工作指引、默认主模型/视觉模型与技能范围；成功返回带 id 和 endpoints 的完整记录。"),
    "update_agent": ("更新智能体", "按完整表单更新；先读取原记录，仅改目标字段再提交。访问路径 slug 不可改，修改对新任务生效。"),
    "get_agent": ("读取智能体", "读取配置、默认模型、技能与公开入口；工作指引属于管理员数据。"),
    "delete_agent": ("删除智能体", "永久删除定义；有保留任务时可能返回 409，应先停用并等待生命周期清理。"),
    "managed_agent_card": ("预览 Agent Card", "返回当前已保存配置生成的公开名片，私有工作指引不放入 Card。"),
    "managed_mcp_disclosure": ("查看 MCP 接口披露", "读取 SDK 实际注册的工具、参数、资源和提示词，不执行工具。"),
    "create_service_account": ("创建服务账号", "原始 token 仅本次返回；请保存到调用者指定的受限位置。它是机器任务凭据，不能调用管理 API。"),
    "update_service_account": ("更新或轮换服务凭据", "enabled 控制启停；rotate=true 生成新凭据并撤销旧令牌。不要在超时后盲目重复轮换。停用不自动取消任务。"),
    "delete_service_account": ("删除服务账号及历史", "永久清理此账号的凭据、任务、事件、会话与文件；有活跃任务时返回 409。"),
    "monitored_tasks": ("机器任务列表", "读取机器调用记录；结合任务详情排查输入、输出和工具过程。"),
    "stop_machine_task": ("取消机器任务", "协作式请求取消；调用后继续查询终态，不能把请求成功等同于子进程已退出。"),
    "inspect_machine_task": ("机器任务详情", "返回任务、消息、工具、上下文与事件；仅读取记录，不唤醒执行模型。"),
    "inspect_task_files": ("任务会话文件树", "读取名称、目录、大小与时间等元数据；节点清理后可能返回快照，不提供文件内容备份。"),
    "users": ("用户列表", "列出可管理的用户身份，不返回登录密码。"),
    "create_user": ("创建用户", "创建 user 或 admin 角色账号；用户名必须唯一。"),
    "set_password": ("重置用户密码", "为指定用户设置密码；不把密码放进聊天记录、命令参数或日志。"),
    "user_model_access": ("读取用户模型权限", "返回供应商范围、模型范围和不含 Provider 凭据的可选目录。"),
    "set_user_model_access": ("设置用户模型权限", "两个字段均需提交。null 表示跟随全部/默认范围，[] 表示关闭；供应商与模型范围取交集。"),
    "tools": ("工具下发目录", "列出工具、分类与全局开关；不执行工具。"),
    "set_tool_dispatch": ("设置工具全局下发", "以 enabled 显式设置开关；个人授权可独立开放全局关闭的工具。submit_results 不在此开关范围。"),
    "user_tool_access": ("读取用户工具权限", "读取个人授权；null 跟随全局下发，[] 不开放可配置工具。"),
    "set_user_tool_access": ("设置用户工具权限", "allowed_tool_names 是完整个人清单，null 跟随全局。保存后下一轮使用新权限。"),
    "set_role": ("修改用户角色", "设置 user/admin；服务保留至少一个管理员，失去管理员角色的登录会话不能继续管理。"),
    "delete_user": ("删除用户与所属数据", "永久删除该用户及相关会话数据；不能删除最后一个管理员。"),
    "user_sessions": ("用户会话列表", "读取持久化会话及当前内存状态。"),
    "inspect_session": ("会话内容详情", "只读返回消息、工具、上下文摘要及挂载信息，不触发模型调用。"),
    "delete_session": ("删除会话与文件", "永久删除历史与会话目录；与仅驱逐缓存不同。"),
    "evict_session": ("驱逐会话缓存", "卸载内存态，保留历史；可能影响当前运行，调用前核对目标与活跃状态。"),
    "list_providers": ("供应商及模型目录", "管理员可读取完整 Provider api_key，结果须按敏感数据处理，不直接贴入 AI 对话。"),
    "create_provider": ("创建模型供应商", "配置上游地址、密钥和可选代理；base_url 是上游模型地址，与网页前缀无关。"),
    "update_provider": ("修改模型供应商", "只提交变更字段；api_key='********' 表示保留现有密钥。null 字段不更新。"),
    "delete_provider": ("删除模型供应商", "删除供应商及其模型，先核对当前默认模型和依赖它的智能体。"),
    "add_model": ("新增模型", "设置上游模型名称、视觉标记、用户下发及每模型并发；0 表示无限制。"),
    "update_model": ("修改模型能力与并发", "只提交变更字段。并发按模型 ID 共享，降低上限不打断已开始的调用；user_enabled 控制全局用户下发。"),
    "delete_model": ("删除模型", "删除模型配置；使用此默认模型的智能体需要重新配置。"),
    "activate_model": ("设置平台默认主模型", "设置后重载配置并驱逐在线会话缓存，可能影响活跃任务。"),
    "import_providers": ("批量导入供应商与模型", "document 包装导入内容；指定 active 时激活并重载。不是简单追加，不应盲目重试。"),
    "list_default_skills": ("技能下发列表", "读取数据库下发状态与管理员库的 imported/enabled/stale 信息。"),
    "toggle_default_skill": ("切换技能下发开关", "每次调用都会反转状态，不是幂等设置。先 GET 当前状态，仅在目标不同的时候调用一次，再回读。"),
    "import_default_skill": ("从技能库导入下发入口", "name 为包名.md，读取管理员库 SKILL.md 并写入默认下发配置，新会话生效。"),
    "get_default_skill": ("读取已下发技能入口", "读取数据库中的技能主指引，可能与管理员库源文件不同。"),
    "upload_default_skill": ("保存技能下发入口", "以 content 保存合法 SKILL.md 文本；不自动审批脚本或改写旧会话副本。"),
    "delete_default_skill": ("删除技能下发入口", "移除默认下发记录，不自动删除管理员库源文件和旧会话副本。"),
    "list_skill_scripts": ("列出技能代码", "列出包内 Python 文件和大小；辅助模块不一定是可执行入口。"),
    "get_skill_script": ("读取技能脚本或成员文本", "读取管理员库中的脚本或附属文本，包括 references 与 config.json；不是读取普通用户会话副本。"),
    "put_skill_script": ("保存技能代码", "content 必须为合法 Python；写入管理员库，仅保存不会赋予信任。目录路径相对当前包。"),
    "delete_skill_script": ("删除技能代码", "删除选定管理员库文件，不隐式删除信任审计和旧会话副本。"),
    "put_skill_member": ("保存技能附属文本", "保存 Markdown、JSON、YAML、TXT、CSV 等成员；Python 使用 skill-scripts。config.json 修改后需要审核新摘要。"),
    "delete_skill_member": ("删除技能附属文件", "删除指定包内成员；Python 文件需用 skill-scripts 入口。"),
    "get_runtime_config": ("读取工具回合上限", "返回持久化覆盖值；max_tool_iterations=null 表示没有覆盖。"),
    "set_runtime_config": ("设置工具回合上限", "0 为无限，null 清除覆盖，正整数为上限；修改会重载配置并驱逐在线会话缓存。"),
    "get_skill_source": ("读取技能库主指引", "name 为包名.md，映射到管理员库包目录的 SKILL.md。"),
    "put_skill_source": ("保存技能库主指引", "content 需包含合法技能 frontmatter；保存管理员库入口，与 default-skills 下发记录分开。"),
    "delete_skill_source": ("删除技能库主指引", "只删除主入口；配套成员和下发记录需要按用户要求分别处理。"),
    "skill_library_tree": ("管理员技能文件树", "列出包、脚本、成员及下发状态；包含孤立成员目录，字段中的名称不是服务器任意绝对路径。"),
    "skill_script_template": ("读取脚本模板", "返回当前确定性脚本的输入输出契约模板，不创建或执行脚本。"),
    "skill_security_catalog": ("查询可信代码目录", "搜索、筛选、分页查看当前版本和信任状态；不扫描或重新下发旧会话。"),
    "skill_security_selection": ("取得跨页选择快照", "返回所有筛选结果的明确文件版本，仅用于构建后续逐文件操作清单，不自动批准。"),
    "skill_security_batch": ("批量批准或撤销可信版本", "每批 1–200 项，各项核对 SHA-256；部分失败不回滚其他成功项，必须逐项检查 results。"),
    "skill_security_status": ("读取单文件安全门禁", "查看当前双摘要、批准与撤销记录；批准 current.sha256，撤销 approved.sha256。"),
    "approve_skill_file": ("批准当前文件版本", "提交预览 current.sha256；源字节已变返回 409。仅批准选定管理员库文件，不执行、不重签旧会话。"),
    "revoke_skill_file": ("撤销文件可信版本", "提交 approved.sha256，事务内撤销并审计；拦截旧授权后续执行，不中断已启动脚本。"),
    "test_skill_script": ("测试已批准的技能脚本", "args 为 JSON 对象字符串，timeout 限制在 1–30 秒；整包受保护代码/配置必须获准。临时工作目录不是安全沙箱。"),
}


def install_admin_contract(app, base_path: str) -> None:
    def schema():
        if app.openapi_schema is not None:
            return app.openapi_schema
        spec = get_openapi(title=app.title, version=__version__, routes=app.routes,
                           servers=[{"url": base_path or "/"}])
        spec.setdefault("components", {}).setdefault("securitySchemes", {})["umeko_admin"] = {
            "type": "apiKey", "in": "cookie", "name": "umeko_admin",
            "description": "POST /admin/login 后保存的管理员 Cookie；用户 Cookie 和机器服务 Token 均不能替代。",
        }
        for route in app.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            name = route.endpoint.__name__
            title, behavior = OPERATIONS[name]
            for method in route.methods:
                operation = spec["paths"][route.path_format][method.lower()]
                operation["summary"] = title
                operation["description"] = behavior
                public = name in {"health", "login", "logout"}
                operation["security"] = [] if public else [{"umeko_admin": []}]
                operation["x-umeko-mutating"] = method not in {"GET", "HEAD"}
                operation["x-umeko-automatic-retry"] = False
                if not public:
                    operation["responses"]["401"] = {"description": "未登录、会话失效或不是管理员。"}
        app.openapi_schema = spec
        return spec
    app.openapi = schema
