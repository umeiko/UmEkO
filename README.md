<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/icon-light.svg">
  <img src="docs/assets/brand/icon.svg" alt="UMEKO logo" width="96" height="96">
</picture>

# UMEKO

**Unified Multi-agent Execution Kernel & Orchestrator**

[![CI](https://github.com/umeiko/UmEkO/actions/workflows/ci.yml/badge.svg)](https://github.com/umeiko/UmEkO/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/umeiko/UmEkO?include_prereleases)](https://github.com/umeiko/UmEkO/releases)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)

**English** | [简体中文](READMECN.md)

</div>

---

UMEKO is a Python agent service for working with files. It provides a web interface,
a CLI and an HTTP API, with model configuration, user management and skill packs.

**[Documentation site](https://umeiko.github.io/UmEkO/)** · [Architecture](https://umeiko.github.io/UmEkO/architecture/) · [API reference](https://umeiko.github.io/UmEkO/api/)

| ![](docs/screenshots/workspace.png) | ![](docs/screenshots/admin.png) |
|:---:|:---:|
| Workspace and tool calls | Admin console |

## Features

- **Web interface**: streaming chat, tool details and call history, file filtering and previews, with seven interface languages.
- **Agent delegation**: the main agent delegates file tasks through `delegate_task`. Sub-agent context is released after it returns a result.
- **Image analysis**: `image_reasoning` supports image analysis and text extraction, with progress displayed in the tool details.
- **Model configuration**: multiple providers and models, vision flags, JSON import and per-model concurrency limits.
- **Administration**: a separate port for users, sessions, models, skill packs, service credentials and resource monitoring.
- **Machine integrations**: MCP Streamable HTTP and A2A 1.0 JSON-RPC, with scoped service credentials, durable tasks, bounded queues and automatic expiry.
- **Multiple agents**: configure separate names, instructions, models and skill selections in the admin console; publish each under `/agent/{slug}` with its own Card, MCP, A2A and REST task endpoints, sharing one runtime and model queues.
- **File operations**: reading, searching, editing and writing within session directories, archive extraction with 7-Zip and drag-and-drop uploads.
- **History**: messages, tool calls and attachment mappings are stored in SQLite.
- **Run control**: SSE output and cooperative cancellation.

## Quick start

### Download exe (Windows)

Download `umeko-server.exe` from [Releases](https://github.com/umeiko/UmEkO/releases),
place it in a directory and run it.

On first startup, the server initializes the admin account and generates a
deployment `.env` template. Use your configured admin credentials to sign in, then
configure and activate a model in the admin
Provider / Model page or through the CLI before starting a conversation.

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

## Architecture

| Layer | Responsibility | Source |
| --- | --- | --- |
| L3: interfaces | Web, administration, local workspace and CLI | `server/`, `local.py`, `cli.py` |
| L2: host services | Sessions, storage, profiles and configuration | `host/` |
| L1: runtime | Agents, Run lifecycle and events | `agent.py`, `sub_agent.py`, `runner.py`, `events.py` |
| L0: core | Model clients, tools, skills and cancellation | `llm/`, `skills/`, `cancellation.py` |

Web and CLI use the event definitions in `events.py` to display execution progress.
See the [architecture documentation](https://umeiko.github.io/UmEkO/architecture/)
for current implementation details. See [machine tasks](https://umeiko.github.io/UmEkO/api/machine-tasks/),
[MCP](https://umeiko.github.io/UmEkO/api/mcp/), [A2A](https://umeiko.github.io/UmEkO/api/a2a/)
and [resource monitoring](https://umeiko.github.io/UmEkO/api/monitoring/) for integration instructions.

## Skill packs

A skill pack contains a Markdown prompt and optional supporting documents and
Python scripts. Agents read supporting files with `read_pack_file` and execute
scripts with `run_skill_script`, which supports timeouts and cancellation.

Administrators edit, distribute, enable and disable packs in the admin console.
Users mount packs in individual sessions.

## Configuration

Model credentials, names, proxies, vision flags and concurrency limits are stored
in the Provider registry (`UMEKO_DATA_ROOT/umeko.db`). Web, local mode and CLI share
the same resolver. `.env` contains deployment settings and runtime defaults.

| Key | Description |
|---|---|
| `UMEKO_DATA_ROOT` | persistent data / Provider registry directory (default `server_data`) |
| `UMEKO_BASE_PATH` | public URL prefix, e.g. `/doc-master/consistency/image-text`; empty for root |
| `MODEL_CA_FILE` | additional PEM CA for HTTPS model services; certificate checks remain enabled |
| `UMEKO_ADMIN_USERNAME/PASSWORD` | credentials for initializing the first admin account |

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

## Development

```bash
uv sync --extra dev              # test and packaging dependencies
uv run pytest tests/ -q          # project tests
uv run pyinstaller umeko.spec    # build the single-file server exe
```

Add domain workflows, such as diagram generation or document quality checks,
through skill packs.
