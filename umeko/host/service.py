"""宿主服务层（L2）：把 L1 运行时组装成可被各交付端复用的服务。

本包不 import 任何 Web 框架：
- server/（FastAPI，云场景）只做 HTTP/SSE 适配；
- 未来本地 IDE 入口可进程内直接使用，或本地 HTTP 复用同一服务。
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .. import events as ev
from ..agent import UmekoAgent
from ..cancellation import OperationCancelled
from ..config import ModelConfig, Settings, apply_overrides
from ..prompts.system import DEFAULT_SYSTEM
from ..runtime import app_dir
from ..runner import Run, RunManager, TERMINAL_STATUSES
from ..session import Session
from ..tree import TreeNode, TreeBudget, build_tree, compile_filter
from .profile import CLOUD_PROFILE, Profile
from ..skillpacks import parse_skill_pack_text
from .storage import Store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_kind(path: Path) -> str:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return "image"
    if path.suffix.lower() == ".svg":
        return "svg"
    if path.suffix.lower() in {".log", ".txt", ".md", ".csv", ".json", ".xml", ".html"}:
        return "text"
    return "file"


@dataclass
class SessionState:
    id: str
    created_at: str
    root: Path
    session: Session
    agent: UmekoAgent
    user_id: str = ""
    title: str = "未命名会话"
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    files: dict[str, Path] = field(default_factory=dict)
    active_run_holder: dict = field(default_factory=lambda: {"run": None}, repr=False)
    mounted_resources: dict[str, set[str]] = field(
        default_factory=lambda: {"skills": set()}, repr=False
    )
    builtin_resources: dict[str, set[str]] = field(
        default_factory=lambda: {"skills": set()}, repr=False
    )


class AgentService:
    """宿主服务（L2）：Session 装配、运行调度、工作区与 Skill 资源。

    纯 Python 实现，不依赖任何 Web 框架；FastAPI（云）/ 本地 IDE / CLI
    各自作为薄适配层复用它。Session 与运行态在内存，历史与挂载在 SQLite。
    """

    WORKSPACE_ROOTS = ("workspace", "attachments", "generate")

    def __init__(
        self,
        settings: Settings,
        data_root: str | Path,
        workspace_root: str | Path = "output",
        store: Store | None = None,
        profile: Profile = CLOUD_PROFILE,
        command_runner=None,
    ):
        self._base_settings = settings
        self.profile = profile
        # run_command 工具后端（CommandRunner 协议）；云场景必须保持 None
        self._command_runner = command_runner if profile.allow_command else None
        self.data_root = Path(data_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.store = store or Store(self.data_root / "umeko.db")
        # DB 配置覆盖层（管理面在线修改）优先于 .env；内存中生效配置可随时重载
        self.settings = apply_overrides(settings, self.store.config())
        self.sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()
        self.run_manager = RunManager(max_workers=4)

    @property
    def runs(self) -> dict[str, Run]:
        """兼容入口：Run 注册表由 RunManager 持有。"""
        return self.run_manager.runs

    # ---------- Workspace 文件树 ----------

    def session_workspace(self, session_id: str) -> Path:
        root = self.get_session(session_id).root / "workspace"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _workspace_path(
        self, session_id: str, relative_path: str, *, must_exist: bool = True,
        allow_root: bool = True,
    ) -> Path:
        session = self.get_session(session_id)
        if not relative_path or "\x00" in relative_path:
            raise ValueError("文件路径不能为空")
        candidate = (session.root / relative_path).resolve()
        try:
            relative = candidate.relative_to(session.root)
        except ValueError as exc:
            raise ValueError("文件路径超出当前 Session 工作区") from exc
        if not relative.parts or relative.parts[0] not in self.WORKSPACE_ROOTS:
            raise ValueError("该 Session 内部目录不允许通过 Workspace 访问")
        if not allow_root and len(relative.parts) == 1:
            raise ValueError("不能修改 Workspace 顶级目录")
        if must_exist and not candidate.exists():
            raise FileNotFoundError(relative_path)
        return candidate

    def workspace_tree(self, session_id: str, filter: str = "") -> list[dict]:
        session = self.get_session(session_id)
        try:
            rx = compile_filter(filter or None)
        except ValueError as e:
            raise ValueError(str(e))
        budget = TreeBudget()
        nodes: list[dict] = []
        for name in self.WORKSPACE_ROOTS:
            directory = session.root / name
            if not directory.is_dir():
                continue
            tree = build_tree(directory, budget=budget, pattern=filter or None)
            tree.path = name  # 可读根显示名（真实目录名可能不同）
            nodes.append(self._tree_node_to_dict(tree))
        return nodes

    @staticmethod
    def _tree_node_to_dict(node: TreeNode) -> dict:
        base = {
            "name": node.name,
            "path": node.path,
            "type": "directory" if node.is_dir else "file",
            "children": [AgentService._tree_node_to_dict(c) for c in node.children],
        }
        if not node.is_dir:
            base["size"] = node.size
        if node.omitted or node.children_truncated:
            base["truncated"] = True
            omitted = node.omitted
            tail = node.children[-1] if node.children else None
            tail_name = tail.name if tail is not None else None
            hint = f"其余 {omitted} 项" if omitted else "部分内容"
            base["children"].append({
                "name": f"…（{hint}被折叠）",
                "path": f"{node.path}/__truncated__",
                "type": "file",
                "size": None,
                "children": [],
                "virtual": True,
            })
        return base

    def workspace_file(self, session_id: str, relative_path: str) -> Path:
        candidate = self._workspace_path(session_id, relative_path)
        if not candidate.is_file():
            raise FileNotFoundError(relative_path)
        return candidate

    def workspace_download(self, session_id: str, relative_path: str) -> tuple[Path, bool]:
        """返回下载目标；目录会打包为临时 ZIP，并由响应层负责删除。"""
        target = self._workspace_path(session_id, relative_path)
        if target.is_file():
            return target, False
        if not target.is_dir():
            raise FileNotFoundError(relative_path)

        session_root = self.get_session(session_id).root.resolve()
        target_root = target.resolve()
        handle = tempfile.NamedTemporaryFile(
            prefix="umeko-directory-", suffix=".zip", delete=False
        )
        archive = Path(handle.name)
        handle.close()
        try:
            with zipfile.ZipFile(
                archive, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
            ) as output:
                root_name = target.name
                output.writestr(f"{root_name}/", b"")
                for path in sorted(target.rglob("*"), key=lambda item: item.as_posix()):
                    if path.is_symlink():
                        continue
                    resolved = path.resolve(strict=True)
                    try:
                        resolved.relative_to(session_root)
                        resolved.relative_to(target_root)
                    except ValueError as exc:
                        raise ValueError("目录中包含超出当前 Session 的路径") from exc
                    member = Path(root_name, *path.relative_to(target).parts).as_posix()
                    if path.is_dir():
                        output.writestr(member.rstrip("/") + "/", b"")
                    elif path.is_file():
                        output.write(path, member)
            return archive, True
        except Exception:
            archive.unlink(missing_ok=True)
            raise

    def web_text(self, session_id: str, content: str | None) -> str | None:
        """隐藏服务器路径，同时保留可点击的 Session 文件引用。

        本地场景（profile.mask_paths=False）路径本来就在用户自己机器上，
        直接原样返回，方便 IDE 展示与跳转。
        """
        if not content or not self.profile.mask_paths:
            return content
        session = self.get_session(session_id)
        session_root = str(session.root.resolve())
        root_variants = {session_root, session_root.replace("\\", "/")}
        if not any(source in content for source in root_variants):
            return content
        replacements: list[tuple[str, str]] = []
        for root_name in self.WORKSPACE_ROOTS:
            root = session.root / root_name
            if not root.exists():
                continue
            for path in (root, *root.rglob("*")):
                try:
                    relative = path.resolve().relative_to(session.root).as_posix()
                except (OSError, ValueError):
                    continue
                if path.is_file():
                    replacement = f"[{relative}](workspace-file:{quote(relative, safe='')})"
                elif path.is_dir():
                    replacement = f"`{relative}`"
                else:
                    continue
                resolved = str(path.resolve())
                replacements.extend(
                    (
                        (resolved, replacement),
                        (resolved.replace("\\", "/"), replacement),
                    )
                )

        rendered = content
        for source, replacement in sorted(set(replacements), key=lambda item: len(item[0]), reverse=True):
            rendered = rendered.replace(source, replacement)

        for source in root_variants:
            rendered = rendered.replace(source, "当前 Session")
        return rendered

    def create_workspace_entry(self, session_id: str, relative_path: str, entry_type: str) -> Path:
        target = self._workspace_path(session_id, relative_path, must_exist=False, allow_root=False)
        if target.exists():
            raise ValueError(f"已存在：{relative_path}")
        if not target.parent.is_dir():
            raise ValueError("父目录不存在")
        if entry_type == "directory":
            target.mkdir()
        elif entry_type == "file":
            target.touch()
        else:
            raise ValueError("不支持的文件类型")
        return target

    def transfer_workspace_entry(
        self, session_id: str, source_path: str, target_path: str, operation: str
    ) -> Path:
        session = self.get_session(session_id)
        source = self._workspace_path(session_id, source_path, allow_root=False)
        target = self._workspace_path(session_id, target_path, must_exist=False, allow_root=False)
        if target.exists():
            raise ValueError(f"目标已存在：{target_path}")
        if not target.parent.is_dir():
            raise ValueError("目标父目录不存在")
        if source.is_dir() and (target == source or source in target.parents):
            raise ValueError("不能把目录移动或复制到自身内部")
        if operation == "copy":
            shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)
        elif operation == "move":
            shutil.move(str(source), str(target))
            for file_id, registered in list(session.files.items()):
                try:
                    tail = registered.relative_to(source)
                except ValueError:
                    continue
                session.files[file_id] = target / tail
        else:
            raise ValueError("不支持的文件操作")
        return target

    def delete_workspace_entry(self, session_id: str, relative_path: str) -> None:
        session = self.get_session(session_id)
        target = self._workspace_path(session_id, relative_path, allow_root=False)
        for file_id, registered in list(session.files.items()):
            if registered == target or target in registered.parents:
                session.files.pop(file_id, None)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def save_workspace_file(
        self, session_id: str, filename: str, content: bytes,
        relative_dir: str = "",
    ) -> Path:
        clean_name = Path(filename).name.strip()
        if not clean_name:
            raise ValueError("文件名不能为空")
        # relative_dir：workspace 内的目标子目录（拖拽到具体目录时传入），
        # 经 _workspace_path 校验，防越界；为空 = workspace 根
        workspace = self.session_workspace(session_id)
        if relative_dir:
            target_dir = self._workspace_path(
                session_id, relative_dir, must_exist=True, allow_root=False
            )
            if not target_dir.is_dir():
                raise ValueError(f"目标目录不存在：{relative_dir}")
        else:
            target_dir = workspace
        stem = Path(clean_name).stem
        suffix = Path(clean_name).suffix
        path = target_dir / clean_name
        counter = 1
        while path.exists():
            path = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        path.write_bytes(content)
        return path

    # ---------- 压缩包解压（7-Zip） ----------

    ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".tgz"}

    def extract_archive(self, session_id: str, relative_path: str) -> Path:
        """用本机 7-Zip 把 workspace 内的压缩包解压到同名目录（不覆盖已有文件）。

        返回解压目标目录。安全：目标目录保持在 workspace 内；7z 已带防路径
        穿越（-snld 前缀剥离 + 目标限制）；超出预算（条目/累计体积）时中止。
        """
        import subprocess

        archive = self._workspace_path(session_id, relative_path, must_exist=True)
        if archive.suffix.lower() not in self.ARCHIVE_SUFFIXES:
            raise ValueError(
                f"不支持的压缩包格式：{archive.suffix or '(无后缀)'}。"
                f"支持：{'、'.join(sorted(self.ARCHIVE_SUFFIXES))}"
            )
        seven_zip = Path(os.environ.get("SEVENZIP_PATH", r"C:\Program Files\7-Zip\7z.exe"))
        if not seven_zip.is_file():
            raise ValueError(
                "未找到 7-Zip（默认路径 C:\\Program Files\\7-Zip\\7z.exe），"
                "请安装或用环境变量 SEVENZIP_PATH 指定 7z.exe 位置。"
            )
        target = archive.parent / archive.stem
        # 同名目录已存在：追加序号，避免混淆旧解压结果
        final_target = target
        counter = 1
        while final_target.exists():
            final_target = archive.parent / f"{archive.stem}_{counter}"
            counter += 1
        final_target.mkdir(parents=True)
        workspace = self.session_workspace(session_id).resolve()
        try:
            result = subprocess.run(
                [str(seven_zip), "x", "-y", f"-o{final_target}", str(archive)],
                capture_output=True, text=True, timeout=300,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(final_target, ignore_errors=True)
            raise ValueError("解压超时（5 分钟），已中止并清理。") from exc
        if result.returncode != 0:
            shutil.rmtree(final_target, ignore_errors=True)
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            raise ValueError("解压失败：" + (detail[-1] if detail else f"7z 退出码 {result.returncode}"))
        # 安全校验：解压产物必须全部落在 workspace 内
        for p in final_target.rglob("*"):
            try:
                p.resolve().relative_to(workspace)
            except ValueError as exc:
                shutil.rmtree(final_target, ignore_errors=True)
                raise ValueError("压缩包内含越界路径，已中止并清理。") from exc
        return final_target

    # ---------- Session 生命周期 ----------

    def create_session(
        self,
        *,
        user_id="",
        title="未命名会话",
        _restore_id=None,
        settings: Settings | None = None,
    ) -> SessionState:
        effective = settings if settings is not None else self.settings
        session_id = _restore_id or f"sess_{uuid.uuid4().hex}"
        root = self.data_root / "users" / user_id / "sessions" / session_id
        root.mkdir(parents=True, exist_ok=bool(_restore_id))
        (root / "workspace").mkdir(exist_ok=True)
        (root / "attachments").mkdir(exist_ok=True)
        (root / "generate").mkdir(exist_ok=True)
        builtin_resources = {"skills": set()}
        target = root / "client" / "skills"
        target.mkdir(parents=True, exist_ok=True)
        # Skill 分发唯一通道：管理员在管理面「默认 Skill」维护（default_skills 表）。
        # 文件系统 skills/ 目录不再自动播种——是否下发由管理员决定。
        for item in self.store.default_skills():
            dest = target / item["name"]
            if not dest.exists():
                dest.write_text(item["content"], encoding="utf-8")
            if parse_skill_pack_text(item["content"]) is not None:
                builtin_resources["skills"].add(item["name"])

        session = Session(
            effective,
            root / "generate",
            skill_dir=root / "client" / "skills",
        )
        holder: dict[str, Run | None] = {"run": None}

        tool_event_ids = {"main": [], "subagent": []}  # started→completed 关联队列

        def on_event(event_type: str, data: dict) -> None:
            """引擎事件（L1）-> 宿主事件（L2），Web 前端 SSE 契约保持不变。"""
            run = holder["run"]
            if run is None:
                return
            if event_type == ev.ASSISTANT_DELTA:
                text = data.get("text", "")
                run.emit("assistant.delta", text=text)
                run.emit("usage.delta", chars=len(text), kind="assistant")
            elif event_type == ev.REASONING_DELTA:
                text = data.get("text", "")
                run.emit("reasoning.status", status="thinking")
                run.emit("reasoning.delta", text=text)
                run.emit("usage.delta", chars=len(text), kind="reasoning")
            elif event_type == ev.TOOL_TICK:
                run.emit("usage.delta", chars=len(data.get("text", "")), kind="tool")
            elif event_type == ev.TOOL_STARTED:
                run.emit("tool.started", name=data.get("name"),
                         arguments=data.get("arguments"))
                try:
                    db_id = self.store.add_tool_event(
                        session_id, agent="main", name=data.get("name", "tool"),
                        arguments=json.dumps(data.get("arguments"), ensure_ascii=False)
                        if data.get("arguments") is not None else None,
                        run_id=run.id,
                    )
                    tool_event_ids["main"].append(db_id)
                except Exception:
                    pass  # 持久化失败不阻断运行
            elif event_type == ev.TOOL_COMPLETED:
                name = data.get("name", "tool")
                run.emit("tool.completed", name=name, result=data.get("result"))
                run.emit("workspace.changed", reason=f"tool:{name}")
                pending = tool_event_ids["main"]
                if pending:
                    db_id = pending.pop(0)
                    try:
                        self.store.complete_tool_event(
                            db_id,
                            json.dumps(data.get("result"), ensure_ascii=False)
                            if data.get("result") is not None else None,
                        )
                    except Exception:
                        pass
            elif event_type == ev.TOOL_PROGRESS:
                run.emit("tool.progress", name=data.get("name"),
                         output_delta=data.get("output_delta", ""))
            elif event_type == ev.PROGRESS_UPDATED:
                run.emit("progress.updated", message=data.get("message"))
                run.emit("workspace.changed", reason="progress")
            elif event_type.startswith(ev.SUBAGENT_PREFIX):
                run.emit(event_type, **data)
                sub = event_type[len(ev.SUBAGENT_PREFIX):]
                if sub == "usage":
                    run.emit("usage.delta", chars=data.get("chars", 0), kind="subagent")
                if sub == "tool.started":
                    try:
                        db_id = self.store.add_tool_event(
                            session_id, agent="subagent", name=data.get("name", "tool"),
                            arguments=json.dumps(data.get("arguments"), ensure_ascii=False)
                            if data.get("arguments") is not None else None,
                            run_id=run.id,
                        )
                        tool_event_ids["subagent"].append(db_id)
                    except Exception:
                        pass
                if sub == "tool.completed":
                    run.emit("workspace.changed",
                             reason=f"subagent:{data.get('name', 'tool')}")
                    pending = tool_event_ids["subagent"]
                    if pending:
                        db_id = pending.pop(0)
                        try:
                            self.store.complete_tool_event(
                                db_id,
                                json.dumps(data.get("result"), ensure_ascii=False)
                                if data.get("result") is not None else None,
                            )
                        except Exception:
                            pass

        agent = UmekoAgent(
            effective,
            session,
            DEFAULT_SYSTEM,
            output_root=root,
            readable_root=root,
            readable_roots=tuple(root / name for name in self.WORKSPACE_ROOTS),
            command_runner=self._command_runner,
            should_cancel=lambda: bool(
                holder["run"] and holder["run"].cancel_requested()
            ),
            on_event=on_event,
        )
        state = SessionState(
            session_id, _now(), root, session, agent, user_id=user_id, title=title,
            active_run_holder=holder, builtin_resources=builtin_resources,
        )
        with self._lock:
            self.sessions[session_id] = state
        if _restore_id:
            state.mounted_resources = self.store.resource_mounts(session_id)
            self._activate_mounted_resources(state)
            summary, messages = self.store.context_messages(session_id)
            agent.restore_history(messages, summary)
            # 恢复附件映射：上次会话上传的 file_id → 磁盘文件（失效路径自动剔除）
            state.files.update(self.store.session_files(session_id))
        else:
            self.store.save_session(session_id, user_id, title)
        return state

    def get_session(self, session_id: str) -> SessionState:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            record = self.store.session_by_id(session_id)
            if record is None:
                raise KeyError(f"未知会话：{session_id}") from exc
            return self.create_session(
                user_id=record["user_id"], title=record["title"],
                _restore_id=session_id,
            )

    # ---------- Run 执行 ----------

    def create_run(self, session_id: str, user_input: str, attachments: list[str]) -> Run:
        session = self.get_session(session_id)
        active = session.active_run_holder["run"]
        if active is not None and active.status not in {"completed", "failed", "cancelled"}:
            raise ValueError("当前 Session 已有任务正在运行")
        # 用户级/会话级模型选择在每个新 Run 生效：配置有变化就重装配该 Session
        # （DB 历史保留，重建后自动恢复上下文，不影响其他在线 Session）。
        effective = self.effective_settings_for(session.user_id, session_id)
        if effective != session.agent.settings:
            record = self.store.session_by_id(session_id)
            self.evict_session(session_id)
            session = self.create_session(
                user_id=record["user_id"], title=record["title"],
                _restore_id=session_id, settings=effective,
            )
        if session.title == "未命名会话":
            title = " ".join(user_input.strip().split())[:28] or "未命名会话"
            session.title = title
            self.store.rename_session(session_id, session.user_id, title)
        paths: list[Path] = []
        for file_id in attachments:
            if file_id not in session.files:
                raise ValueError(f"未知附件：{file_id}")
            paths.append(session.files[file_id])
        self.store.add_message(
            session_id, "user", user_input,
            json.dumps([path.name for path in paths], ensure_ascii=False),
        )
        run = self.run_manager.create(session_id)  # 自带 run.queued 事件并入注册表
        session.active_run_holder["run"] = run
        self.run_manager.submit(
            run, lambda: self._execute_run(session, run, user_input, paths)
        )
        return run

    def _execute_run(
        self, session: SessionState, run: Run, user_input: str, paths: list[Path]
    ) -> None:
        with session.lock:
            if run.cancel_requested():
                self._finish_cancelled(session, run)
                return
            run.status = "running"
            run.emit("run.started")
            try:
                image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
                images = [path for path in paths if path.suffix.lower() in image_suffixes]
                documents = [path for path in paths if path not in images]
                prompt = user_input
                session.mounted_resources = self.store.resource_mounts(session.id)
                activated = self._activate_mounted_resources(session)
                for item in activated:
                    run.emit("resource.activated", **item)
                mounted = self.mounted_prompt(session)
                if mounted:
                    prompt += mounted
                if documents:
                    prompt += (
                        "\n\n[系统提供的本轮用户附件]\n"
                        + "\n".join(f"- {path.name}: {path}" for path in documents)
                        + "\n在回答本轮问题前，必须先用 read_document 读取上述附件；"
                        "不要只根据文件名或用户描述猜测内容。"
                    )
                reply = session.agent.chat(prompt, images=images or None)
                self.store.add_message(session.id, "assistant", reply)
                if run.cancel_requested():
                    run.finish("cancelled", reply=reply)
                else:
                    run.finish("completed", reply=reply)
            except OperationCancelled:
                self._finish_cancelled(session, run)
            except Exception as exc:
                run.finish("failed", error=str(exc))
            finally:
                if session.active_run_holder["run"] is run:
                    session.active_run_holder["run"] = None

    def _finish_cancelled(self, session: SessionState, run: Run) -> None:
        reply = "任务已停止。"
        self.store.add_message(session.id, "assistant", reply)
        run.finish("cancelled", reply=reply)
        if session.active_run_holder["run"] is run:
            session.active_run_holder["run"] = None

    def active_run(self, session_id: str) -> Run | None:
        run = self.get_session(session_id).active_run_holder["run"]
        if run is None or run.status in {"completed", "failed", "cancelled"}:
            return None
        return run

    def context_stats(self, session_id: str) -> dict:
        return self.get_session(session_id).agent.context_stats()

    def compact_context(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        active = session.active_run_holder["run"]
        if active is not None and active.status not in {"completed", "failed", "cancelled"}:
            raise ValueError("任务运行中，暂时不能压缩上下文")
        with session.lock:
            result = session.agent.compact_context()
            if not result.get("compressed"):
                return result
            response = dict(result)
            summary = response.pop("summary")
            retained = response.pop("retained_plain_messages")
            self.store.save_context_summary(session_id, summary, retained)
            return response

    def clear_context(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        active = session.active_run_holder["run"]
        if active is not None and active.status not in {"completed", "failed", "cancelled"}:
            raise ValueError("任务运行中，暂时不能清空上下文")
        with session.lock:
            result = session.agent.clear_context()
            self.store.clear_context(session_id)
            return result

    def cancel_run(self, run_id: str) -> Run:
        run = self.get_run(run_id)
        run.request_cancel()
        return run

    # ---------- 管理面（仅 admin 端口暴露；用户面路由不含这些入口） ----------

    def evict_session(self, session_id: str) -> bool:
        """驱逐内存态 Session（取消在跑 Run、丢弃 Agent）；DB 历史保留。"""
        with self._lock:
            state = self.sessions.pop(session_id, None)
        if state is None:
            return False
        run = state.active_run_holder["run"]
        if run is not None and not run.finished:
            run.request_cancel()
        return True

    def evict_all_sessions(self) -> int:
        """配置变更后调用：驱逐全部内存态 Session，下次访问按新配置重装配。"""
        with self._lock:
            ids = list(self.sessions)
        evicted = sum(1 for sid in ids if self.evict_session(sid))
        return evicted

    # ---------- 用户级模型解析 ----------

    @staticmethod
    def _config_from_row(row: dict, default_proxy: str | None) -> ModelConfig:
        return ModelConfig(
            name=row["model"], api_key=row["api_key"],
            base_url=row["base_url"], proxy=row["proxy"] or default_proxy,
        )

    def effective_settings_for(
        self, user_id: str, session_id: str | None = None
    ) -> Settings:
        """按优先级解析某用户（某会话）的生效配置：

        主智能体：会话覆盖 > 用户主模型偏好 > 全局（active 模型/覆盖层/.env）
        子智能体：用户子模型偏好 > 跟随主智能体
        视觉智能体：用户视觉偏好 > 主模型原生视觉（None）> 注册表视觉兜底
        引用了已删除模型的偏好/覆盖在此静默回退（存储层删除时也会主动清理）。
        """
        settings = self.settings
        prefs = self.store.user_model_prefs(user_id) if user_id else Store._empty_prefs()
        override_id = None
        if session_id:
            record = self.store.session_by_id(session_id)
            override_id = (record or {}).get("model_override_id")
        main_id = override_id or prefs["main_model_id"]
        if (
            main_id is None
            and prefs["sub_model_id"] is None
            and prefs["vision_model_id"] is None
        ):
            return settings

        text_model, text_vision = settings.text_model, settings.text_model_vision
        vision_model = settings.vision_model
        main_row = self.store.model_by_id(main_id) if main_id else None
        if main_row is not None:
            text_model = self._config_from_row(main_row, settings.text_model.proxy)
            text_vision = bool(main_row["vision"])

        sub_model, sub_vision = settings.sub_model, settings.sub_model_vision
        if prefs["sub_model_id"]:
            sub_row = self.store.model_by_id(prefs["sub_model_id"])
            if sub_row is not None:
                sub_model = self._config_from_row(sub_row, settings.text_model.proxy)
                sub_vision = bool(sub_row["vision"])

        if prefs["vision_model_id"]:
            vision_row = self.store.model_by_id(prefs["vision_model_id"])
            if vision_row is not None and vision_row["vision"]:
                vision_model = self._config_from_row(
                    vision_row, settings.text_model.proxy
                )
        elif main_row is not None:
            # 主模型被用户显式更换且未指定视觉模型：按主模型视觉能力重推
            if text_vision:
                vision_model = None
            else:
                fallback = self.store.first_vision_model(
                    prefer_provider=main_row["provider_id"]
                )
                vision_model = (
                    self._config_from_row(fallback, settings.text_model.proxy)
                    if fallback else settings.vision_model
                )

        return replace(
            settings,
            text_model=text_model,
            text_model_vision=text_vision,
            sub_model=sub_model,
            sub_model_vision=sub_vision,
            vision_model=vision_model,
        )

    def reload_config(self) -> dict:
        """重读配置并驱逐全部在线 Session（配置变更即时全员生效）。

        优先级：Provider 注册表激活模型 > app_config 覆盖键 > .env。
        激活模型有视觉能力时不再配 OCR 兜底视觉模型；无视觉时自动选用
        注册表中第一个视觉模型（优先同 Provider）。
        """
        settings = apply_overrides(self._base_settings, self.store.config())
        active = self.store.active_model()
        if active is not None:
            proxy = active["proxy"] or settings.text_model.proxy
            text_model = ModelConfig(
                name=active["model"], api_key=active["api_key"],
                base_url=active["base_url"], proxy=proxy,
            )
            if active["vision"]:
                vision_model = None  # 主模型原生视觉，无需 OCR 兜底
            else:
                fallback = self.store.first_vision_model(
                    prefer_provider=active["provider_id"]
                )
                vision_model = (
                    ModelConfig(
                        name=fallback["model"], api_key=fallback["api_key"],
                        base_url=fallback["base_url"],
                        proxy=fallback["proxy"] or proxy,
                    )
                    if fallback else settings.vision_model
                )
            settings = replace(
                settings, text_model=text_model, vision_model=vision_model,
                text_model_vision=bool(active["vision"]),
            )
        self.settings = settings
        evicted = self.evict_all_sessions()
        return {
            "text_model": settings.text_model.name,
            "text_model_vision": settings.text_model_vision,
            "vision_model": settings.vision_model.name if settings.vision_model else None,
            "evicted_sessions": evicted,
        }

    def admin_sessions(self, user_id: str) -> list[dict]:
        """某用户的 Session 列表，附内存态与上下文占用（未加载的不唤醒）。"""
        result = []
        for row in self.store.sessions(user_id):
            info = {
                "id": row["id"], "title": row["title"],
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "loaded": row["id"] in self.sessions,
            }
            if info["loaded"]:
                stats = self.sessions[row["id"]].agent.context_stats()
                info["context_percent"] = stats["percent"]
                info["message_count"] = stats["message_count"]
            result.append(info)
        return result

    def delete_session_admin(self, session_id: str) -> None:
        """删除 Session：内存驱逐 + DB 记录（FK 级联消息/挂载）+ 磁盘目录。"""
        record = self.store.session_by_id(session_id)
        if record is None:
            raise KeyError(f"未知会话：{session_id}")
        self.evict_session(session_id)
        self.store.delete_session(session_id, record["user_id"])
        shutil.rmtree(
            self.data_root / "users" / record["user_id"] / "sessions" / session_id,
            ignore_errors=True,
        )

    def delete_user_admin(self, user_id: str) -> None:
        """删除用户：驱逐其全部内存态 Session + DB 级联 + 磁盘目录。"""
        for row in self.store.sessions(user_id):
            self.evict_session(row["id"])
        self.store.delete_user(user_id)
        shutil.rmtree(self.data_root / "users" / user_id, ignore_errors=True)

    # ---------- 客户端 Skill 资源 ----------

    @staticmethod
    def _resource_kind(kind: str) -> str:
        if kind != "skills":
            raise ValueError("资源类型只能是 skills")
        return kind

    def client_resources(self, session_id: str, kind: str) -> list[dict]:
        session = self.get_session(session_id)
        kind = self._resource_kind(kind)
        session.mounted_resources = self.store.resource_mounts(session_id)
        directory = session.root / "client" / kind
        resources = []
        for path in sorted(directory.glob("*.md"), key=lambda p: p.name.casefold()):
            if parse_skill_pack_text(path.read_text(encoding="utf-8")) is None:
                continue
            resources.append({
                "kind": kind,
                "name": path.name,
                "mounted": path.name in session.mounted_resources[kind],
                "builtin": path.name in session.builtin_resources[kind],
            })
        return resources

    @staticmethod
    def _validate_resource(content: str) -> None:
        if parse_skill_pack_text(content) is None:
            raise ValueError(
                "Skill 格式无效：文件必须以 --- 开始和结束 front matter，"
                "并包含非空的 name 与 description"
            )

    def client_resource(self, session_id: str, kind: str, name: str) -> tuple[Path, bool]:
        session = self.get_session(session_id)
        kind = self._resource_kind(kind)
        clean_name = Path(name).name
        if clean_name != name or not clean_name.lower().endswith(".md"):
            raise ValueError("资源名必须是单个 .md 文件名")
        path = session.root / "client" / kind / clean_name
        if not path.is_file():
            raise FileNotFoundError(name)
        self._validate_resource(path.read_text(encoding="utf-8"))
        return path, clean_name in session.mounted_resources[kind]

    def create_client_resource(
        self, session_id: str, kind: str, name: str, content: str
    ) -> dict:
        session = self.get_session(session_id)
        kind = self._resource_kind(kind)
        clean_name = Path(name).name.strip()
        if clean_name != name or not clean_name.lower().endswith(".md"):
            raise ValueError("资源名必须是单个 .md 文件名")
        self._validate_resource(content)
        directory = session.root / "client" / kind
        path = directory / clean_name
        if path.exists():
            raise ValueError(f"资源已存在：{clean_name}")
        path.write_text(content, encoding="utf-8")
        return {
            "kind": kind, "name": path.name, "mounted": False,
            "builtin": False, "content": content,
        }

    def generate_client_resource(
        self, session_id: str, kind: str, name: str, description: str
    ) -> dict:
        session = self.get_session(session_id)
        kind = self._resource_kind(kind)
        result = session.session.create_skill(name, description)
        if "生成失败" in result or result.startswith("错误"):
            raise ValueError(result)
        path, mounted = self.client_resource(session_id, kind, f"{name.strip().lower()}.md")
        return {
            "kind": kind, "name": path.name, "mounted": mounted,
            "builtin": False, "content": path.read_text(encoding="utf-8"),
        }

    def delete_client_resource(self, session_id: str, kind: str, name: str) -> None:
        session = self.get_session(session_id)
        path, _ = self.client_resource(session_id, kind, name)
        if path.name in session.builtin_resources[kind]:
            raise ValueError("系统默认资源不能删除")
        session.mounted_resources[kind].discard(path.name)
        self.store.set_resource_mount(session_id, kind, path.name, False)
        self._deactivate_resource(session, path)
        path.unlink()

    def update_client_resource(
        self,
        session_id: str,
        kind: str,
        name: str,
        *,
        content: str | None = None,
        mounted: bool | None = None,
    ) -> dict:
        session = self.get_session(session_id)
        path, current_mounted = self.client_resource(session_id, kind, name)
        if content is not None:
            self._validate_resource(content)
            if current_mounted:
                self._deactivate_resource(session, path)
            path.write_text(content, encoding="utf-8")
        if mounted is not None:
            if mounted:
                session.mounted_resources[kind].add(path.name)
            else:
                session.mounted_resources[kind].discard(path.name)
            self.store.set_resource_mount(session_id, kind, path.name, mounted)
            current_mounted = mounted
        if current_mounted:
            self._activate_resource(session, path)
        elif mounted is False:
            self._deactivate_resource(session, path)
        return {
            "kind": kind,
            "name": path.name,
            "mounted": current_mounted,
            "builtin": path.name in session.builtin_resources[kind],
            "content": path.read_text(encoding="utf-8"),
        }

    def mounted_prompt(self, session: SessionState) -> str:
        sections = []
        for name in sorted(session.mounted_resources["skills"]):
            path = session.root / "client" / "skills" / name
            if path.is_file():
                content = path.read_text(encoding="utf-8")
                parsed = parse_skill_pack_text(content)
                resource_name = parsed.name if parsed is not None else path.stem
                sections.append(
                    f"\n### 用户明确要求加载 Skill：{resource_name}\n"
                    f"执行本轮任务前，必须先调用 use_skill(name={resource_name!r})"
                    f"并严格遵循其指引；不得只在回复中声称已使用。\n\n{content}"
                )
        if not sections:
            return ""
        return (
            "\n\n[系统提供的当前客户端挂载资源]"
            "\n以下 Skill 已由用户明确勾选挂载，本轮必须视为用户明确要求使用。"
            "先判断每个挂载的 Skill 与本轮任务是否相关；明显无关的，点名该 Skill "
            "并请用户先取消挂载，不得静默忽略；若与用户本轮明确要求冲突，"
            "以用户本轮要求为准。\n"
            + "\n".join(sections)
        )

    def _activate_resource(self, session: SessionState, path: Path) -> None:
        pack = parse_skill_pack_text(path.read_text(encoding="utf-8"))
        if pack is not None:
            session.session.use_skill(pack.name)

    def _deactivate_resource(self, session: SessionState, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return
        pack = parse_skill_pack_text(content)
        if pack is not None:
            session.session.unuse_skill(pack.name)

    def _activate_mounted_resources(self, session: SessionState) -> list[dict]:
        activated = []
        missing = []
        for name in sorted(session.mounted_resources["skills"]):
            path = session.root / "client" / "skills" / name
            if not path.is_file():
                missing.append(name)
                continue
            self._activate_resource(session, path)
            parsed = parse_skill_pack_text(path.read_text(encoding="utf-8"))
            activated.append({
                "kind": "skills",
                "name": parsed.name if parsed is not None else path.stem,
                "filename": path.name,
            })
        for name in missing:
            session.mounted_resources["skills"].discard(name)
            self.store.set_resource_mount(session.id, "skills", name, False)
        return activated

    # ---------- 附件与产物 ----------

    def get_run(self, run_id: str) -> Run:
        try:
            return self.run_manager.get(run_id)
        except KeyError as exc:
            raise KeyError(f"未知 Run：{run_id}") from exc

    def save_file(self, session_id: str, filename: str, content: bytes) -> tuple[str, Path]:
        session = self.get_session(session_id)
        file_id = f"file_{uuid.uuid4().hex}"
        clean_name = Path(filename).name.strip()
        if not clean_name:
            raise ValueError("文件名不能为空")
        directory = session.root / "attachments"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / clean_name
        stem, suffix, counter = path.stem, path.suffix, 1
        while path.exists():
            path = directory / f"{stem}_{counter}{suffix}"
            counter += 1
        path.write_bytes(content)
        session.files[file_id] = path
        self.store.add_session_file(session_id, file_id, path)
        return file_id, path

    def attach_workspace_file(self, session_id: str, relative_path: str) -> tuple[str, Path]:
        session = self.get_session(session_id)
        path = self.workspace_file(session_id, relative_path)
        file_id = f"file_{uuid.uuid4().hex}"
        session.files[file_id] = path
        self.store.add_session_file(session_id, file_id, path)
        return file_id, path

    def artifacts(self, session_id: str) -> list[dict]:
        session = self.get_session(session_id)
        result = []
        for path in sorted(session.root.rglob("*")):
            if not path.is_file() or "uploads" in path.parts:
                continue
            relative = path.relative_to(session.root).as_posix()
            artifact_id = hashlib.sha256(relative.encode()).hexdigest()[:20]
            result.append({
                "id": artifact_id,
                "name": relative,
                "kind": _artifact_kind(path),
                "size": path.stat().st_size,
                "download_url": f"/v1/sessions/{session_id}/artifacts/{artifact_id}/content",
                "_path": path,
            })
        return result

    def artifact(self, session_id: str, artifact_id: str) -> tuple[Path, str]:
        for item in self.artifacts(session_id):
            if item["id"] == artifact_id:
                path = item["_path"]
                return path, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        raise KeyError(f"未知产物：{artifact_id}")
