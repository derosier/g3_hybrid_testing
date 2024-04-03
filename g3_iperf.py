#!/usr/bin/env python3
# pylint: disable=too-many-lines

import logging
import argparse
import threading
import signal
import time
import os
import json
from collections import Counter
import sys

import serial

import g3_comms.g3_rx
import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_resp
import g3_comms.g3_connman
import g3_comms.g3_consts
from g3_comms import g3_lib

import iperf_msgs

g3_comms.g3_tx.cmd_verbose = True

default_port="/dev/ttyACM0"
default_baudrate=115200
default_new_baudrate=921600

# Measured 20 seconds for coordinator to start, and 25 seconds for device to start on a clean network
START_TIMEOUT = 60.0
SRV_START_TIMEOUT = 0.5
PING_START_TIMEOUT = 5.0
PING_START_RETRIES = 10
PING_RESP_TIMEOUT = 5.0
SRV_ECHO_TIMEOUT = 0.5

SRV_UDP_PORT = 5000
CLIENT_UDP_PORT = 5001

PING_MAX_TIME = 60
DONE_COUNT_PACKETS = 3

NS_IN_SEC = 1000000000

LOOKUP_MEDIA = ('plc', 'rf')

msg_buffer = bytes()

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", default=default_port, help=f"Serial port, default {default_port}")
parser.add_argument("-b", "--baud", default=default_baudrate, help=f"Serial port baud rate, default {default_baudrate}. GUI sniffer uses 460800 baud.")
parser.add_argument("-V", "--verbosity", default="WARNING", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-t", "--timeout", type=int, default=5, help="Command wait for response timeout, default 5 seconds.")
parser.add_argument("-n", "--noreset", action="store_true", help="Assume properly running, don't issue HW and SW resets. Saves 30 seconds on start.")
parser.add_argument("--speed", type=int, default=default_new_baudrate, help=f"Post-init serial port baud rate, default {default_new_baudrate}")
parser.add_argument("-S", "--size", type=int, default=iperf_msgs.MSG_LEN, help=f"Number of bytes to send in message, default {iperf_msgs.MSG_LEN}")
parser.add_argument("-m", "--media", default='all', choices=['all', 'plc', 'rf'], help="Select media to use. Default is both.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("-s", "--server", action="store_true", help="Run as a server.")
group.add_argument("-o", "--oneshotserver", action="store_true", help="Run as a server for a single client run.")
group.add_argument("-c", "--client", type=int, help="Run as a client and target the given short address.")
parser.add_argument("-a", "--activity", help="Unique name for experiment with same metadata.")
parser.add_argument("-P", "--pcm", action="store_true", help="Set PCM into pass-through mode.")
parser.add_argument("-T", "--time", type=int, default=PING_MAX_TIME, help="Time to run the test for, default 60 seconds.")
parser.add_argument("-i", "--interval", type=int, default=60, help="Interim reporting interval, default 60 seconds.")
parser.add_argument("-r", "--rate", type=int, default=0, help="Rate to send pings at, in seconds; default 0==as fast as possible.")

# Instantiate a global instance of every response we want to process on Rx
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.HWResetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.UARTBaudSetResp())
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
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.MetaError())

connman = g3_comms.g3_connman.ConnMan(g3_comms.g3_msgs.msg_decode_list)

args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

_G_running = False
def exit_clean():
    global _G_running
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
    logging.info(f"srv_start_callback({_}, {name}, {fields})")
    _G_returned_srv_start = fields
    _G_wait_srv_start.set()


# Reply G3BOOT-DEV-START: {'error_code': 0, 'status': 'G3_SUCCESS', 'short_id': 1, 'pan_id': 30749}
_G_wait_dev_start = threading.Event()
_G_returned_dev_start = {}
def dev_start_callback(_, name, fields):
    global _G_returned_dev_start
    logging.info(f"dev_start_callback({_}, {name}, {fields})")
    _G_returned_dev_start = fields
    _G_wait_dev_start.set()

# We can use the same event variables for both data callbacks
_G_wait_data = threading.Event()
_G_returned_data = {}
# Reply G3UDP-DATA.Ind: {'error_code': 0, 'prevhop_addrmode': 2, 'prevhop_pan': 30749, 'prevhop_addr': 48, 'lqi': 233, 'phasediff': 6, 'modtype': 'Robust', 'modscheme': 'Differential', 'tonemap': b'\xff\xff\xff', 'bc0num': 0, 'bc0': [], 'prevhop_media': 0, 'conn_id': 1, 'src_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x000', 'src_port': 5000, 'dest_addr': b'\xfe\x80\x00\x00\x00\x00\x00\x00x\x1d\x00\xff\xfe\x00\x00\x01', 'dest_port': 5001, 'data_len': 6, 'data': b'hello!'}
def data_rx_server_callback(_, name, fields): # pylint: disable=unused-argument
    global _G_returned_data
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
def data_rx_client_callback(_, name, fields): # pylint: disable=unused-argument
    global _G_returned_data
    _G_returned_data = fields
    _G_wait_data.set()

