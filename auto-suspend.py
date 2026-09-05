#!/usr/bin/env python3
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

ACTIVITY_PATH = '/tmp/activity.lock'
INACTIVITY_PATH = '/tmp/inactivity'
IDLE_SECONDS = 90
POLL_SECONDS = 30
LOG_PATH = '/home/shireikan/Documents/llm-gateway/debug.log'
WOL_DETECT_PATH = '/home/shireikan/ProjectsLinux/llm-gateway/wol-detect.sh'

def timestamp():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')

def log(message):
    line = f'{timestamp()} auto-suspend: {message}'
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')
    except OSError as exc:
        print(
            f'{timestamp()} auto-suspend: cannot write {LOG_PATH}: {exc}',
            file=sys.stderr,
            flush=True,
        )

def is_inactive():
    try:
        last_activity = os.path.getmtime(ACTIVITY_PATH)
    except FileNotFoundError:
        return False
    except OSError as exc:
        log(f'cannot read {ACTIVITY_PATH}: {exc}')
        return False
    log(f'last activity at {time.time() - last_activity}')
    return time.time() - last_activity >= IDLE_SECONDS

def clean_stale_inactivity_marker():
    try:
        os.unlink(INACTIVITY_PATH)
    except FileNotFoundError:
        log(f'cold-start cleanup: {INACTIVITY_PATH} was not present')
    except OSError as exc:
        log(f'cold-start cleanup failed for {INACTIVITY_PATH}: {exc}')
    else:
        log(f'cold-start cleanup: deleted {INACTIVITY_PATH}')

def mark_inactivity():
    try:
        with open(INACTIVITY_PATH, 'a', encoding='utf-8'):
            pass
    except OSError as exc:
        log(f'failed to create {INACTIVITY_PATH}: {exc}')
        return False
    return True

def arm_suspend():
    subprocess.run(
        [
            'systemd-run',
            '--user',
            '--on-active=30s',
            '--unit=deferred-suspend',
            'systemctl',
            'suspend',
        ],
        check=False,
    )
    log('suspend armed for 30 seconds from now')

def handoff_to_wol_detector():
    output = open(os.devnull, 'w', encoding='utf-8')
    try:
        subprocess.Popen(
            ['nohup', WOL_DETECT_PATH],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        output.close()
    log(f'handed off to {WOL_DETECT_PATH} in the background')

def main():
    clean_stale_inactivity_marker()
    Path(ACTIVITY_PATH).touch()
    log('monitoring for inactivity')

    while True:
        if is_inactive():
            log('inactivity detected')
            if not mark_inactivity():
                return 1
            arm_suspend()
            log('sleep started for 120 seconds')
            time.sleep(120)
            handoff_to_wol_detector()
            log('exiting after WOL handoff')
            return 0
        else:
            log('activity detected')
        time.sleep(POLL_SECONDS)

if __name__ == '__main__':
    raise SystemExit(main())

