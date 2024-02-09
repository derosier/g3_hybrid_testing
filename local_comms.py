#!/usr/bin/env python3
# pylint: disable=too-many-lines

import logging
import argparse
import signal
import time
import secrets

import toml

import g3_comms.g3_tx
import g3_comms.g3_msgs
import g3_comms.g3_consts

DEFAULT_CFG_FILE = "local_comms.toml"

parser = argparse.ArgumentParser()
parser.add_argument("-V", "--verbosity", default="DEBUG", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-C", "--config", default=DEFAULT_CFG_FILE, help="Name of configuration file to load")

args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

if args.verbosity.upper() == "DEBUG":
    # A couple of internal debug filtering flags exist in g3_comms to hold verbosity down. If we're
    # in DEBUG mode, right now we want to see these messages, so let's enable these flags.
    g3_comms.g3_msgs.print_msg = True
    g3_comms.g3_tx.cmd_verbose = True

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

def save_config(filename, cfg):
    # We store the key as pure hex text and then restore that to a bytes object. Otherwise
    # we get a weird array that we don't want.
    cfg['local comms']['session_key'] = cfg['local comms']['session_key'].hex()
    with open(filename, 'w', encoding="utf-8") as f:
        toml.dump(cfg, f)

def lcn_parmeters_init(panel_config):
    lcn_cfg = {}
    try:
        # load our last saved state if we can
        lcn_cfg = panel_config['local comms']
        lcn_cfg['session_key'] = bytes.fromhex(lcn_cfg['session_key'])
    except KeyError:
        # if we don't have a last saved state, then we need to initialize it
        lcn_cfg['key_time'] = time.time()
        lcn_cfg['session_key'] = secrets.token_bytes(g3_comms.g3_consts.G3_PSK_LEN)

    return lcn_cfg

def coordinator_main(panel_config):
    logging.info("### Started Coordinator")

    # First we need to set this up.  Coordinators always start in LCN mode. But if we've never
    # started before, we'll need to do some setup.
    lcn_config = lcn_parmeters_init(panel_config)

    while _G_running:
        time.sleep(0.1)

    panel_config['local comms'] = lcn_config
    save_config('c_session.toml', panel_config)

####################################################################################################
##  MAIN
####################################################################################################

def main():
    logging.info("*** Starting Local Comms")
    logging.debug(f"args: {args}")

    signal.signal(signal.SIGINT, shutdown_handler)

    panel_config = {}
    panel_config = load_config(args.config)

    logging.info(f"Configuration loaded: {panel_config}")

    if panel_config['panel_type'] == 'coordinator':
        logging.info("Designated as the Coordinator panel")
        coordinator_main(panel_config)
    elif panel_config['panel_type'] == 'device':
        logging.info("Designated as a device panel")
        while _G_running:
            time.sleep(0.1)
    else:
        logging.error(f"Invalid panel type: {panel_config['panel_type']}")

    logging.info("*** Quitting Local Comms")

if __name__ == "__main__":
    main()