####################################################################################################
##  Stats and accounting
####################################################################################################

def init_accounting(stats):
    logging.debug(f"    init_srv_accounting({stats})")
    stats.clear()
    stats['send_count'] = 0
    stats['rx_count'] = 0
    stats['resp_count'] = 0
    stats['ping_count'] = 0
    stats['send_bytes'] = 0
    stats['rx_bytes'] = 0
    stats['resp_bytes'] = 0
    stats['ping_bytes'] = 0
    stats['corrupted_count'] = 0
    stats['skipped_count'] = 0
    stats['nacked_count'] = 0
    stats['send_error'] = 0
    stats['send_error'] = 0
    stats['end_time_ns'] = 0
    stats['media_list'] = []
    stats['lqi_list'] = []
    stats['phasediff_list'] = []
    stats['modtype_list'] = []
    stats['modscheme_list'] = []
    stats['tonemap_list'] = []

    # capturing start time should be the last thing we do.  I know we'll have a little overhead
    # due to python, but might as well minimize that.
    stats['start_time_ns'] = time.monotonic_ns()

def finalize_accounting(stats):
    # capturing end time should be the first thing we do.  I know we'll have a little overhead
    # due to python, but might as well minimize that.
    stats['end_time_ns'] = time.monotonic_ns()
    logging.debug(f"    finalize_srv_accounting({stats})")

    # covert the list data to counts like a histogram
    stats['media_hist'] = {}
    media = Counter(stats['media_list'])
    for key in media:
        stats['media_hist'][LOOKUP_MEDIA[key]] = media[key]
    stats['lqi_hist'] = Counter(stats['lqi_list'])
    stats['phasediff_hist'] = Counter(stats['phasediff_list'])
    stats['modtype_hist'] = Counter(stats['modtype_list'])
    stats['modscheme_hist'] = Counter(stats['modscheme_list'])
    stats['tonemap_hist'] = Counter(stats['tonemap_list'])

# start is in integer nanoseconds based on time.monotronic_ns()
# t is in seconds, can be int or floating, either works
def time_elapsed(t, start):
    elapsed = (time.monotonic_ns() - start)/NS_IN_SEC
    return t <= elapsed

def record_stats(activity_name, client_info, stats):
    # Create data dict to export
    elapsed_s = (stats['end_time_ns'] - stats['start_time_ns'])/NS_IN_SEC
    total_bytes = stats['send_bytes'] + stats['rx_bytes']
    valid_bytes = stats['send_bytes'] + stats['resp_bytes']
    total_bps = total_bytes/elapsed_s
    valid_bps = valid_bytes/elapsed_s
    lost = stats['send_count'] - stats['resp_count']
    # NOTE: We need to record this as well, but it doesn't seem to be recorded
    snr = "Unknown"

    results = {}
    results["elapsed_s"] = elapsed_s
    results["total_bytes"] = total_bytes
    results["valid_bytes"] = valid_bytes
    results["total_bps"] = total_bps
    results["valid_bps"] = valid_bps
    results["lost_packets"] = lost
    results["srv_id"] = str(client_info['srv_id'])
    results["send_count"] = stats['send_count']
    results["nacked_count"] = stats['nacked_count']
    results["ping_count"] = stats['ping_count']
    results["corrupted_count"] = stats['corrupted_count']
    results["skipped_count"] = stats['skipped_count']
    results["rx_bytes"] = stats['rx_bytes']
    results["ping_bytes"] = stats['ping_bytes']
    results["snr"] = snr   # We will need this eventually

    # Since the lists of stats are ordered, we can just report the raw info
    results["data_set"] = {}
    results["data_set"]["media"] = []
    for val in stats['media_list']:
        results["data_set"]["media"].append(LOOKUP_MEDIA[val])
    results["data_set"]["lqi"] = stats['lqi_list']
    results["data_set"]["phasediff"] = stats['phasediff_list']
    results["data_set"]["modtype"] = stats['modtype_list']
    results["data_set"]["modscheme"] = stats['modscheme_list']
    results["data_set"]["tonemap"] = []
    for val in stats['tonemap_list']:
        results["data_set"]["tonemap"].append(str(val))

    # Check for existing results json file
    # If one does NOT exist, create one
    file_name = "temp/"+activity_name+"_results.json"
    if not os.path.isfile(file_name):
        print("\nCreating results file {" + file_name + "}...")
        with open(file_name,"w", encoding='UTF-8') as f:
            json.dump([results], f, indent=2)
    # If one does exist, read it, append to it, then write it back
    #   Provide warning if it does exist to make sure we want to append
    else:
        print("\nExisting results file found {" + file_name + "}!")
        print("\n\tNew results will be appended...")
        with open(file_name, "r", encoding='UTF-8') as f:
            prior_results = json.load(f)
        prior_results.append(results)
        with open(file_name,"w", encoding='UTF-8') as f:
            json.dump(prior_results, f, indent=2)

