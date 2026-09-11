"""通用会话状态：产物目录、工作文档与 Skill 挂载，供工具处理器读写。

领域会话状态（如"当前图""当前任务"）由各领域项目在自己的 Session 中扩展；
基座 Session 只管：产物落点（write_file 的写入边界）、工作文档（多素材整合的
中间产物）、Skill 的发现/挂载/卸载。
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings
from .skillpacks import SkillPack, get_skill_pack, load_skill_packs

logger = logging.getLogger(__name__)


class Session:
    """一次 Agent 会话的通用状态。

    - output_dir：产物目录，write_file/replace_in_file 的写入边界，路径始终绝对；
    - 工作文档（working_doc.md）：整合多份素材信息的中间产物，避免素材原文
      长期堆在对话上下文里；
    - Skill 挂载：use_skill 读取技能包指引并登记为已启用，供主 Agent 编排使用。
    """

    def __init__(
        self,
        settings: Settings,
        output_dir: str | Path,
        *,
        skill_dir: str | Path | None = None,
    ):
        self._settings = settings
        self._output_dir = Path(output_dir).resolve()
        self._skill_dir = Path(skill_dir).resolve() if skill_dir is not None else None
        self._active_skill_names: set[str] = set()

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
        """工作文档路径：整合素材信息与初步方案的中间产物（markdown）。"""
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

    def list_skill_packs(self) -> str:
        """列出 skills/ 目录下所有技能包（list_skill_packs 工具的 handler）。"""
        packs = load_skill_packs(self._skill_dir)
        if not packs:
            return "skills 目录下没有可用的技能包。"
        return "可用技能包：\n" + "\n".join(
            f"- {p.name}：{p.description}" for p in packs.values()
        )

    def active_skill_packs(self) -> list[SkillPack]:
        """返回当前已启用的合法 Skill。"""
        packs = load_skill_packs(self._skill_dir)
        return [packs[name] for name in sorted(self._active_skill_names) if name in packs]

    def use_skill(self, name: str) -> str:
        """读取技能包完整指引（use_skill 工具的 handler）。"""
        try:
            pack = get_skill_pack(name, self._skill_dir)
        except ValueError as e:
            return f"错误：{e}"
        self._active_skill_names.add(pack.name)
        return (
            f"以下是技能包 {pack.name} 的操作指引，请严格遵照执行：\n\n"
            f"{pack.instructions}"
        )

    def unuse_skill(self, name: str) -> None:
        """卸载此前显式启用的 Skill。"""
        self._active_skill_names.discard(name.strip().lower())

    def create_skill(self, name: str, description: str) -> str:
        """生成并校验一个 Session 目录中的提示词型 Skill。"""
        from .skill_agent import SkillAgent  # 延迟导入：仅用到时加载

        result = SkillAgent(self._settings, self._skill_dir).create(name, description)
        if not result.ok:
            return f"Skill 生成失败：{result.error}"
        return f"Skill 已生成（{result.rounds} 轮通过校验）：{result.path}"
