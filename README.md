<div align="center">

# UMEKO

**Unified Multi-agent Execution Kernel & Orchestrator**

[![CI](https://github.com/umeiko/UmEkO/actions/workflows/ci.yml/badge.svg)](https://github.com/umeiko/UmEkO/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/umeiko/UmEkO?include_prereleases)](https://github.com/umeiko/UmEkO/releases)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**English** | [简体中文](READMECN.md)

</div>

---

A domain-agnostic **general-purpose Agent platform**: chat with files, delegate sub-tasks, manage models and users — deployable as a cloud service or a local single-exe server.

| ![](docs/screenshots/workspace.png) | ![](docs/screenshots/admin.png) |
|:---:|:---:|
| WebUI — Workspace & tool calls | Admin console |

## Highlights ✨

- 🖥 **WebUI** — streaming chat, tool-call inspector (live streaming output + image thumbnails), file tree with filter, workspace preview, 7 languages
- 🤖 **Two-tier agents** — main agent + sandboxed file sub-agent (`delegate_task`); sub-agent context is destroyed after reporting
- 👁 **Vision pipeline** — `image_reasoning` analyzes images with any prompt (OCR included) and streams output into the tool card in real time
- 🗂 **Provider registry** — multi-provider / multi-model management, vision flags, JSON import, one-click activation with instant hot-reload
- 👥 **Admin console** — user & session management, skill-pack authoring (prompts + sandboxed Python scripts), config hot-reload with instant eviction
- 📦 **File ops** — sandboxed read/grep/edit/write, archive extraction (7-Zip), directory-tree guards, drag-drop uploads
- 💾 **Durable history** — tool calls & attachment mappings persisted in SQLite
- ⚡ **Cancellation & streaming** — cooperative cancel, SSE everywhere

## Quick Start 🚀

### Download exe (Windows)

Grab `umeko-server.exe` from [Releases](https://github.com/umeiko/UmEkO/releases), drop it in an empty folder and double-click.

Zero-config first run: the server boots immediately with a default admin account
(`umeko` / `1234`) and generates a `.env` template — configure providers either
by editing `.env` or entirely from the admin console.

```ini
TEXT_MODEL_NAME=your-model
TEXT_MODEL_BASE_URL=https://api.example.com/v1
TEXT_MODEL_API_KEY=sk-xxx
# Optional — enables image_reasoning:
# VISION_MODEL_NAME=your-vision-model
# VISION_MODEL_API_KEY=sk-xxx
# VISION_MODEL_BASE_URL=https://api.example.com/v1
```

```bash
umeko-server.exe --port 8000          # WebUI  http://127.0.0.1:8000
                                      # Admin  http://127.0.0.1:9000
```

### From source

```bash
git clone https://github.com/umeiko/UmEkO.git
cd UmEkO
uv sync                                   # or: pip install -e ".[dev]"
uv run python -m umeko.server --port 8000 # cloud mode (8000 + admin 9000)
uv run python -m umeko.local  --port 8765 # local mode (no auth)
```

## Architecture 🏗

```
┌────────────────────── Delivery (L3) ────────────────────────┐
│  server/ (FastAPI + WebUI + admin)  local.py  cli.py (REPL) │
├────────────────────── Host services (L2) ───────────────────┤
│  service.py (sessions/runs/config)  storage.py  profile.py  │
├────────────────────── Runtime (L1) ─────────────────────────┤
│  agent.py  sub_agent.py  runner.py (Run lifecycle)  events  │
├────────────────────── Kernel (L0) ──────────────────────────┤
│  llm/ (OpenAI-compat, streaming)  skills/  cancellation.py  │
└──────────────────────────────────────────────────────────────┘
```

One event channel (`events.py`) feeds every delivery surface — Web, CLI and
future IDE clients see the same stream. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Skill Packs

A skill pack is a folder with a same-named `.md` (the prompt) plus optional
member files — data docs (check-item catalogs, read on demand via
`read_pack_file`) and sandboxed Python scripts (executed deterministically via
`run_skill_script` with timeout & cancellation). Admins author, dispatch,
enable/disable and version-check packs from the admin console; users mount them
per session with one click.

## Configuration

Priority: **provider registry (admin console) > DB overrides > .env**

| Key | Description |
|---|---|
| `TEXT_MODEL_NAME/BASE_URL/API_KEY` | main model (required unless configured in admin console) |
| `VISION_MODEL_NAME/BASE_URL/API_KEY` | vision model (enables `image_reasoning`) |
| `MODEL_PROXY` | proxy for the model gateway |
| `UMEKO_ADMIN_USERNAME/PASSWORD` | admin bootstrap (defaults to `umeko`/`1234`) |

## For Developers

```bash
uv run pytest                    # tests
uv run pyinstaller umeko.spec    # build the single-file server exe
```

Domain flows (diagram generation, document QC…) inject via skill packs —
the kernel stays clean.
