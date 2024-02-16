#!/usr/bin/env python3
# pylint: disable=too-many-lines

import logging
import argparse
import threading
import signal
import time
import secrets
import sys
import hashlib
import queue

import toml
import serial

import iperf_msgs

import g3_comms.g3_rx
import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_resp
import g3_comms.g3_connman
import g3_comms.g3_consts
from g3_comms import g3_lib
import local_comms_rx_handler
import local_comms_cli

from local_comms_consts import * # pylint: disable=wildcard-import

runinfo = {
    'lcn_cfg': {},
    'pairn_cfg': {},
    'net_cfg': {},
    'net_mode': 'none',
    'panel_config': {},
}

parser = argparse.ArgumentParser()
parser.add_argument("-V", "--verbosity", default="INFO", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
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
    local_comms_cli.cli_shutdown()

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
_G_wait_net_start = threading.Event()
_G_returned_srv_start = {}
def net_start_callback(_, name, fields):
    global _G_returned_srv_start
    logging.info(f"net_start_callback({_}, {name}, {fields})")
    _G_returned_srv_start = fields
    _G_wait_net_start.set()

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
        lcn_cfg['pan'] = int.from_bytes(secrets.token_bytes(2), byteorder='big') % LC_MAX_LCN_PANID
        while lcn_cfg['pan'] <= LC_MAX_PAIR_PANID:
            lcn_cfg['pan'] = int.from_bytes(secrets.token_bytes(2), byteorder='big') % LC_MAX_LCN_PANID
        lcn_cfg['devicetype'] = 'coordinator'

    if 'devicetype' not in lcn_cfg.keys():
        print('devicetype not found')
        lcn_cfg['devicetype'] = panel_config['panel_type']
    else:
        print(f'lcn_cfg["devicetype"]: {lcn_cfg["devicetype"]}')
    return lcn_cfg

def get_lcn_cfg(panel_config):
    lcn_cfg = None
    if 'local comms' in panel_config:
        if 'pan' in panel_config['local comms']:
            try:
                lcn_cfg = panel_config['local comms']
                lcn_cfg['session_key'] = bytes.fromhex(lcn_cfg['session_key'])
                lcn_cfg['sa'] = -1 # if this got saved, ignore it
                lcn_cfg['devicetype'] = panel_config['panel_type']
            except KeyError:
                lcn_cfg = None

    return lcn_cfg

def create_pair_network_cfg(uuid):
    logging.info(f"create_pair_network_cfg({uuid})")
    pair_cfg = {}

    # For a network config, we need three things:
    #     * PANID
    #     * Short ID (for coordinator)
    #     * PSK
    #
    # The PANID and PSK can be derived from the panel identification information.
    # We'll use a sha256 hash on the UUID (encoded per hashlib's requirements).
    # From this, the first 16 bytes will be our PSK, and the last two bytes we'll turn
    # into an integer for the PANID. We will ensure our PANID is < 5000, because PANIDs >= 5000
    # are defined for our LCNs.
    # The Coordinator short ID will be a constant.
    id_hash = hashlib.sha256(uuid.encode()).digest()
    pair_cfg['session_key'] = id_hash[:16]
    pair_cfg['pan'] = int.from_bytes(id_hash[30:], byteorder='big') % LC_MAX_PAIR_PANID
    if pair_cfg['pan'] == 0:
        pair_cfg['pan'] = 1
    pair_cfg['sa'] = LC_PAIR_SA

    return pair_cfg

def setup_network(serial_device, net_cfg):
    logging.info(f"setup_network({net_cfg})")

    g3_lib.set_nvm_panid(serial_device, net_cfg['pan'])
    if net_cfg['sa'] >= 0:
        g3_lib.set_nvm_shortaddr(serial_device, net_cfg['sa'])
    g3_lib.set_nvm_psk(serial_device, 0, net_cfg['session_key'])

def start_network(serial_device, net_cfg):
    logging.info(f"Starting network ({net_cfg})")
    # Start our network
    setup_network(serial_device, net_cfg)
    (sw_reset, status) = g3_lib.sw_reset(serial_device, net_cfg['devicetype'], 'ipv6_boot')
    if not sw_reset:
        logging.error(f"Unable to perform a SWRESET: {status}")

    # Wait until we're reset
    # Indicator = Reply G3BOOT-SRV-START: {'error_code': 0, 'status': 'G3_SUCCESS'}
    _G_wait_net_start.clear()
    if not _G_wait_net_start.wait(START_TIMEOUT):
        logging.error("Never received network start, timeout.")
    if not g3_lib.check_status_ok(_G_returned_srv_start):
        logging.error("Network start unsuccessful.")
        return

    # Setup connections
    connman.req_info(serial_device)  # this reloads the cached info so it isn't stale
    connman.print_info()
    _ = connman.new_conn(serial_device, -1, 0, LC_CONTROL_PORT)
    _ = connman.new_conn(serial_device, -1, 0, LC_DATA_PORT)
    connman.print_conn_list()

    # Accept Rx and Tx
    local_comms_rx_handler.LocalComms_Rx_Handler.HandleRX = True

def stop_network(serial_device):
    local_comms_rx_handler.LocalComms_Rx_Handler.HandleRX = False
    connman.clear_connections(serial_device)

def do_status(serial_device, state):
    print(f"Current running state: {state}")
    panid = g3_lib.get_panid(serial_device)
    sa = g3_lib.get_shortid(serial_device)
    print(f"PAN ID: {panid}")
    print(f"Short address: {sa}")

    connman.print_conn_list()
    print(f"{runinfo}")

def do_txtest(serial_device, sa_dest, numpackets):
    logging.debug(f"do_txtest({sa_dest}, {numpackets})")
    # Setup connection to sa_dest
    connid = connman.new_conn(serial_device, sa_dest, LC_CONTROL_PORT, LC_CONTROL_PORT)

    for i in range(0, numpackets):
        # Encode a g3_iperf ping packet
        msg_buffer = iperf_msgs.MSG_DATA[:400]
        ping_packet = iperf_msgs.encode_ping_packet(connman.my_short_address, i, msg_buffer)

        # Send the packet
        (send_ok, status) = g3_lib.send_udp(serial_device, connid, i, ping_packet)
        if not send_ok:
            logging.error(f"Error sending ping: {status}")

    # Cleanup connection
    connman.del_connection(serial_device, connid)

def coordinator_main(panel_config, serial_device):
    logging.info("### Started Coordinator")

    state = 'start'
    mailbox = queue.Queue()

    # 1. Setup hooks
    g3_lib.set_hook(net_start_callback, ['G3BOOT-SRV-START', 'G3BOOT-DEV-START'])
    g3_lib.set_hook(join_callback, ['G3BOOT-SRV-JOIN'])
    g3_lib.set_hook(local_comms_rx_handler.data_rx_callback, ['G3UDP-DATA.Ind'])
    g3_lib.set_hook(local_comms_rx_handler.data_rx_callback, ['META-ERROR'])

    # Coordinators always start in LCN mode. But if we've never started before, we'll need to do
    # some setup. This function will take what the config file gave us and check if we've got
    # session information. If no parameters, we'll create them.
    lcn_cfg = lcn_parmeters_init(panel_config)
    lcn_cfg['sa'] = LC_COORD_SA
    runinfo['lcn_cfg'] = lcn_cfg
    runinfo['net_mode'] = 'lcn'
    net_cfg = lcn_cfg
    runinfo['net_cfg'] = net_cfg

    start_network(serial_device, net_cfg)
    state = 'lcn'

    # Start Rx handler thread
    rx_handler = local_comms_rx_handler.LocalComms_Rx_Handler(serial_device)
    rx_handler_thread = threading.Thread(target=rx_handler.run)
    rx_handler_thread.start()

    # Start Tx thread

    # Start cli thread
    cli_handler_thread = threading.Thread(target=local_comms_cli.cli_main, args=[mailbox])
    cli_handler_thread.start()

    while state != 'quit':
        if not local_comms_cli.cli_is_running():
            state = 'quit'
        try:
            message = mailbox.get(block=True, timeout=1.0)
        except queue.Empty:
            continue
        logging.debug(f"Processing command {message['type']}")
        if message['type'] == 'hello':
            print("Got 'hello' in coordinator thread.")
        elif message['type'] == 'status':
            do_status(serial_device, state)
        elif message['type'] == 'txtest':
            do_txtest(serial_device, message['dest'], message['count'])
        elif message['type'] == 'quit':
            state = 'quit'
        elif message['type'] == 'pair':
            stop_network(serial_device)
            net_cfg = create_pair_network_cfg(message['uuid'])
            net_cfg['devicetype'] = 'device' # create_pair_network_cfg doesn't set this
            runinfo['net_mode'] = 'pairing'
            runinfo['net_cfg'] = net_cfg
            start_network(serial_device, net_cfg)
            state = 'pairing'
        else:
            print(f"Unknown message {message['type']}")

    # Kill our threads
    cli_handler_thread.join()
    local_comms_rx_handler.LocalComms_Rx_Handler.quit()
    rx_handler_thread.join()

    panel_config['local comms'] = lcn_cfg
    save_config('c_session.toml', panel_config)


def device_main(panel_config, serial_device):
    logging.info("### Started Device")

    state = 'starting'
    mailbox = queue.Queue()

    # 1. Setup hooks
    g3_lib.set_hook(net_start_callback, ['G3BOOT-SRV-START', 'G3BOOT-DEV-START'])
    g3_lib.set_hook(join_callback, ['G3BOOT-SRV-JOIN'])
    g3_lib.set_hook(local_comms_rx_handler.data_rx_callback, ['G3UDP-DATA.Ind'])
    g3_lib.set_hook(local_comms_rx_handler.data_rx_callback, ['META-ERROR'])

    # If this Device has run an LCN before, then we'll have configuration available.
    lcn_cfg = get_lcn_cfg(panel_config)
    runinfo['lcn_cfg'] = lcn_cfg
    if lcn_cfg:
        # start an LCN network
        net_cfg = lcn_cfg
        runinfo['net_mode'] = 'lcn'
        state = 'lcn'
    else:
        net_cfg = create_pair_network_cfg(panel_config['pcm']['uuid'])
        net_cfg['devicetype'] = 'coordinator' # create_pair_network_cfg doesn't set this
        runinfo['net_mode'] = 'pairing'
        state = 'pairing'

    runinfo['net_cfg'] = net_cfg

    start_network(serial_device, net_cfg)

    # Start Rx handler thread
    rx_handler = local_comms_rx_handler.LocalComms_Rx_Handler(serial_device)
    rx_handler_thread = threading.Thread(target=rx_handler.run)
    rx_handler_thread.start()

    # Start Tx thread

    # Start cli thread
    cli_handler_thread = threading.Thread(target=local_comms_cli.cli_main, args=[mailbox])
    cli_handler_thread.start()

    while state != 'quit':
        if not local_comms_cli.cli_is_running():
            state = 'quit'
        try:
            message = mailbox.get(block=True, timeout=1.0)
        except queue.Empty:
            continue
        logging.debug(f"Processing command {message['type']}")
        if message['type'] == 'hello':
            print("Got 'hello' in coordinator thread.")
        elif message['type'] == 'status':
            do_status(serial_device, state)
        elif message['type'] == 'txtest':
            do_txtest(serial_device, message['dest'], message['count'])
        elif message['type'] == 'quit':
            state = 'quit'
        else:
            print(f"Unsupported message {message['type']}")

    # Kill our threads
    cli_handler_thread.join()
    local_comms_rx_handler.LocalComms_Rx_Handler.quit()
    rx_handler_thread.join()

    if lcn_cfg:
        panel_config['local comms'] = lcn_cfg
    save_config('session.toml', panel_config)

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
    runinfo['panel_config'] = panel_config

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

    connman.init_setup(serial_device)
    connman.clear_connections(serial_device)

    if panel_config['panel_type'] == 'coordinator':
        logging.info("Designated as the Coordinator panel")
        coordinator_main(panel_config, serial_device)
    elif panel_config['panel_type'] == 'device':
        logging.info("Designated as a device panel")
        device_main(panel_config, serial_device)
    else:
        logging.error(f"Invalid panel type: {panel_config['panel_type']}")

    # Cleanup and quit
    g3_lib.set_speed(serial_device, 115200)

    g3_comms.g3_rx.G3Rx.quit()
    rx_thread.join()

    logging.info("*** Quitting Local Comms")

if __name__ == "__main__":
    main()