def print_stats(side, client_info, stats):
    elapsed_s = (stats['end_time_ns'] - stats['start_time_ns'])/NS_IN_SEC
    print("======================================================================================")
    if side == iperf_msgs.MSG_DIR_OUT: # client
        print(f"iperf session results round-trip to server at {client_info['srv_id']}")
        print(f"Sent: {stats['send_count']}")
        print(f"Responses: {stats['resp_count']}")
        print(f"Nacked: {stats['nacked_count']}")
        total_bytes = stats['send_bytes'] + stats['rx_bytes']
        valid_bytes = stats['send_bytes'] + stats['resp_bytes']
        print(f"Round-trip bytes: {total_bytes}")
        print(f"Valid bytes: {valid_bytes}")
        total_bps = total_bytes/elapsed_s
        valid_bps = valid_bytes/elapsed_s
        print(f"Time: {elapsed_s}")
        lost = stats['send_count'] - stats['resp_count']
        print(f"Lost packets: {lost}")
        print(f"Total throughput bytes-per-second: {total_bps:.3f}")
        print(f"Valid throughput bytes-per-second: {valid_bps:.3f}")
    else: # server
        print(f"iperf session results from client at {client_info['addr']}")
        print(f"Arrived count: {stats['ping_count']}")
        print(f"Corrupted: {stats['corrupted_count']}")
        print(f"Skipped: {stats['skipped_count']}")
        total_bytes = stats['rx_bytes']
        valid_bytes = stats['ping_bytes']
        print(f"Rx bytes: {total_bytes}")
        print(f"Valid bytes: {valid_bytes}")
        total_bps = total_bytes/elapsed_s
        valid_bps = valid_bytes/elapsed_s
        print(f"Time: {elapsed_s:.3f}")
        lost = stats['send_count'] - stats['ping_count']
        print(f"Lost packets: {lost}")
        print(f"Total throughput bytes-per-second: {total_bps:.3f}")
        print(f"Valid throughput bytes-per-second: {valid_bps:.3f}")
    print("--------------------------------------------------------------------------------------")
    print(f"Media: {stats['media_hist']}")
    print(f"LQI: {stats['lqi_hist']}")
    print(f"PhaseDiff: {stats['phasediff_hist']}")
    print(f"Modulation Type: {stats['modtype_hist']}")
    print(f"Modulation Scheme: {stats['modscheme_hist']}")
    print(f"Tonemaps: {stats['tonemap_hist']}")
    print("======================================================================================")

####################################################################################################
##  Server stuff
####################################################################################################

# init board will do a reset and the relevant software reset
def init_board_server(device):
    # 1. Setup hooks
    g3_lib.set_hook(srv_start_callback, ['G3BOOT-SRV-START'])
    g3_lib.set_hook(join_callback, ['G3BOOT-SRV-JOIN'])
    g3_lib.set_hook(data_rx_server_callback, ['G3UDP-DATA.Ind'])
    g3_lib.set_hook(data_rx_server_callback, ['META-ERROR'])

    if args.noreset:
        return True

    # 2. HWRESET
    if args.pcm:
        logging.debug("PCM mode does not issue HOSTIF-HWRESET. Continuing board setup.")
    else:
        if not g3_lib.hw_reset(device):
            logging.error("HWRESET failed.")
            return False

    # 3. SWRESET to coordinator
    retry_count = 1
    if args.pcm:
        retry_count = 5
    swreset_ok = False
    while retry_count:
        if retry_count > 1:
            logging.warning(f"SWRESET try {retry_count}")
        (swreset_ok, _) = g3_lib.sw_reset(device, 'coordinator', 'ipv6_boot')
        retry_count = retry_count - 1
        if swreset_ok:
            break
        time.sleep(1)
    if not swreset_ok:
        logging.error("G3LIB-SWRESET unsuccessful.")
        return False

    # 4. Wait until we're reset
    # Indicator = Reply G3BOOT-SRV-START: {'error_code': 0, 'status': 'G3_SUCCESS'}
    _G_wait_srv_start.clear()
    if not _G_wait_srv_start.wait(START_TIMEOUT):
        logging.error("Never received G3BOOT-SRV-START, timeout.")

    if not g3_lib.check_status_ok(_G_returned_srv_start):
        logging.error("G3BOOT-SRV-START unsuccessful.")
        return False

    print("Server start was successful.")

    return True

