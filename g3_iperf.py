#!/usr/bin/env python3

import logging
import argparse
import threading
import signal

import serial

import g3_comms.g3_rx
import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_resp
from g3_comms import g3_cmd
import g3_comms.g3_connman

default_port="/dev/ttyACM0"
default_baudrate=115200

# Measured 20 seconds for coordinator to start, and 25 seconds for device to start on a clean network
START_TIMEOUT = 60.0

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", default=default_port, help=f"Serial port, default {default_port}")
parser.add_argument("-b", "--baud", default=default_baudrate, help=f"Serial port baud rate, default {default_baudrate}. GUI sniffer uses 460800 baud.")
parser.add_argument("-V", "--verbosity", default="DEBUG", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-t", "--timeout", type=int, default=5, help="Command wait for response timeout, default 5 seconds.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("-s", "--server", action="store_true", help="Run as a server.")
group.add_argument("-c", "--client", type=int, help="Run as a client and target the given short address.")

# Instantiate a global instance of every response we want to process on Rx
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.HWResetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.DBGToolResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3GetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3SetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.SWResetResp())
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

connman = g3_comms.g3_connman.ConnMan(g3_comms.g3_msgs.msg_decode_list)

args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    g3_comms.g3_rx.G3Rx.quit()



# The callback is called from the received message hook and because of the way it is done
# the first parameter will be the actual Resp object. We can ignore this. The next arguments:
#    _ - This is the context set when the hook is set here we can ignore it
#    name - The name of the message rx, which would be G3Resp.g3_name
#    fields - the parsed fields from the message


# Reply G3BOOT-SRV-JOIN: {'error_code': 0, 'e_addr': 12336387418442792960, 'short_id': 1}
def join_callback(_, name, fields):
    logging.debug(f"join_callback({_}, {name}, {fields})")
    print(f"Node with address {fields['short_id']} joined the network.")

# Reply G3BOOT-SRV-START: {'error_code': 0, 'status': 'G3_SUCCESS'}
_G_wait_srv_start = threading.Event()
_G_returned_srv_start = {}
def srv_start_callback(_, name, fields):
    global _G_returned_srv_start
    print(f"srv_start_callback({_}, {name}, {fields})")
    _G_returned_srv_start = fields
    _G_wait_srv_start.set()


# Reply G3BOOT-DEV-START: {'error_code': 0, 'status': 'G3_SUCCESS', 'short_id': 1, 'pan_id': 30749}
_G_wait_dev_start = threading.Event()
_G_returned_dev_start = {}
def dev_start_callback(_, name, fields):
    global _G_returned_dev_start
    print(f"dev_start_callback({_}, {name}, {fields})")
    _G_returned_dev_start = fields
    _G_wait_dev_start.set()

# Reply G3UDP-DATA.Ind: {'error_code': 0, 'prevhop_addrmode': 2, 'prevhop_pan': 30749, 'prevhop_addr': 48, 'lqi': 233, 'phasediff': 6, 'modtype': 'Robust', 'modscheme': 'Differential', 'tonemap': b'\xff\xff\xff', 'bc0num': 0, 'bc0': [], 'prevhop_media': 0, 'conn_id': 1, 'src_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x000', 'src_port': 5000, 'dest_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x00\x01', 'dest_port': 5001, 'data_len': 6, 'data': b'hello!'}
def data_rx_server_callback(_, name, fields):
    print(f"data_rx_server_callback({_}, {name}, {fields})")

# Reply G3UDP-DATA.Ind: {'error_code': 0, 'prevhop_addrmode': 2, 'prevhop_pan': 30749, 'prevhop_addr': 48, 'lqi': 233, 'phasediff': 6, 'modtype': 'Robust', 'modscheme': 'Differential', 'tonemap': b'\xff\xff\xff', 'bc0num': 0, 'bc0': [], 'prevhop_media': 0, 'conn_id': 1, 'src_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x000', 'src_port': 5000, 'dest_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x00\x01', 'dest_port': 5001, 'data_len': 6, 'data': b'hello!'}
def data_rx_client_callback(_, name, fields):
    print(f"data_rx_client_callback({_}, {name}, {fields})")

def set_hook(hook, name_list):
    for msg in g3_comms.g3_msgs.msg_decode_list:
        if msg.g3_name in name_list:
            msg.set_hook(hook, None)

def check_status_ok(fields):
    try:
        if not fields['status'] == 'G3_SUCCESS':
            logging.debug(f"Check status error: {fields['status']}")
            return False
    except KeyError:
        logging.debug("Check status error fields['status'] not found.")
        return False
    return True

def hw_reset(device):
    reset_cmd = g3_cmd.HWResetCmd()
    reset_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, reset_cmd)
    reset_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    try:
        if not fields['error_code'] == 0:
            logging.error("HOSTIF-HWRESET unsuccessful.")
            return False
    except KeyError:
        logging.error("HOSTIF-HWRESET unsuccessful.")
        return False
    return True

