#!/usr/bin/env python3

import logging
import argparse
import threading
import signal
import struct

import serial

import g3_comms.g3_rx
import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_resp
from g3_comms import g3_cmd
import g3_comms.g3_connman
from g3_comms.g3_crc import crc16

default_port="/dev/ttyACM0"
default_baudrate=115200

# Measured 20 seconds for coordinator to start, and 25 seconds for device to start on a clean network
START_TIMEOUT = 60.0
SRV_START_TIMEOUT = 0.5

SRV_UDP_PORT = 5000
CLIENT_UDP_PORT = 5001

MSG_TYPE_NONE  = 0x00
MSG_TYPE_START = 0x01
MSG_TYPE_DONE = 0x02
MSG_TYPE_PING = 0x03
MSG_TYPE_PONG = 0x04
MSG_TYPE_ERROR = 0xFF
MSG_TYPE_INVALID = 0xFF

MSG_DIR_NONE = 0x00
MSG_DIR_OUT = 0x01
MSG_DIR_RESP = 0x02

MSG_MAX_PACKETS = 1000

# 400 bytes below
# pg 36 shows the PHY MTU. We'll assume 2RS blocks and stay < the maxes for now
MSG_LEN = 400
MSG_DATA = bytes.fromhex(
"deadbeef deadbeef deadbeef deadbeef deadbeef deadbeef deadbeef deadbeef"
"00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000"
"11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111"
"22222222 22222222 22222222 22222222 22222222 22222222 22222222 22222222"
"33333333 33333333 33333333 33333333 33333333 33333333 33333333 33333333"
"44444444 44444444 44444444 44444444 44444444 44444444 44444444 44444444"
"55555555 55555555 55555555 55555555 55555555 55555555 55555555 55555555"
"66666666 66666666 66666666 66666666 66666666 66666666 66666666 66666666"
"77777777 77777777 77777777 77777777 77777777 77777777 77777777 77777777"
"88888888 88888888 88888888 88888888 88888888 88888888 88888888 88888888"
"99999999 99999999 99999999 99999999 99999999 99999999 99999999 99999999"
"aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa aaaaaaaa"
"55555555 55555555 a5a5a5a5 ffffffff"
)

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", default=default_port, help=f"Serial port, default {default_port}")
parser.add_argument("-b", "--baud", default=default_baudrate, help=f"Serial port baud rate, default {default_baudrate}. GUI sniffer uses 460800 baud.")
parser.add_argument("-V", "--verbosity", default="DEBUG", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-t", "--timeout", type=int, default=5, help="Command wait for response timeout, default 5 seconds.")
parser.add_argument("-n", "--noreset", action="store_true", help="Assume properly running, don't issue HW and SW resets. Saves 30 seconds on start.")
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

_G_running = False
def exit_clean():
    global _G_running
    g3_comms.g3_rx.G3Rx.quit()
    _G_running = False

def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    exit_clean()

####################################################################################################
##  Message processing
####################################################################################################

# The callback is called from the received message hook and because of the way it is done
# the first parameter will be the actual Resp object. We can ignore this. The next arguments:
#    _ - This is the context set when the hook is set here we can ignore it
#    name - The name of the message rx, which would be G3Resp.g3_name
#    fields - the parsed fields from the message


# Happens when a device joins the PAN
# Reply G3BOOT-SRV-JOIN: {'error_code': 0, 'e_addr': 12336387418442792960, 'short_id': 1}
_G_wait_joined = threading.Event()
_G_returned_joined = {}
def join_callback(_, name, fields):
    global _G_returned_joined
    logging.debug(f"join_callback({_}, {name}, {fields})")
    print(f"Node with address {fields['short_id']} joined the network.")
    _G_returned_joined = fields
    _G_wait_joined.set()

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

# We can use the same event variables for both data callbacks
_G_wait_data = threading.Event()
_G_returned_data = {}
# Reply G3UDP-DATA.Ind: {'error_code': 0, 'prevhop_addrmode': 2, 'prevhop_pan': 30749, 'prevhop_addr': 48, 'lqi': 233, 'phasediff': 6, 'modtype': 'Robust', 'modscheme': 'Differential', 'tonemap': b'\xff\xff\xff', 'bc0num': 0, 'bc0': [], 'prevhop_media': 0, 'conn_id': 1, 'src_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x000', 'src_port': 5000, 'dest_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x00\x01', 'dest_port': 5001, 'data_len': 6, 'data': b'hello!'}
def data_rx_server_callback(_, name, fields):
    global _G_returned_data
    print(f"data_rx_server_callback({_}, {name}, {fields})")
    _G_returned_data = fields
    _G_wait_data.set()

#Reply G3UDP-DATA.Ind: {'error_code': 0, 'prevhop_addrmode': 2, 'prevhop_pan':
#30749, 'prevhop_addr': 48, 'lqi': 233, 'phasediff': 6, 'modtype': 'Robust',
#'modscheme': 'Differential', 'tonemap': b'\xff\xff\xff', 'bc0num': 0, 'bc0':
#[], 'prevhop_media': 0, 'conn_id': 1, 'src_addr':
#b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x000', 'src_port':
#5000, 'dest_addr':
#b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x00\x01', 'dest_port':
#5001, 'data_len': 6, 'data': b'hello!'}
def data_rx_client_callback(_, name, fields):
    global _G_returned_data
    print(f"data_rx_client_callback({_}, {name}, {fields})")
    _G_returned_data = fields
    _G_wait_data.set()

def set_hook(hook, name_list):
    for msg in g3_comms.g3_msgs.msg_decode_list:
        for name_msg in name_list:
            if msg.g3_name == name_msg:
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

def send_udp(device, connid, handle, packet):
    cmd_args = argparse.Namespace()
    cmd_args.connid = connid
    cmd_args.handle = handle
    cmd_args.bindata = packet
    udp_cmd = g3_cmd.UDPData()
    udp_cmd.parse_args(cmd_args)
    udp_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, udp_cmd)
    udp_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("G3UDP-DATA unsuccessful.")
        return (False, fields['status'])
    return (True, fields['status'])