def wait_for_connection(device, client_info):
    print("Waiting for connection...")
    while _G_running:
        _G_wait_data.clear()
        if not _G_wait_data.wait(SRV_START_TIMEOUT):
            continue # timeout here is expected
        if not _G_returned_data['valid_msg']:
            logging.error(f"wait_for_connection - Data Rx but invalid packet: {_G_returned_data['rx_status']}")
            continue
        packet = iperf_msgs.decode_packet(_G_returned_data['data'])
        if iperf_msgs.valid_start_packet(packet):
            client_info['start_packet'] = _G_returned_data
            client_info['addr'] = packet['sender_id']
            client_info['max_num'] = packet['max_num']
            client_info['connid'] = connman.new_conn(device, packet['sender_id'], _G_returned_data['src_port'], SRV_UDP_PORT)
            start_response = iperf_msgs.encode_start_reponse(connman.my_short_address, packet['max_num'])
            (send_ok, status) = g3_lib.send_udp(device, client_info['connid'], 1, start_response)
            if not send_ok:
                logging.error(f"Error sending start_response: {status}")
                connman.del_connection(device, client_info['connid'])
                client_info.clear()
                return False
            else:
                print("Established connection to client:")
                connman.print_conn(client_info['connid'])
                return True
    # We only get here when we're no longer _G_running.  Everything else loops or returns
    return False

def check_ping(packet, raw_msg, num, client_info, stats):
    # first, validate CRC is good!
    if packet['crc'] != packet['computed_crc']:
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        print("BAD CRC")
        return (False,num)

    # second, subtype, short id - if these are invalid, something's weird
    if packet['subtype'] != iperf_msgs.MSG_DIR_OUT or packet['sender_id'] != client_info['addr']:
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        print("BAD META")
        return (False, num)

    # check packet number
    if packet['packet_num'] > num:
        print(f"Skipped packet {num}, got {packet['packet_num']}")
        # technically might still be a valid packet, so increment number
        stats['skipped_count'] = stats['skipped_count'] + (packet['packet_num'] - num)
    elif packet['packet_num'] != num:
        print(f"BAD PACKET NUM; got {packet['packet_num']} expected {num}")
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        return (False, packet['packet_num'])

    # validate data
    length = len(packet['data'])
    if packet['data'] != iperf_msgs.MSG_DATA[:length]:
        print("BAD DATA")
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        return (False, packet['packet_num'])

    stats['ping_count'] = stats['ping_count'] + 1
    stats['ping_bytes'] = stats['ping_bytes'] + len(raw_msg['data'])

    return (True, packet['packet_num'])

def send_nack(device, client_info, expected=iperf_msgs.MSG_TYPE_PING, packet_num=0xffffffff):
    packet = iperf_msgs.encode_nack_packet(connman.my_short_address, expected, packet_num)
    (send_ok, status) = g3_lib.send_udp(device, client_info['connid'], 200, packet)
    if not send_ok:
        logging.error(f"Error sending NACK: {status}")