# init board will do a reset and the relevant software reset
def init_board_server(device):
    # 1. Setup hooks
    set_hook(srv_start_callback, ('G3BOOT-SRV-START'))
    set_hook(join_callback, ('G3BOOT-SRV-JOIN'))
    set_hook(data_rx_server_callback, ('G3UDP-DATA.Ind'))

    # 2. HWRESET
    if not hw_reset(device):
        return False

    # 3. SWRESET to coordinator
    _G_wait_srv_start.clear()
    cmd_args = argparse.Namespace()
    cmd_args.bandplan = 'FCC'
    cmd_args.devicetype = 'coordinator'
    cmd_args.mode = 'ipv6_boot'
    swreset_cmd = g3_cmd.SWResetCmd()
    swreset_cmd.parse_args(cmd_args)
    swreset_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, swreset_cmd)
    swreset_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("G3LIB-SWRESET unsuccessful.")
        return False

    # 4. Wait until we're reset
    # Indicator = Reply G3BOOT-SRV-START: {'error_code': 0, 'status': 'G3_SUCCESS'}
    if not _G_wait_srv_start.wait(START_TIMEOUT):
        logging.error("Never received G3BOOT-SRV-START, timeout.")

    if not check_status_ok(_G_returned_srv_start):
        logging.error("G3BOOT-SRV-START unsuccessful.")
        return False

    return True

def do_server(device): # pylint: disable=unused-argument
    pass
# The following messages get sent on a coordinator when a device joins:
# Reply G3BOOT-SRV-GETPSK: {'error_code': 0, 'e_addr': 12336387418442792960, 'idp_len': 8, 'idp': (12336387418442792960, 8, b'\x00\x80\xe1\xff\xfe\xa63\xab\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')}
# Reply G3BOOT-SRV-JOIN: {'error_code': 0, 'e_addr': 12336387418442792960, 'short_id': 1}



def init_board_client(device):
    set_hook(dev_start_callback, ('G3BOOT-DEV-START'))
    set_hook(data_rx_client_callback, ('G3UDP-DATA.Ind'))

    # 2. HWRESET
    if not hw_reset(device):
        return False

    # 3. SWRESET to coordinator
    _G_wait_dev_start.clear()
    cmd_args = argparse.Namespace()
    cmd_args.bandplan = 'FCC'
    cmd_args.devicetype = 'device'
    cmd_args.mode = 'ipv6_boot'
    swreset_cmd = g3_cmd.SWResetCmd()
    swreset_cmd.parse_args(cmd_args)
    swreset_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, swreset_cmd)
    swreset_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("G3LIB-SWRESET unsuccessful.")
        return False

    # 4. Wait until we're reset
    if not _G_wait_dev_start.wait(START_TIMEOUT):
        logging.error("Never received G3BOOT-DEV-START, timeout. Exiting")

    if not check_status_ok(_G_returned_dev_start):
        logging.error("G3BOOT-DEV-START unsuccessful.")
        return False

    return True

def do_client(device): # pylint: disable=unused-argument
    pass
# The following messages get sent on a device when it finishes joining the PAN:
# Reply G3BOOT-DEV-PANSORT.I: {'error_code': 0, 'pan_count': 2, 'pan': [{'PAN_ID': 30749, 'link_quality': 234, 'LBA_addr': 48, 'route_cost': 4, 'media_type': 0}, {'PAN_ID': 30749, 'link_quality': 155, 'LBA_addr': 48, 'route_cost': 4, 'media_type': 1}]}
# Reply G3BOOT-DEV-START: {'error_code': 0, 'status': 'G3_SUCCESS', 'short_id': 1, 'pan_id': 30749}

def main():
    logging.debug("*** Starting iperf")
    logging.debug(f"args: {args}")

    signal.signal(signal.SIGINT, shutdown_handler)

    # Setup the serial port to our device
    port = args.port
    baudrate = args.baud
    logging.debug(f'Using port {port} at baud {baudrate}')
    device = serial.Serial(port, baudrate=baudrate, timeout=0)
    logging.debug(f"Opened serial port {device.name}")

    # Setup our Rx processing
    logging.debug(f"Registered messages for decode: {g3_comms.g3_msgs.msg_decode_list}")
    rx_protocol = g3_comms.g3_rx.G3Rx(device)
    rx_thread = threading.Thread(target=rx_protocol.run)
    rx_thread.start()

    init_ret = False
    if args.server:
        init_ret = init_board_server(device)
    else:
        init_ret = init_board_client(device)

    if init_ret:
        # connman.init_setup() does commands and expects responses. It is unable to work unless we do
        # it after the rx_thread starts.
        connman.init_setup(device)

        print("\n\nInitialization complete")
        print("=======================\n")
        connman.print_info()
        connman.print_conn_list()
        if args.server:
            do_server(device)
        else:
            do_client(device)

    # Cleanup and quit
    rx_thread.join()

if __name__ == "__main__":
    main()
