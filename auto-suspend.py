#!/usr/bin/env python3
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from common.conf_manager import cfg, setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)

ACTIVITY_PATH = '/tmp/activity.lock'
IDLE_SECONDS = 300
POLL_SECONDS = 10

def is_inactive():
    if not os.path.exists(ACTIVITY_PATH):
        logger.info(f'{ACTIVITY_PATH} missing — exiting')
        sys.exit(0)
    last_activity = os.path.getmtime(ACTIVITY_PATH)
    logger.info(f'last activity at {time.time() - last_activity}')
    return time.time() - last_activity >= IDLE_SECONDS

def arm_suspend():
    log_file = '/tmp/auto-suspend-deferred.log'
    subprocess.Popen(
        ['bash', '-c', f'sleep 30 && sudo systemctl suspend >> {log_file} 2>&1'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info('suspend armed for 30 seconds from now')

def main():
    Path(ACTIVITY_PATH).touch()
    logger.info('monitoring for inactivity')
    while True:
        if is_inactive():
            arm_suspend()
            logger.info('exiting')
            return 0
        else:
            logger.info('activity detected')
        time.sleep(POLL_SECONDS)

if __name__ == '__main__':
    raise SystemExit(main())

