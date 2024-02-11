#!/usr/bin/env python3
# pylint: disable=too-many-lines

import logging
import argparse
import threading
import signal
import time
import secrets
import sys

import toml
import serial

import g3_comms.g3_rx
import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_resp
import g3_comms.g3_consts
from g3_comms import g3_lib

DEFAULT_CFG_FILE = "local_comms.toml"

parser = argparse.ArgumentParser()
parser.add_argument("-V", "--verbosity", default="DEBUG", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-c", "--config", default=DEFAULT_CFG_FILE, help="Name of configuration file to load")

args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

if args.verbosity.upper() == "DEBUG":
    # A couple of internal debug filtering flags exist in g3_comms to hold verbosity down. If we're
    # in DEBUG mode, right now we want to see these messages, so let's enable these flags.
    g3_comms.g3_msgs.print_msg = True
    g3_comms.g3_tx.cmd_verbose = True

# Instantiate a global instance of every response we want to process on Rx
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.HWResetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.UARTBaudSetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.DBGToolResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3GetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3SetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.SWResetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.NetstatusInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootSrvStartResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootSrvJoinInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootDevStartResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootDevPANSortInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootGetPSKInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootSrvSetPSKResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.UDPData())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.UDPDataInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.UDPConnSet())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.UDPConnGet())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.MetaError())

_G_running = True
def exit_clean():
    global _G_running
    _G_running = False

_G_sig_hit = 0
def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    global _G_sig_hit
    exit_clean()
    _G_sig_hit = _G_sig_hit+1
    if _G_sig_hit > 2:
        raise Exception("Force ^C")

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


def init_serial(panel_config):
    port = panel_config['serial']['port']
    ispcm = panel_config['serial']['pcm_pass_through']

    device = serial.Serial(port, baudrate=115200, timeout=0)
    logging.info(f"Opened serial port {device.name}")

    if ispcm:
        logging.warning("Setting up PCM passthrough")
        device.write( "g3_pass_through\r".encode('utf-8'))
        time.sleep(1)

    return device

def init_serial_speed(serial_device, panel_config):
    speed_ok = False
    baudrate = panel_config['serial']['baudrate']
    logging.debug(f'Changing to baud {baudrate}')
    (speed_ok, _) = g3_lib.set_speed(serial_device, baudrate)
    serial_device.baudrate = baudrate
    return speed_ok

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

    # Setup the serial port to our device
    serial_device = init_serial(panel_config)

    # Setup our Rx processing, must be done before we send any messages (like change UART speed)
    rx_protocol = g3_comms.g3_rx.G3Rx(serial_device)
    rx_thread = threading.Thread(target=rx_protocol.run)
    rx_thread.start()

    speed_ok = init_serial_speed(serial_device, panel_config)
    if not speed_ok:
        logging.error("Error when setting up the serial device.")
        exit_clean()
        sys.exit(1)

    if panel_config['panel_type'] == 'coordinator':
        logging.info("Designated as the Coordinator panel")
        coordinator_main(panel_config)
    elif panel_config['panel_type'] == 'device':
        logging.info("Designated as a device panel")
        while _G_running:
            time.sleep(0.1)
    else:
        logging.error(f"Invalid panel type: {panel_config['panel_type']}")

    # Cleanup and quit
    g3_lib.set_speed(serial_device, 115200)

    g3_comms.g3_rx.G3Rx.quit()
    rx_thread.join()

    logging.info("*** Quitting Local Comms")

if __name__ == "__main__":
    main()
