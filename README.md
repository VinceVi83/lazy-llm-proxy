# LazyLLMProxy

A small FastAPI gateway for local Ollama inference, with optional audio transcription and Linux Wake-on-LAN (WOL) / inactivity-suspend support. The supplied code uses one Ollama backend; it is not a multi-provider router or plugin framework.

## Features

- `GET /health`, `GET /models`, `POST /call-llm`, `POST /transcribe`, `POST /transcribe-and-call`, and `POST /wol-ack`.
- Ollama chat calls use a FIFO queue and run sequentially; callers wait up to 300 seconds.
- Supported options: `temperature`, `top_p`, `top_k`, `num_predict` (or `max_tokens`), and `think`.
- Audio is fetched from `audio_url` and transcribed with `faster-whisper`. Script startup initializes Whisper in CPU mode with French.
- `/health` and `/call-llm` update `/tmp/activity.lock`; `/wol-ack` updates it and starts `auto-suspend.py`.
- `auto-suspend.py` checks every 10 seconds for 120 seconds of inactivity, then schedules suspend 30 seconds later.
- `profile` and `attachments` request fields are accepted but unused. Linux systemd/WOL files are under `linux/`.

## Prerequisites

- Linux is required for systemd, `ethtool`, WOL, and `systemctl suspend`.
- Python 3 and packages in `requirements.txt`.
- Ollama reachable from the gateway host, with model installed `qwen2.5:7b-instruct-q8_0` and `qwen2.5:3b`.

`requirements.txt` lists NVIDIA CUDA/cuDNN packages, although built-in Whisper startup uses CPU. The external configuration manager and the `llm_client` package imported by tests are not declared pip dependencies.

## Installation

Clone with submodules so the configuration dependency is fetched:

```sh
git clone --recurse-submodules <REPOSITORY_URL>
cd lazy-llm-proxy
# If needed:
git submodule update --init --recursive
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

From the repository root, after configuring the external submodule and settings:

```sh
python3 llm-gateway.py
```

## Usage examples

Check health (replace host and port):

```sh
curl -i http://<HOST>:<PORT>/health
```

Send a chat request:

```sh
curl -sS -X POST http://<HOST>:<PORT>/call-llm \
  -H 'Content-Type: application/json' \
  -d '{"system_prompt":"Answer briefly.","prompt":"Hello","model":"qwen2.5:3b","options":{"temperature":0.2}}'
```

The chat response includes a `result` string. List models with `GET /models`. Transcription routes accept JSON with `audio_url`; `audio_language` is accepted, but the engine uses its initialized language. `POST /transcribe-and-call` transcribes and sends the text to Ollama. Audio routes need Whisper initialized: the script entry point does this; ASGI module import alone does not.

`POST /wol-ack` is intended to acknowledge WOL and start the inactivity monitor. The gateway has no authentication; do not expose it to an untrusted network.

## Architecture and flow

```text
RPi: check TCP 9999 --OK--> POST PC:8000/call-llm
       │ failure
       └─ magic packet UDP broadcast ─> PC wakes up
                                      │
                         wakeup-server responds "up" on :9999
                                      │
                         RPi SSH: touch /tmp/wol
                                      │
                         wol-detect observes /tmp/wol
                                      │
                         starts auto-suspend.py
                                      │
                         REST request touches /tmp/activity.lock
                                      │
                 > 600 s without activity --> touch /tmp/inactivity --> systemctl suspend
```

`wol-detect.service` is started on each boot by `multi-user.target`. It waits for the local TCP server, then monitors `/tmp/wol` for 18 seconds. A manual start/wake without this marker therefore does not trigger the monitor.

The `pc-server/` and `rpi-client/` components are not in the uploaded archive and could not be verified against code.

## Repository structure

| Path | Purpose |
|---|---|
| `llm-gateway.py`, `whisper_engine.py` | FastAPI gateway and Whisper engine |
| `auto-suspend.py` | Inactivity monitor and delayed suspend |
| `common/` | Configuration submodule path declared in `.gitmodules` |
| `configure_paths.py` | Replaces markers in selected local files |
| `linux/` | systemd templates and `wol-detect.sh` |
| `tests/` | LLM benchmark and WOL/health checker |
| `requirements.txt` | Declared Python dependencies |

## Credits and license

Project: LazyLLMProxy.
Distributed under the MIT License; see [`LICENSE`](LICENSE). Copyright (c) 2026 Vincent NGUYEN.
