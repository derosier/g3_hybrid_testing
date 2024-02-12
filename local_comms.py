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
import g3_comms.g3_connman
import g3_comms.g3_consts
from g3_comms import g3_lib
import local_comms_rx_handler

LC_COORD_SA = 1000
LC_CONTROL_PORT = 900
LC_DATA_PORT = 901

START_TIMEOUT = 60.0

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
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.NVMResp())
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

connman = g3_comms.g3_connman.ConnMan(g3_comms.g3_msgs.msg_decode_list)

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
        raise Exception("Force ^C") # pylint: disable=broad-exception-raised

####################################################################################################
##  Message processing
####################################################################################################

# The callback is called from the received message hook and because of the way it is done
# the first parameter will be the actual Resp object. We can ignore this. The next arguments:
#    _ - This is the context set when the hook is set here we can ignore it
#    name - The name of the message rx, which would be G3Resp.g3_name
#    fields - the parsed fields from the message

# Reply G3BOOT-SRV-START: {'error_code': 0, 'status': 'G3_SUCCESS'}
# Used when we boot into coordinator mode. Allows us to pause after our swreset and know we're
# running.
_G_wait_srv_start = threading.Event()
_G_returned_srv_start = {}
def net_start_callback(_, name, fields):
    global _G_returned_srv_start
    logging.info(f"net_start_callback({_}, {name}, {fields})")
    _G_returned_srv_start = fields
    _G_wait_srv_start.set()

# Happens when a device joins the PAN
# Reply G3BOOT-SRV-JOIN: {'error_code': 0, 'e_addr': 12336387418442792960, 'short_id': 1}
def join_callback(_, name, fields):
    logging.debug(f"join_callback({_}, {name}, {fields})")
    print(f"Node with address {fields['short_id']} joined the network.")

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
        lcn_cfg['key_created'] = time.time()
        lcn_cfg['session_key'] = secrets.token_bytes(g3_comms.g3_consts.G3_PSK_LEN)
        lcn_cfg['lcn_pan'] = int.from_bytes(secrets.token_bytes(2), byteorder='big')

    return lcn_cfg

def coordinator_setup_lcn(serial_device, lcn_cfg):
    logging.info(f"coordinator_setup_lcn({lcn_cfg})")

    g3_lib.set_nvm_panid(serial_device, lcn_cfg['lcn_pan'])
    g3_lib.set_nvm_shortaddr(serial_device, LC_COORD_SA)
    g3_lib.set_nvm_psk(serial_device, 0, lcn_cfg['session_key'])

def coordinator_main(panel_config, serial_device):
    logging.info("### Started Coordinator")

    # 1. Setup hooks
    g3_lib.set_hook(net_start_callback, ['G3BOOT-SRV-START'])
    g3_lib.set_hook(join_callback, ['G3BOOT-SRV-JOIN'])
    g3_lib.set_hook(local_comms_rx_handler.data_rx_callback, ['G3UDP-DATA.Ind'])
    g3_lib.set_hook(local_comms_rx_handler.data_rx_callback, ['META-ERROR'])

    # Coordinators always start in LCN mode. But if we've never started before, we'll need to do
    # some setup. This function will take what the config file gave us and check if we've got
    # session information. If no parameters, we'll create them.
    lcn_config = lcn_parmeters_init(panel_config)
    lcn_config['sa'] = LC_COORD_SA

    # Start our LCN
    coordinator_setup_lcn(serial_device, lcn_config)
    (sw_reset, status) = g3_lib.sw_reset(serial_device, 'coordinator', 'ipv6_boot')
    if not sw_reset:
        logging.error(f"Unable to perform a SWRESET: {status}")

    # Wait until we're reset
    # Indicator = Reply G3BOOT-SRV-START: {'error_code': 0, 'status': 'G3_SUCCESS'}
    _G_wait_srv_start.clear()
    if not _G_wait_srv_start.wait(START_TIMEOUT):
        logging.error("Never received G3BOOT-SRV-START, timeout.")
    if not g3_lib.check_status_ok(_G_returned_srv_start):
        logging.error("G3BOOT-SRV-START unsuccessful.")
        return

    # Setup connections
    connman.init_setup(serial_device)
    connman.print_info()
    _ = connman.new_conn(serial_device, -1, 0, LC_CONTROL_PORT)
    _ = connman.new_conn(serial_device, -1, 0, LC_DATA_PORT)
    connman.print_conn_list()

    # Start Rx handler thread
    rx_handler = local_comms_rx_handler.LocalComms_Rx_Handler(serial_device)
    rx_handler_thread = threading.Thread(target=rx_handler.run)
    rx_handler_thread.start()

    # Start Tx thread

    # Now, in our "main" thread, handle the CLI
    while _G_running:
        time.sleep(1.0)

    # Kill our threads
    local_comms_rx_handler.LocalComms_Rx_Handler.quit()
    rx_handler_thread.join()

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

    if not g3_lib.hw_reset(serial_device):
        logging.error("Unable to perform a HWRESET")
        exit_clean()
        g3_comms.g3_rx.G3Rx.quit()
        rx_thread.join()
        sys.exit(1)

    speed_ok = init_serial_speed(serial_device, panel_config)
    if not speed_ok:
        logging.error("Error when setting up the serial device.")
        exit_clean()
        g3_comms.g3_rx.G3Rx.quit()
        rx_thread.join()
        sys.exit(1)

    if panel_config['panel_type'] == 'coordinator':
        logging.info("Designated as the Coordinator panel")
        coordinator_main(panel_config, serial_device)
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