def do_echos(device, client_info, stats):
    logging.debug("    do_echos()")
    # So, we're in do_echos until we get a stop or a start packet. We'll use those as things to
    # kick us out of this mode, but otherwise we just rx and then echo packets.
    done = False
    msg_number = 1 # we start with 1
    ping_ok = False
    handle = 1
    _G_wait_data.clear()
    last_bytes = 0
    interval_start = time.monotonic_ns()
    start_time = interval_start
    while not done and _G_running:
        if not _G_wait_data.wait(SRV_ECHO_TIMEOUT):
            continue # timeout here is expected

        # We are also going to assume packets can't come in faster than we process them.
        # TODO: queue packets!
        raw_msg = _G_returned_data
        _G_wait_data.clear()
        if not raw_msg['valid_msg']:
            print(f"do_echos - Data Rx but invalid packet: {raw_msg['rx_status']}")
            send_nack(device, client_info)
            stats['rx_count'] = stats['rx_count'] + 1
            stats['rx_bytes'] = stats['rx_bytes'] + len(raw_msg['data'])
            stats['corrupted_count'] = stats['corrupted_count'] + 1
            continue

        packet = iperf_msgs.decode_packet(raw_msg['data'])

        # When we're in this mode, only accept from our client
        if client_info['addr'] != g3_comms.g3_msgs.hi_short_addr_from_ipaddr(raw_msg['src_addr']):
            # just discard this right now
            continue

        stats['rx_bytes'] = stats['rx_bytes'] + len(raw_msg['data'])
        stats['rx_count'] = stats['rx_count'] + 1

        # Now, figure out the type and do the right thing; We'll assume this is a valid bit of data
        if packet['type'] == iperf_msgs.MSG_TYPE_START:
            done = True
            continue
        if packet['type'] == iperf_msgs.MSG_TYPE_DONE:
            stats['send_count'] = packet['packet_num']
            done = True
            continue

        if packet['type'] == iperf_msgs.MSG_TYPE_PING:
            (ping_ok, msg_number) = check_ping(packet, raw_msg, msg_number, client_info, stats)
            # Note in the case of skips, we update msg_number to the new packet number. We only
            # increase the number, anything that decreases it is considered corrupted.
        else:
            # what could it be?  Ignore and drop. Count it as invalid.
            send_nack(device, client_info)
            stats['corrupted_count'] = stats['corrupted_count'] + 1
            continue

        if ping_ok:
            # If we got this far, we have a 100% valid packet, now send the response
            resp_packet = iperf_msgs.encode_resp_packet(connman.my_short_address, packet)
            (send_ok, status) = g3_lib.send_udp(device, client_info['connid'], handle, resp_packet, print_progress=True)
            if not send_ok:
                logging.error(f"Error sending response: {status}")
                stats['send_error'] = stats['send_error'] + 1

            # send back our packet before doing the stats on it - ie do this outside the fastpath
            stats['media_list'].append(raw_msg['prevhop_media'])
            stats['lqi_list'].append(raw_msg['lqi'])
            stats['phasediff_list'].append(raw_msg['phasediff'])
            stats['modtype_list'].append(raw_msg['modtype'])
            stats['modscheme_list'].append(raw_msg['modscheme'])
            stats['tonemap_list'].append(raw_msg['tonemap'])

            # Now update our local info
            msg_number = msg_number + 1
            handle = (handle + 1) % 100 # max value is 0xff, but we don't really care if we use all
        else:
            send_nack(device, client_info, packet_num=packet['packet_num'])

        if time_elapsed(args.interval, interval_start):
            # Note this is mostly the same code as in do_iperfs(). I didn't create a function because:
            # 1. what we use for bytes is slightly different
            # 2. function calls are expensive, and this is the fast-path. So basically I'm
            #    "unrolling" the function call.
            last_start = interval_start
            interval_start = time.monotonic_ns()
            elapsed_s = (interval_start - last_start)/NS_IN_SEC
            interval_bytes = stats['rx_bytes'] - last_bytes
            last_bytes = stats['rx_bytes']
            interval_throughput = interval_bytes/elapsed_s
            i_start = (last_start - start_time)/NS_IN_SEC
            i_end = (interval_start - start_time)/NS_IN_SEC
            print(f"\n[{i_start:.1f} - {i_end:.1f}]\t{interval_bytes} bytes\t{interval_throughput:.1f} Bps")


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
    listen_connid = connman.new_conn(device, -1, 0, SRV_UDP_PORT)
    if listen_connid is None:
        _G_running = False
        logging.error("Unable to setup listen connection, exiting.")
    else:
        connman.print_conn_list()

    # We'll loop until we quit.
    while _G_running:
        if wait_for_connection(device, client_info):
            print("Got connection, doing PONG.")
            init_accounting(stats)
            do_echos(device, client_info, stats)
            connman.del_connection(device, client_info['connid'])
            print('') # get a newline because we've been printing out the rx'd packet connection number to show progress
            finalize_accounting(stats)
            print_stats(iperf_msgs.MSG_DIR_RESP, client_info, stats)
        if args.oneshotserver:
            exit_clean()

    if listen_connid is not None:
        connman.del_connection(device, listen_connid)

####################################################################################################
##  Client stuff
####################################################################################################