# Packet formats are all similar, we put all the fields for all the messages in there
# and just ignore the ones that aren't relevant.
# B  | Type
# B  | Direction: None (0) | Tx (1)| Response (2)
# H  | Sender short_id
# I  | Max Packet Number
# I  | Packet Number
# H  | Length
# xB | Data
# H  | CRC16 - CRC of all bytes in this packet except the CRC
#
# We'll use a data length of 400 bytes. See MSG_LEN

# By always using init_packet_fields() we avoid checking `except KeyValue` logic. So to simplify
# our other functions, let's always use this to init the fields. Also important as we won't always
# use all the fields, so we have to have them, but they might need to be set at defaults.
def init_packet_fields():
    fields = {}
    fields['type'] = MSG_TYPE_NONE
    fields['direction'] = MSG_DIR_NONE
    fields['sender_id'] = connman.my_short_address
    fields['max_num'] = MSG_MAX_PACKETS
    fields['packet_num'] = 0
    fields['data'] = b''
    fields['crc'] = 0
    fields['computed_crc'] = 0
    return fields

MSG_HEAD_FORMAT = "<BBHIIH"
MSG_DATA_FORMAT = "{length}s"
MSG_CRC_FORMAT = "H"

def encode_packet(fields):
    length = len(fields['data'])
    msg = struct.pack(f"<BBHIIH{length}s",
                      fields['type'], fields['direction'],
                      fields['sender_id'], fields['max_num'],
                      fields['packet_num'], length, fields['data'])
    computed_crc = crc16.bit_by_bit_fast(msg)
    complete_msg = msg + struct.pack("<H", computed_crc)
    return complete_msg

