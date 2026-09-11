"""场景边界配置（L2）：云多租户 vs 本地个人，同一份服务、两种边界。

两类使用场景共享全部层代码，差异收敛为一个 Profile：
- 云（CLOUD_PROFILE）：强制认证、多租户隔离、禁止 run_command、回复脱敏路径；
- 本地 IDE（LOCAL_PROFILE）：隐式单用户、放行 run_command、展示真实本地路径。

新增边界差异时优先在这里加开关，而不是在各交付端写 if。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    auth_enabled: bool = True    # 是否启用注册/登录/租户隔离
    allow_command: bool = False  # 是否放行 run_command 工具（仅本地可信环境）
    mask_paths: bool = True      # 回复中是否把服务端绝对路径改写为 Session 相对路径


CLOUD_PROFILE = Profile(name="cloud")
LOCAL_PROFILE = Profile(
    name="local", auth_enabled=False, allow_command=True, mask_paths=False
)