def init_board_client(device):
    g3_lib.set_hook(dev_start_callback, ['G3BOOT-DEV-START'])
    g3_lib.set_hook(data_rx_client_callback, ['G3UDP-DATA.Ind'])
    g3_lib.set_hook(data_rx_client_callback, ['META-ERROR'])

    if args.noreset:
        return True

    # 2. HWRESET
    if args.pcm:
        logging.debug("PCM mode does not issue HOSTIF-HWRESET. Continuing board setup.")
    else:
        if not g3_lib.hw_reset(device):
            logging.error("HWRESET failed.")
            return False

    # 3. SWRESET to coordinator
    retry_count = 1
    if args.pcm:
        retry_count = 5
    swreset_ok = False
    while retry_count:
        if retry_count > 1:
            logging.warning(f"SWRESET try {retry_count}")
        (swreset_ok, _) = g3_lib.sw_reset(device, 'device', 'ipv6_boot')
        retry_count = retry_count - 1
        if swreset_ok:
            break
        time.sleep(1)
    if not swreset_ok:
        logging.error("G3LIB-SWRESET unsuccessful.")
        return False

    # 4. Wait until we're reset
    _G_wait_dev_start.clear()
    if not _G_wait_dev_start.wait(START_TIMEOUT):
        logging.error("Never received G3BOOT-DEV-START, timeout. Exiting")

    if not g3_lib.check_status_ok(_G_returned_dev_start):
        logging.error("G3BOOT-DEV-START unsuccessful.")
        return False

    print("Client start was successful.")

    return True

# To setup a connection, we basically need to send a message to the server.  We don't start sending
# packets though until the response is confirmed.
def setup_connection(device, connid, session_info):
    logging.debug("    setup_connection()")
    start_packet = iperf_msgs.encode_start_packet(connman.my_short_address)
    _G_wait_data.clear()
    (send_ok, status) = g3_lib.send_udp(device, connid, 1, start_packet)
    if not send_ok:
        logging.error(f"Error sending setup_connection: {status}")
        return False
    if not _G_wait_data.wait(PING_START_TIMEOUT):
        logging.error("Never received response from server, timeout.")
        return False
    if not _G_returned_data['valid_msg']:
        print(f"setup_connection - Data Rx but invalid packet: {_G_returned_data['rx_status']}")
        return False
    session_info['start_response'] = _G_returned_data
    response = iperf_msgs.decode_packet(_G_returned_data['data'])
    session_info['srv_id'] = response['sender_id']
    logging.debug(f"Got start response from {session_info['srv_id']}:\n{response}")
    print(f"Successfully setup connection with server at {session_info['srv_id']}")
    return True

def check_pong(packet, raw_msg, num, srv_id, stats):
    # for the client, we'll use 'rx_count' and 'rx_bytes' to keep track of the raw rx, ignoring
    # any corruption
    stats['rx_count'] = stats['rx_count'] + 1
    stats['rx_bytes'] = stats['rx_bytes'] + len(raw_msg['data'])

    # first, validate CRC is good!
    if packet['crc'] != packet['computed_crc']:
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        print("BAD CRC")
        return (False,num)

    # OK, it could be a NACK, handle that
    if packet['type'] == iperf_msgs.MSG_TYPE_NACK:
        stats['nacked_count'] = stats['nacked_count'] + 1
        return (False, num)

    # second, check type, subtype, short id - if these are invalid, something's weird
    if packet['type'] != iperf_msgs.MSG_TYPE_PONG or packet['subtype'] != iperf_msgs.MSG_DIR_RESP or packet['sender_id'] != srv_id:
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        print("BAD META")
        return (False, num)

    # check packet number
    if packet['packet_num'] > num:
        print(f"Skipped packet {num}, got {packet['packet_num']}")
        # technically might still be a valid packet, so increment number
        stats['skipped_count'] = stats['skipped_count'] + (packet['packet_num'] - num)
    elif packet['packet_num'] != num:
        print(f"BAD PACKET NUM; got {packet['packet_num']} expected {num}")
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        return (False, packet['packet_num'])

    # validate data
    if packet['data'] != msg_buffer:
        print("BAD DATA")
        stats['corrupted_count'] = stats['corrupted_count'] + 1
        return (False, packet['packet_num'])

    stats['resp_count'] = stats['resp_count'] + 1
    stats['resp_bytes'] = stats['resp_bytes'] + len(raw_msg['data'])

    return (True, packet['packet_num'])

