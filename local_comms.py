#!/usr/bin/env python3
# pylint: disable=too-many-lines

import logging
import argparse
import signal
import time
import toml

DEFAULT_CFG_FILE = "local_comms.toml"

parser = argparse.ArgumentParser()
parser.add_argument("-V", "--verbosity", default="DEBUG", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-C", "--config", default=DEFAULT_CFG_FILE, help="Name of configuration file to load")

args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

_G_running = True
def exit_clean():
    global _G_running
    _G_running = False

def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    exit_clean()

def load_config(filename):
    cfg = {}
    logging.debug("Loading configuration")
    cfg = toml.load(filename)
    try:
        if cfg['pcm']['gateway']:
            cfg['panel_type'] = 'coordinator'
        else:
            cfg['panel_type'] = 'device'
    except KeyError: # missing gateway is the same as false in this case
        cfg['panel_type'] = 'device'
        cfg['pcm']['gateway'] = False

    return cfg

def coordinator_main(panel_config):
    logging.debug("### Started Coordinator")
    while _G_running:
        time.sleep(0.1)

####################################################################################################
##  MAIN
####################################################################################################

def main():
    logging.debug("*** Starting Local Comms")
    logging.debug(f"args: {args}")

    signal.signal(signal.SIGINT, shutdown_handler)

    panel_config = {}
    panel_config = load_config(args.config)

    logging.debug(f"Configuration loaded: {panel_config}")

    if panel_config['panel_type'] == 'coordinator':
        logging.debug("Designated as the Coordinator panel")
        coordinator_main(panel_config)
    elif panel_config['panel_type'] == 'device':
        logging.debug("Designated as a device panel")
        while _G_running:
            time.sleep(0.1)
    else:
        logging.error(f"Invalid panel type: {panel_config['panel_type']}")

    logging.debug("*** Quitting Local Comms")

if __name__ == "__main__":
    main()