def decode_packet(data):
    print(f"@@@ decode packet: {data.hex()}")
    fields = {}
    fmt = "<BBHIIH"
    header = struct.unpack_from(fmt, data)
    fields['type'] = header[0]
    fields['direction'] = header[1]
    fields['sender_id'] = header[2]
    fields['max_num'] = header[3]
    fields['packet_num'] = header[4]
    length = header[5]
    offset = struct.calcsize(fmt)
    fmt = f"<{length}s"
    fields['data'] = struct.unpack_from(fmt, data, offset)[0]
    offset = offset + struct.calcsize(fmt)
    fields['crc'] = struct.unpack_from("<H", data, offset)[0]
    fields['computed_crc'] = crc16.bit_by_bit_fast(data[0:offset])
    logging.debug(f"CRC computed on data packet {fields['computed_crc']:04x}, CRC Rx {fields['crc']:04x}")
    return fields

def encode_start_packet():
    fields = init_packet_fields()
    fields['type'] = MSG_TYPE_START
    fields['direction'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    return encode_packet(fields)

def encode_start_reponse(num_packets):
    fields = init_packet_fields()
    fields['type'] = MSG_TYPE_START
    fields['direction'] = MSG_DIR_RESP
    fields['max_num'] = num_packets
    return encode_packet(fields)

def valid_start_packet(packet):
    print(f"    valid_start_packet({packet})")
    return True

def encode_ping_packet(packet_num):
    fields = init_packet_fields()
    fields['type'] = MSG_TYPE_PING
    fields['direction'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    fields['packet_num'] = packet_num
    fields['data'] = MSG_DATA
    return encode_packet(fields)

def encode_resp_packet(ping_fields):
    fields = init_packet_fields()
    fields['type'] = MSG_TYPE_PONG
    fields['direction'] = MSG_DIR_RESP
    fields['max_num'] = ping_fields['max_num']
    fields['packet_num'] = ping_fields['packet_num']
    fields['data'] = ping_fields['data']
    return encode_packet(fields)

def encode_done_packet(packets_sent):
    fields = init_packet_fields()
    fields['type'] = MSG_TYPE_DONE
    fields['direction'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    fields['packet_num'] = packets_sent
    return encode_packet(fields)


####################################################################################################
##  Stats and accounting
####################################################################################################

def init_accounting(stats):
    logging.debug(f"    init_srv_accounting({stats})")

def finalize_accounting(stats):
    logging.debug(f"    finalize_srv_accounting({stats})")

def print_stats(client_info, stats):
    print("iperf session results")
    print(f"Client:\n\t{client_info}")
    print(f"Stats:\n\t{stats}")

####################################################################################################
##  Server stuff
####################################################################################################

# init board will do a reset and the relevant software reset
def init_board_server(device):
    # 1. Setup hooks
    set_hook(srv_start_callback, ['G3BOOT-SRV-START'])
    set_hook(join_callback, ['G3BOOT-SRV-JOIN'])
    set_hook(data_rx_server_callback, ['G3UDP-DATA.Ind'])

    if args.noreset:
        return True

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

def wait_for_connection(device, client_info):
    print("Waiting for connection...")
    _G_wait_data.clear()
    while _G_running:
        if not _G_wait_data.wait(SRV_START_TIMEOUT):
            continue # timeout here is expected
        packet = decode_packet(_G_returned_data['data'])
        if valid_start_packet(packet):
            client_info['start_packet'] = _G_returned_data
            client_info['addr'] = packet['sender_id']
            client_info['max_num'] = packet['max_num']
            client_info['connid'] = connman.new_conn(device, packet['sender_id'], _G_returned_data['src_port'], SRV_UDP_PORT)
            start_response = encode_start_reponse(packet['max_num'])
            (send_ok, status) = send_udp(device, client_info['connid'], 1, start_response)
            if not send_ok:
                logging.error(f"Error sending start_response: {status}")
                connman.del_connection(device, client_info['connid'])
                client_info.clear()
                return False
            else:
                return True
    # We only get here when we're no longer _G_running.  Everything else loops or returns
    return False

def do_echos(device, connid, client_info, stats): #pylint: disable=unused-argument
    logging.debug("    do_echos()")

# The purpose of the server is to get iperf packets and echo them back. Basically in sequence:
#    1. wait for a connection, then setup the echo processing
#    2. While more packets
#       2.1 rx a packet
#       2.2 validate packet
#       2.3 change to indicate it was rx and send back
#       2.4 do accounting
#    3. clean up connection
#    4. print accounting information
#    5. go back to wait state as long as _G_running is true
def do_server(device):
# The following messages get sent on a coordinator when a device joins:
# Reply G3BOOT-SRV-GETPSK: {'error_code': 0, 'e_addr': 12336387418442792960, 'idp_len': 8, 'idp': (12336387418442792960, 8, b'\x00\x80\xe1\xff\xfe\xa63\xab\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')}
# Reply G3BOOT-SRV-JOIN: {'error_code': 0, 'e_addr': 12336387418442792960, 'short_id': 1}
    global _G_running
    _G_running = True
    stats = {}
    client_info = {}

    # First we'll setup our connection.  We'll use port 5000 as our local port, and setup to accept
    # from all.
    connid = connman.new_conn(device, -1, 0, SRV_UDP_PORT)

    # We'll loop until we quit.
    while _G_running:
        if wait_for_connection(device, client_info):
            print("Got connection, doing PONG.")
            init_accounting(stats)
            do_echos(device, connid, client_info, stats)
            finalize_accounting(stats)
            print_stats(client_info, stats)

    connman.del_connection(device, connid)

####################################################################################################
##  Client stuff
####################################################################################################

def init_board_client(device):
    set_hook(dev_start_callback, ['G3BOOT-DEV-START'])
    set_hook(data_rx_client_callback, ['G3UDP-DATA.Ind'])

    if args.noreset:
        return True

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

# To setup a connection, we basically need to send a message to the server.  We don't start sending
# packets though until the response is confirmed.
def setup_connection(device, connid, session_info):
    logging.debug("    setup_connection()")
    start_packet = encode_start_packet()
    _G_wait_data.clear()
    (send_ok, status) = send_udp(device, connid, 1, start_packet)
    if not send_ok:
        logging.error(f"Error sending setup_connection: {status}")
        return False
    if not _G_wait_data.wait(START_TIMEOUT):
        logging.error("Never received response from server, timeout.")
        return False
    session_info['start_response'] = _G_returned_data
    response = decode_packet(_G_returned_data['data'])
    print(f"Got start response:\n{response}")
    return True

def do_iperfs(device, connid, session_info, stats):#pylint: disable=unused-argument
    logging.debug("    do_iperfs()")

def close_connection(device, connid, session_info):#pylint: disable=unused-argument
    logging.debug("    close_connection()")

# The purpose of the client is to send iperf packets and rx the response back from the server.
# Basically in sequence:
#    1. initiate a connection with a server
#    2. While more packets to send
#       2.1 Tx a packet
#       2.2 Wait for Rx response
#       2.3 validate response packet
#       2.4 do accounting
#    3. clean up connection
#    4. print accounting information
def do_client(device):
    stats = {}
    session_info = {}

    # First we'll setup our connection.  We'll use port 5001 as our local port, 5000 as the srv port
    # and connect to the server at the address given
    connid = connman.new_conn(device, args.client, SRV_UDP_PORT, CLIENT_UDP_PORT)

    if setup_connection(device, connid, session_info):
        init_accounting(stats)
        do_iperfs(device, connid, session_info, stats)
        finalize_accounting(stats)
        close_connection(device, connid, session_info)
        print_stats(session_info, stats)

    connman.del_connection(device, connid)

# The following messages get sent on a device when it finishes joining the PAN:
# Reply G3BOOT-DEV-PANSORT.I: {'error_code': 0, 'pan_count': 2, 'pan': [{'PAN_ID': 30749, 'link_quality': 234, 'LBA_addr': 48, 'route_cost': 4, 'media_type': 0}, {'PAN_ID': 30749, 'link_quality': 155, 'LBA_addr': 48, 'route_cost': 4, 'media_type': 1}]}
# Reply G3BOOT-DEV-START: {'error_code': 0, 'status': 'G3_SUCCESS', 'short_id': 1, 'pan_id': 30749}

####################################################################################################
##  MAIN
####################################################################################################

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
            exit_clean()

    # Cleanup and quit
    rx_thread.join()

if __name__ == "__main__":
    main()