def do_iperfs(device, connid, session_info, stats):#pylint: disable=unused-argument
    logging.debug("    do_iperfs()")
    packet_num = 1 # we're going to do a 1 base so we can distinguish between 0 and not.
    handle = 1
    done = False
    last_bytes = 0
    interval_start = time.monotonic_ns()
    start_time = interval_start
    while not done and _G_running:
        # We're going to do this purely synchronously, which might be slow. Send ping, wait for pong.
        # It will be really slow if we don't get a packet back because our timeout is 5 seconds (see
        # pp. 38-39 for why, should really be 10 seconds, but come on)
        # TODO: threaded implementation for the RX with accounting for packets
        ping_packet = iperf_msgs.encode_ping_packet(connman.my_short_address, packet_num, msg_buffer)
        _G_wait_data.clear()
        (send_ok, status) = g3_lib.send_udp(device, connid, handle, ping_packet, print_progress=True)
        if send_ok:
            stats['send_count'] = stats['send_count'] + 1
            stats['send_bytes'] = stats['send_bytes'] + len(ping_packet)
            if _G_wait_data.wait(PING_RESP_TIMEOUT):
                if not _G_returned_data['valid_msg']:
                    print(f"do_iperfs - Data Rx but invalid packet: {_G_returned_data['rx_status']}")
                    # even in the invalid response case, we move on to the next one
                else:
                    pong_msg = _G_returned_data
                    pong_packet = iperf_msgs.decode_packet(pong_msg['data'])
                    (ok_pong, packet_num) = check_pong(pong_packet, pong_msg, packet_num, session_info['srv_id'], stats) #pylint: disable=unused-variable
                    if ok_pong:
                        stats['media_list'].append(pong_msg['prevhop_media'])
                        stats['lqi_list'].append(pong_msg['lqi'])
                        stats['phasediff_list'].append(pong_msg['phasediff'])
                        stats['modtype_list'].append(pong_msg['modtype'])
                        stats['modscheme_list'].append(pong_msg['modscheme'])
                        stats['tonemap_list'].append(pong_msg['tonemap'])
        else:
            logging.error(f"Error sending ping: {status}")
            stats['send_error'] = stats['send_error'] + 1
            time.sleep(1.0)

        # increment our tracking data
        packet_num = packet_num + 1
        handle = (handle + 1) % 100 # max value is 0xff, but we don't really care if we use all

        # Do interval status prints if we asked for that
        if args.interval < args.time and time_elapsed(args.interval, interval_start):
            # Note this is mostly the same code as in do_echos(). I didn't create a function because:
            # 1. what we use for bytes is slightly different
            # 2. function calls are expensive, and this is the fast-path. So basically I'm
            #    "unrolling" the function call.
            last_start = interval_start
            interval_start = time.monotonic_ns()
            elapsed_s = (interval_start - last_start)/NS_IN_SEC
            interval_bytes = stats['send_bytes'] + stats['rx_bytes'] - last_bytes
            last_bytes = stats['send_bytes'] + stats['rx_bytes']
            interval_throughput = interval_bytes/elapsed_s
            i_start = (last_start - start_time)/NS_IN_SEC
            i_end = (interval_start - start_time)/NS_IN_SEC
            print(f"\n[{i_start:.1f} - {i_end:.1f}]\t{interval_bytes} bytes\t{interval_throughput:.1f} Bps")

        # If we wanted to throttle our rate, then sleep between packets
        if args.rate > 0:
            time.sleep(args.rate)

        # end condition is either sent our max packets OR args.time seconds.
        # TODO: make this configurable
        if packet_num > iperf_msgs.MSG_MAX_PACKETS or time_elapsed(args.time, stats['start_time_ns']):
            done = True

# We're going to make sure the server receives this, but not bother having it respond.  Some 10% or
# so packets don't arrive, so just send this several times.
def close_connection(device, connid, sent_count):
    logging.debug("    close_connection()")
    done_packet = iperf_msgs.encode_done_packet(connman.my_short_address, sent_count)
    done_count = 0
    while done_count < DONE_COUNT_PACKETS and _G_running:
        (send_ok, status) = g3_lib.send_udp(device, connid, 1, done_packet)
        if not send_ok and status == 'timed out':
            logging.error("Timeout when sending DONE packet.")
        done_count = done_count + 1

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
    global _G_running
    _G_running = True
    stats = {}
    session_info = {}

    # First we'll setup our connection.  We'll use port 5001 as our local port, 5000 as the srv port
    # and connect to the server at the address given
    connid = connman.new_conn(device, args.client, SRV_UDP_PORT, CLIENT_UDP_PORT)
    connman.print_conn_list()

    for tries in range(0, PING_START_RETRIES):
        if not _G_running:
            break
        if setup_connection(device, connid, session_info):
            init_accounting(stats)
            do_iperfs(device, connid, session_info, stats)
            print('') # get a newline because we've been printing out the rx'd packet connection number to show progress
            finalize_accounting(stats)
            close_connection(device, connid, stats['send_count'])
            print_stats(iperf_msgs.MSG_DIR_OUT, session_info, stats)
            if not args.activity is None:
                record_stats(args.activity, session_info, stats)
            break
        eom = "quitting."
        if tries < PING_START_RETRIES - 1:
            eom = "retrying."
        print(f"Failed to contact server, {eom}")

    connman.del_connection(device, connid)

