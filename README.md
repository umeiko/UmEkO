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
(`umeko` / `1234`) and generates a deployment `.env` template. Configure model
credentials in the admin Provider / Model page or the shared CLI registry.

```ini
UMEKO_DATA_ROOT=server_data
UMEKO_BASE_PATH=
MODEL_CA_FILE=
```

```bash
umeko-server.exe --port 8000          # WebUI  http://127.0.0.1:8000
                                      # Admin  http://127.0.0.1:9000
```

### From source

```bash
git clone https://github.com/umeiko/UmEkO.git
cd UmEkO
uv sync --extra server                    # or: python -m pip install -e ".[server]"
uv run python -m umeko.server --port 8000 # cloud mode (8000 + admin 9000)
uv run python -m umeko.local  --port 8765 # local mode (no auth)
```

## Startup and deployment

See the [startup and production deployment guide](docs/deployment.md) (Chinese)
for first-run setup, Windows exe usage, config migration, NGINX / ALB prefixes,
model CAs, streaming checks, persistent storage, upgrades and troubleshooting.
The [documentation index](docs/README.md) also links the architecture and local proxy lab.

Use `umeko.server` for shared deployments; `umeko.local` is a personal,
unauthenticated workspace. Configure and activate models in Provider / Model,
persist `UMEKO_DATA_ROOT`, keep the admin port private, and use a single application
process. Deployment changes in `.env` require a restart.

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

Model credentials, names, proxies and vision flags live in the **shared Provider
registry** (`UMEKO_DATA_ROOT/umeko.db`). Web, local mode and CLI share the same
resolver. `.env` contains deployment settings and runtime defaults.

| Key | Description |
|---|---|
| `UMEKO_DATA_ROOT` | persistent data / Provider registry directory (default `server_data`) |
| `UMEKO_BASE_PATH` | public URL prefix, e.g. `/doc-master/consistency/image-text`; empty for root |
| `MODEL_CA_FILE` | additional PEM CA for HTTPS model services; certificate checks remain enabled |
| `UMEKO_ADMIN_USERNAME/PASSWORD` | admin bootstrap (defaults to `umeko`/`1234`) |

Copy `providers.example.json` to `providers.local`, fill it in and import:

```sh
python -m umeko.cli providers import providers.local
python -m umeko.cli providers list
python -m umeko.cli providers use mdl_MODEL_ID
python -m umeko.cli
```

CLI `/reload` reads the current selection and starts a new conversation. Model
changes apply to the next Web run. Set the same data directory on all entry
points; use `--data-root local_data` to retain an existing isolated local install.
Legacy environment model configuration is migrated once without replacing
existing credentials or active selections. Remove old `.env` model entries with
`python -m umeko.cli providers migrate-env --remove` after checking the data directory.
See [deployment and migration](docs/deployment.md) for NGINX prefix stripping,
private model CAs and the [Red Hat Docker verification lab](scripts/proxy_lab/README.md).

## For Developers

```bash
uv sync --extra dev              # test and packaging dependencies
uv run pytest tests/ -q          # project tests
uv run pyinstaller umeko.spec    # build the single-file server exe
```

Domain flows (diagram generation, document QC…) inject via skill packs —
the kernel stays clean.
