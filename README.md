# LazyLLMProxy

Minimal proxy for local LLMs (Ollama) that automatically puts machines to sleep when idle and wakes them on demand via Wake-on-LAN because your LLMs deserve naps too.

## How it works
- Centralizes all LLM requests through a single endpoint
- Routes to available backends (Ollama, etc.)
- Detects inactivity and suspends the host machine
- Wakes the machine via WOL when a new request arrives
- Arms the suspend mechanism via `wol-detect.service` on boot/wake using the `/tmp/wol` marker

## Stack
- Python (FastAPI)
- Ollama
- Wake-on-LAN
- systemd


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

## Files

| File | Responsibility |
|---|---|
| `pc-server/wol.service` | Enables WOL wake on `eth0` with `ethtool`. |
| `pc-server/wakeup-server.service` | Maintains TCP availability server. |
| `pc-server/wakeup-server.py` | Responds `up` on TCP port 9999 then closes. |
| `pc-server/wol-detect.service` / `.sh` | Waits for server and detects WOL marker post-boot. |
| `pc-server/auto-suspend.py` | Monitors inactivity and suspends only after WOL detection. |
| `pc-server/llm_gateway.py` | REST API placeholder on port 8000. |
| `rpi-client/llm_gateway_checker.py` | Conditional WOL, waiting, SSH marker and REST call. |
| `rpi-client/test_wol_flow.py` | Manual test with unconditional WOL and timing. |

## Shared markers

| Path | Created by | Read/deleted by | Meaning |
|---|---|---|---|
| `/tmp/wol` | RPi via SSH, after confirmed WOL wakeup | `wol-detect.sh` reads then deletes it | Allows arming auto-suspend for this cycle. |
| `/tmp/activity.lock` | `llm_gateway.py` on each POST `/generate` | `auto-suspend.py` only reads `mtime` | Last LLM activity; never touched by `auto-suspend.py`. |
| `/tmp/inactivity` | `wol-detect.sh` deletes an old marker; `auto-suspend.py` creates it before suspend | `wol-detect.sh` can delete a stale marker | Safeguard indicating an inactivity suspension has been initiated. |

## Parameters

- TCP availability: `9999`.
- REST API: `8000`, route `POST /generate`.
- Inactivity threshold: more than `600 s` (10 minutes).
- Inactivity poll: every `30 s`.
- WOL detection window: `18 s` (within the requested range of 15-20 s).

The following optional service can be created to launch the gateway on boot: `llm-gateway.service`, with `After=network.target`, `Restart=always`, and `ExecStart=/usr/bin/python3 /opt/wol-system/llm_gateway.py`. It is not provided as a mandatory service in order to keep the gateway explicitly optional.


curl -v http://192.168.X.XXX:8000/llm-request
sudo ufw status verbose
sudo ufw status numbered
sudo ufw allow from 192.168.X.XXX/24 to any port 8000 proto tcp
sudo ufw allow from 192.168.X.XXX/24 to any port 9999 proto tcp
mkdir -f /etc/systemd/server
cp /etc/systemd/server/llm-gateway.service
sudo ln -s /etc/systemd/server/llm-gateway.service  /etc/systemd/system/llm-gateway.service