# The following messages get sent on a device when it finishes joining the PAN:
# Reply G3BOOT-DEV-PANSORT.I: {'error_code': 0, 'pan_count': 2, 'pan': [{'PAN_ID': 30749, 'link_quality': 234, 'LBA_addr': 48, 'route_cost': 4, 'media_type': 0}, {'PAN_ID': 30749, 'link_quality': 155, 'LBA_addr': 48, 'route_cost': 4, 'media_type': 1}]}
# Reply G3BOOT-DEV-START: {'error_code': 0, 'status': 'G3_SUCCESS', 'short_id': 1, 'pan_id': 30749}

####################################################################################################
##  MAIN
####################################################################################################

def main():
    global msg_buffer
    logging.debug("*** Starting iperf")
    logging.debug(f"args: {args}")

    if args.verbosity.upper() == 'DEBUG':
        g3_comms.g3_msgs.print_msg = True

    size = args.size
    if size > iperf_msgs.MSG_LEN or size <= 0:
        logging.error(f"Invalid packet size selected {size}")
        sys.exit(1)

    if args.rate >= args.time:
        logging.error(f"Invalid ping rate selected {args.rate}")
        sys.exit(1)

    # Give user a warning about failures to log data
    if args.client and args.activity is None:
        logging.warning("     Note: The results from this will not be logged")

    # Check for existence of metadata for logging (if applicable)
    if args.client and not args.activity is None:
        # Check to make sure that there exists a metadata file created previously
        # using the `chronos_tools_cli.py` script prior to running this
        file_name = "temp/"+args.activity+"_metadata.json"
        if not os.path.isfile(file_name):
            logging.error("\n\tERROR: Cannot log data without matching metadata!"
                  "\n\tPlease run the 'chronos_tools_cli.py' script to create the metadata file"
                  "\n\tfor the activity named {%s}",args.activity)

    signal.signal(signal.SIGINT, shutdown_handler)

    # Setup the serial port to our device
    port = args.port
    baudrate = args.baud
    if args.pcm:
        baudrate = 115200
        logging.warning(f'Using port {port} at PCM baud {baudrate}')
    else:
        logging.debug(f'Using port {port} at baud {baudrate}')
    device = serial.Serial(port, baudrate=baudrate, timeout=0)
    logging.debug(f"Opened serial port {device.name}")

    if args.pcm:
        logging.warning("Setting up PCM passthrough")
        device.write( "g3_pass_through\r".encode('utf-8'))
        time.sleep(2)
        baudrate = args.baud
        logging.warning(f'PCM setup done, changing to baud {baudrate}')
        device.baudrate = baudrate
        time.sleep(1)

    # Setup our Rx processing
    logging.debug(f"Registered messages for decode: {g3_comms.g3_msgs.msg_decode_list}")
    rx_protocol = g3_comms.g3_rx.G3Rx(device)
    rx_thread = threading.Thread(target=rx_protocol.run)
    rx_thread.start()

    # Initialize the board - this is server or client specific
    init_ret = False
    if args.server or args.oneshotserver:
        init_ret = init_board_server(device)
    else:
        msg_buffer = iperf_msgs.MSG_DATA[:size]
        init_ret = init_board_client(device)

    # Force media
    media_ok = True  # default to OK, because we might not want to set the media
    if args.media == 'rf':
        (media_ok, _) = g3_lib.set_media(device, g3_comms.g3_consts.G3_MEDIA_RF)
    elif args.media == 'plc':
        (media_ok, _) = g3_lib.set_media(device, g3_comms.g3_consts.G3_MEDIA_PLC)

    # Change UART baudrate
    speed_ok = True
    if args.pcm:
        logging.warning('Forcing lower speed baud-rate of 230400 for PCM')
        (speed_ok, _) = g3_lib.set_speed(device, 230400)
    else:
        (speed_ok, _) = g3_lib.set_speed(device, args.speed)

    # Main body
    if init_ret and media_ok and speed_ok:
        # connman.init_setup() does commands and expects responses. It is unable to work unless we do
        # it after the rx_thread starts.
        connman.init_setup(device)

        print("Initialization complete")
        connman.print_info()
        if args.server or args.oneshotserver:
            do_server(device)
        else:
            do_client(device)
            exit_clean()

    # Cleanup and quit
    g3_lib.set_speed(device, baudrate) # restore to whatever speed we started with
    if args.media != 'all':
        g3_lib.set_media(device, g3_comms.g3_consts.G3_MEDIA_ALL)

    g3_comms.g3_rx.G3Rx.quit()
    rx_thread.join()

if __name__ == "__main__":
    main()
