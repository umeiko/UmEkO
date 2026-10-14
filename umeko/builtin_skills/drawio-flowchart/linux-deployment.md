# Linux 安装、配置与验收

生成可编辑 `.drawio` 只需 Python 3.10+。自动导出 PNG/SVG/PDF 还需 Linux 版
draw.io 桌面程序；服务器没有桌面时使用 Xvfb。包内布局与 XML 内核无需其他图形库。
本说明适用于本 Skill，不改变 UmEkO 平台 Agent 的工具或系统提示词。

## Ubuntu / Debian 原生安装

从 [官方 Release](https://github.com/jgraph/drawio-desktop/releases) 下载与 CPU 架构匹配的
`.deb`；本包 Docker 验收使用 Ubuntu 24.04 / amd64 / draw.io 32.4.1。
下载的安装包放在当前目录，然后运行（文件名替换为实际下载版本）：

```sh
sudo apt-get update
sudo apt-get install -y ./drawio-amd64-32.4.1.deb python3 xvfb xauth fontconfig fonts-noto-cjk libasound2t64
sed -i 's/\r$//' drawio_headless.sh
sudo install -m 0755 drawio_headless.sh /usr/local/bin/drawio-headless
```

上面的 `drawio_headless.sh` 是本包同目录文件；先进入该目录，或将参数替换为它的实际路径。
以上依赖名称对应 Ubuntu 24.04；其他发行版安装提供 `libasound.so.2` 的对应 ALSA 包。
从 Windows 复制 `.sh` 时，先转为 LF 换行再安装，避免 `sh\r` 错误。
RPM 发行版可选官方 `.rpm` 并安装对应的 Xvfb/xauth/字体包；AppImage 需赋予执行权限，
还可能需要发行版的 FUSE 运行支持。当前实测范围为 amd64 的 `.deb` Docker 路径。

用实际运行 UmEkO 服务的普通账户执行，确保该账户的主目录存在且可写，
能够执行 draw.io 并读写本次会话文件。不要仅在管理员自己的账户下测试。

## config.json 怎么填

### 下载并安装原字体

方正兰亭黑简体原文件提供在 [assets Release](https://github.com/umeiko/UmEkO/releases/tag/assets)：
[FZLanTingHeiS-R-GB.ttf](https://github.com/umeiko/UmEkO/releases/download/assets/FZLanTingHeiS-R-GB.ttf)，
[SHA256SUMS.txt](https://github.com/umeiko/UmEkO/releases/download/assets/SHA256SUMS.txt)。
项目维护方确认公司已取得商业授权；字体授权独立于项目代码许可。

```sh
curl --fail --location --retry 3 \
  https://github.com/umeiko/UmEkO/releases/download/assets/FZLanTingHeiS-R-GB.ttf \
  --output /tmp/FZLanTingHeiS-R-GB.ttf
printf '%s  %s\n' \
  '5301bdfe967da491eec7edf29c6ba50cf44f27ad30a0d70a7f74247f3656199b' \
  '/tmp/FZLanTingHeiS-R-GB.ttf' | sha256sum --check -
sudo install -d -m 0755 /usr/local/share/fonts/umeko
sudo install -m 0644 /tmp/FZLanTingHeiS-R-GB.ttf /usr/local/share/fonts/umeko/
sudo fc-cache -f
fc-match -f '%{family}\n' '方正兰亭黑简体'
```

确认返回的 family 包含 `方正兰亭黑简体` 或 `FZLanTingHeiS-R-GB`，然后保留配置中的
`"font_family": "方正兰亭黑简体"`、`"font_size": "10.5"`。Docker 可将上面的字体目录
只读挂载到容器同名路径；宿主已安装字体不代表容器内自动可用。

### 配置字段

`config.json` 是严格 JSON，不支持 `//` 或 `#` 注释；其中 `_help` 是说明字段，脚本忽略它，
可以保留。配置以下字段即可：

| 字段 | 填写方式 |
| --- | --- |
| `drawio_path` | 有桌面的 Linux 可填 `/usr/bin/drawio`；无桌面的服务器填 `/usr/local/bin/drawio-headless`。必须是单个可执行文件的绝对路径，不能填 `xvfb-run -a drawio` 这样的整条命令 |
| `font_family` | 填 Linux 已安装字体的实际 family。保持原风格需安装方正兰亭黑简体；没有该字体时可显式选择 `Noto Sans CJK SC`，图像字体会随之变化 |
| `font_size` | 原风格为字符串 `"10.5"` |
| `scale` | PNG 缩放倍率，默认 `2`，不改变节点的逻辑尺寸 |
| `layout` | 流程图默认宽 172、最小高 28、横向间距 60、纵向间距 28；架构图仍用原 180×60 内核网格 |

无桌面 Linux 的配置示例（其他已有字段和 `_help` 保留）：

```json
{
  "drawio_path": "/usr/local/bin/drawio-headless",
  "font_family": "Noto Sans CJK SC",
  "font_size": "10.5",
  "scale": 2,
  "layout": {"node_width": 172, "node_height": 28, "gap_x": 60, "gap_y": 28}
}
```

也可将 `drawio_path` 留空，设置服务进程的 `DRAWIO_PATH` 或 `UMEKO_DRAWIO_PATH`；
优先顺序为 config → UMEKO_DRAWIO_PATH → DRAWIO_PATH → PATH。
例如 `DRAWIO_PATH=/usr/local/bin/drawio-headless`。
如果安装路径不是 `/usr/bin/drawio`，另设 `DRAWIO_BINARY` 为实际 Linux 可执行文件的绝对路径。
这些变量要进入服务进程／容器的环境，不能只设在另一个终端里。

检查字体：

```sh
fc-match 'Noto Sans CJK SC'
fc-match '方正兰亭黑简体'
```

`fc-match` 可能返回替代字体，请核对输出的 family，不要只看命令退出成功。
用户指定的 `style.md` 中明确填写的字体可覆盖配置；保持原风格时，配置和风格文件都不要
改成替代字体，改为在服务环境安装原字体。包内不分发字体二进制。

## Docker：无需服务器桌面

将 SkillHub 的 `drawio-flowchart.zip` 解压到单独目录，进入包含 `SKILL.md` 的根目录：

```sh
docker build --platform linux/amd64 -f drawio-flowchart/Dockerfile.linux.txt -t umeko-drawio:1.0.1 .
```

Dockerfile 是纯文本 `.txt`，以便随 SkillHub ZIP 上传。镜像安装并校验固定版本官方 `.deb`，
包含 Python、Xvfb、中文开源字体和本技能。运行账户为非 root，容器内通过
`DRAWIO_NO_SANDBOX=1` 显式启用 Electron 的容器兼容参数；原生普通账户运行默认不启用它。
此镜像提供绘图脚本，不运行模型、UmEkO 服务或数据库。

一条命令做无模型验收并自动删除测试容器：

```sh
docker run --init --rm --shm-size=512m --network none --entrypoint python3 umeko-drawio:1.0.1 /skill/drawio-flowchart/linux_smoke.py
```

验收会准备委派任务、用内置 XML 示例生成有判断分支的流程图与分层架构图，
分别导出 `.drawio`、PNG、SVG、PDF，校验结构、字体和文件头，并验证缺少渲染器时确实报错。
测试明确使用已安装的 `Noto Sans CJK SC`，不声称验证了未安装的方正字体。
`--init` 回收渲染器子进程，`--shm-size=512m` 提供足够的 Chromium 共享内存。
Docker 默认 64MB 可能造成连续导出时渲染进程崩溃，表现为 SVG 成功而 PNG/PDF 失败；
不要省略这个参数。Compose 对应设置为 `init: true` 和 `shm_size: 512m`。
若要验收原字体，先将自己有权使用的字体只读挂载到容器的 `/usr/local/share/fonts/`，
再给 `linux_smoke.py` 传 `--font-family '方正兰亭黑简体'`。脚本会检查实际 family，
缺失或回退时失败；不要把字体文件放进公开 Skill ZIP 或镜像构建上下文。

运行真实会话时，把本次任务目录挂载到 `/work`，宿主 Agent 先在目录内生成参数与 XML：

```sh
docker run --init --rm --shm-size=512m --network none --mount "type=bind,src=<本次任务的绝对目录>,dst=/work" \
  umeko-drawio:1.0.1 generate_drawio.py --root /work --args-file /work/workspace/generate-args.json
```

任务目录需允许容器 UID 10001 写入 `generate/`。这是本次会话目录，不要挂载服务数据库、
Provider 配置或整个宿主磁盘。实际生成内容仍由 Agent 写 XML，脚本只校验、布局与导出。

## 常见问题

- `Missing X server` / `cannot open display`：确认 `drawio_path` 指向 headless 包装脚本，且安装了 Xvfb、xauth。
- `Permission denied`：检查包装脚本执行位、会话目录写权限、服务账户的主目录权限。
- `executable is missing`：检查 `DRAWIO_BINARY` 及安装位置；Windows `.exe` 不能直接作为 Linux 渲染器。
- `libasound.so.2` 缺失 / 退出码 127：Ubuntu 24.04 安装 `libasound2t64`；draw.io 的桌面安装包可能没有强制安装这个导出必需的库。
- `Renderer process gone` / `Printing failed`：检查 Docker 共享内存，使用 `--shm-size=512m`。包装脚本关闭硬件加速并使用独立临时配置目录，避免无 GPU 和连续／并发导出的配置冲突。
- 字体或框大小看起来不同：检查实际字体 family 和风格覆盖，安装原字体；不要通过缩小文字或改业务节点掩盖字体缺失。
- 已有配置路径仍是 Windows 路径：先修改 `drawio_path`；非空配置优先于环境变量，旧路径会阻止自动查找。
- PNG/SVG/PDF 导出失败：仍保留有效 `.drawio` 草稿，报告具体失败，不将上次图片作为本次成功结果。

没有新增自动视觉复检；仍由用户要求时做一到两轮。Docker 验收是渲染与结构检查，不调用视觉模型。

## 本次实测记录（2026-10-13）

本地 Docker Desktop 的 Linux / amd64 容器，Ubuntu 24.04、Python 3.12、draw.io 32.4.1，
非 root、关闭网络、`--init --shm-size=512m`：

| 实际识别的字体 | 流程图 PNG/SVG/PDF | 架构图 PNG/SVG/PDF |
| --- | --- | --- |
| Noto Sans CJK SC（镜像自带） | 全部成功 | 全部成功 |
| FZLanTingHeiS-R-GB / 方正兰亭黑简体（本机原字体只读挂载） | 全部成功 | 全部成功 |

同时验证委派规则文件准备、字体落入 XML、PNG/PDF 文件头、SVG 解析及缺少渲染器时的失败返回。
默认 64MB 共享内存下曾出现架构图渲染崩溃及打印失败；512MB 下两套字体连续导出均通过。
不包含模型生成效果评测或自动视觉复检；原字体文件没有进入发行包或构建镜像。
