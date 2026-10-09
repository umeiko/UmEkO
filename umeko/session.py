"""通用会话状态：产物目录、工作文档与 Skill 挂载，供工具处理器读写。

领域会话状态（如"当前图""当前任务"）由各领域项目在自己的 Session 中扩展；
基座 Session 只管：产物落点（write_file 的写入边界）、工作文档（多信息源整合的
中间产物）、Skill 的发现/挂载/卸载。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import Settings
from .skillpacks import SkillPack, get_skill_pack, load_skill_packs

logger = logging.getLogger(__name__)


class Session:
    """一次 Agent 会话的通用状态。

    - output_dir：产物目录，write_file/replace_in_file 的写入边界，路径始终绝对；
    - 工作文档（working_doc.md）：整合关键信息的中间产物，避免大段原文
      长期堆在对话上下文里；
    - Skill 挂载：use_skill 读取技能包指引并登记为已启用，供主 Agent 编排使用。
    """

    def __init__(
        self,
        settings: Settings,
        output_dir: str | Path,
        *,
        skill_dir: str | Path | None = None,
        allowed_skill_packs: set[str] | None = None,
    ):
        self._settings = settings
        self._output_dir = Path(output_dir).resolve()
        self._skill_dir = Path(skill_dir).resolve() if skill_dir is not None else None
        self._active_skill_names: set[str] = set()
        # None: CLI / machine Agent catalogues all permitted packs. Web sessions
        # select which packs appear in the catalogue using the existing mount UI.
        self.catalog_skill_names: set[str] | None = None
        self.allowed_skill_packs = allowed_skill_packs

    def authorize_skill_pack(self, pack: str) -> None:
        if self.allowed_skill_packs is not None and pack not in self.allowed_skill_packs:
            raise ValueError("当前智能体未配置该技能包：" + pack)

    def call_skill_pack(self, pack, handler, **kwargs):
        try:
            self.authorize_skill_pack(pack)
        except ValueError as exc:
            return f"错误：{exc}"
        return handler(pack=pack, **kwargs)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def skill_dir(self) -> Path | None:
        """当前会话的 Skill 目录；None 表示使用系统默认目录。"""
        return self._skill_dir

    # ---------- 工作文档 ----------

    @property
    def working_doc_path(self) -> Path:
        """工作文档路径：整合关键信息与中间结论的中间产物（markdown）。"""
        return self._output_dir / "working_doc.md"

    def read_working_doc(self) -> str:
        """read_working_doc 工具的 handler。"""
        if not self.working_doc_path.is_file():
            return "（工作文档还没有内容，可用 write_working_doc 创建）"
        return self.working_doc_path.read_text(encoding="utf-8")

    def write_working_doc(self, content: str) -> str:
        """write_working_doc 工具的 handler：整体覆盖写入（先读后改即可局部修订）。"""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self.working_doc_path.write_text(content, encoding="utf-8")
        return f"工作文档已更新（{len(content)} 字符）：{self.working_doc_path}"

    # ---------- Skill 挂载 ----------

    def skill_catalog_prompt(self) -> str:
        """Request-only metadata; never append pack bodies to user history."""
        packs = load_skill_packs(self._skill_dir)
        entries = [
            {"name": p.name, "description": " ".join(p.description.split())[:600]}
            for p in packs.values()
            if (self.allowed_skill_packs is None or p.name in self.allowed_skill_packs)
            and (self.catalog_skill_names is None or p.name in self.catalog_skill_names)
        ]
        if not entries:
            return ""
        return (
            "[当前可按需使用的技能目录]\n"
            "以下只有技能简介，不代表已加载正文或要求每轮执行。"
            "本轮任务匹配适用场景，或用户明确指定技能时，先调用 use_skill 读取当前完整指引；"
            "同一任务中已有完整指引时无需重复加载。明显无关的技能直接跳过，"
            "无需点名提醒或要求用户取消启用。正文仅在当前任务上下文中保留，"
            "下一轮如需使用必须重新读取，不能凭历史摘要猜测流程。\n"
            + json.dumps(entries, ensure_ascii=False)
        )

    def list_skill_packs(self) -> str:
        """列出 skills/ 目录下所有技能包（list_skill_packs 工具的 handler）。"""
        packs = {
            name: pack for name, pack in load_skill_packs(self._skill_dir).items()
            if self.allowed_skill_packs is None or name in self.allowed_skill_packs
        }
        if not packs:
            return "skills 目录下没有可用的技能包。"
        lines = []
        for p in packs.values():
            members = self._pack_members(p.name)
            lines.append(f"- {p.name}：{p.description}"
                         + (f"（附属文件：{members}）" if members else ""))
        return "可用技能包：\n" + "\n".join(lines)

    def active_skill_packs(self) -> list[SkillPack]:
        """返回当前已启用的合法 Skill。"""
        packs = load_skill_packs(self._skill_dir)
        return [packs[name] for name in sorted(self._active_skill_names) if name in packs]

    def use_skill(self, name: str) -> str:
        """读取技能包完整指引（use_skill 工具的 handler）。

        支持 `包名/附属文件.md` 形式读取包内附属文档（如检查项清单等数据文件）；
        附属文件不要求 front matter，纯内容注入。
        """
        if "/" in name:
            pack_name, _, member = name.partition("/")
            try:
                self.authorize_skill_pack(pack_name.strip().lower())
                pack = get_skill_pack(pack_name, self._skill_dir)
            except ValueError as e:
                return f"错误：{e}"
            from .skills.pack_reader import read_pack_file
            result = read_pack_file(pack.name, member)
            if result.startswith("错误："):
                return result
            self._active_skill_names.add(pack.name)
            return result
        try:
            self.authorize_skill_pack(name.strip().lower())
            pack = get_skill_pack(name, self._skill_dir)
        except ValueError as e:
            return f"错误：{e}"
        self._active_skill_names.add(pack.name)
        members = self._pack_members(pack.name)
        suffix = (f"\n\n（该技能包还包含附属文件：{members}；"
                  f"use_skill <包名>/<文件名> 可读取）") if members else ""
        return (
            f"以下是技能包 {pack.name} 的操作指引，请严格遵照执行：\n\n"
            f"{pack.instructions}{suffix}"
        )

    def _pack_members(self, pack_name: str) -> str:
        """包内附属文件清单（md + py），供 use_skill/list 提示。"""
        if not self._skill_dir:
            return ""
        pack_dir = self._skill_dir / pack_name
        if not pack_dir.is_dir():
            return ""
        members = [p.name for p in sorted(pack_dir.iterdir())
                   if p.suffix in (".md", ".py") and p.is_file()]
        return "、".join(members)

    def unuse_skill(self, name: str) -> None:
        """卸载此前显式启用的 Skill。"""
        self._active_skill_names.discard(name.strip().lower())

    def create_skill(self, name: str, description: str, should_cancel=None) -> str:
        """生成并校验一个 Session 目录中的提示词型 Skill。"""
        if self.allowed_skill_packs is not None:
            return "错误：当前智能体的技能由管理员配置，请在技能管理中维护。"
        from .skill_agent import SkillAgent  # 延迟导入：仅用到时加载

        result = SkillAgent(self._settings, self._skill_dir).create(
            name, description, should_cancel=should_cancel
        )
        if not result.ok:
            return f"Skill 生成失败：{result.error}"
        return f"Skill 已生成（{result.rounds} 轮通过校验）：{result.path}"
