import argparse
import logging

import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_cmd
import g3_comms.g3_consts

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
        fields['status'] = 'timed out'
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

def sw_reset(device, nodetype, mode):
    cmd_args = argparse.Namespace()
    cmd_args.bandplan = 'FCC'
    cmd_args.devicetype = nodetype
    cmd_args.mode = mode
    swreset_cmd = g3_cmd.SWResetCmd()
    swreset_cmd.parse_args(cmd_args)
    swreset_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, swreset_cmd)
    swreset_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("G3LIB-SWRESET unsuccessful.")
        return (False, fields['status'])
    return (True, fields['status'])

def set_speed(device, speed):
    cmd_args = argparse.Namespace()
    cmd_args.speed = speed
    speed_cmd = g3_cmd.UARTBaudSetCmd()
    speed_cmd.parse_args(cmd_args)
    speed_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, speed_cmd)
    speed_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("HOSTIF-BAUDRATESET unsuccessful.")
        return (False, fields['status'])
    device.baudrate = speed
    logging.warning(f"Serial port baud rate updated to {speed}")
    return (True, fields['status'])

def set_media(device, value):
    cmd_args = argparse.Namespace()
    cmd_args.id = g3_comms.g3_consts.G3_LIB_PECHANNELCONFIG_ID
    cmd_args.index = 0
    cmd_args.data = value
    set_cmd = g3_cmd.G3SetCmd()
    set_cmd.parse_args(cmd_args)
    set_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, set_cmd)
    set_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error(f"Error setting media to {value}.")
        return (False, fields['status'])
    return (True, fields['status'])

def send_udp(device, connid, handle, packet, print_progress=False):
    cmd_args = argparse.Namespace()
    logging.debug(f"send_udp to connection {connid}")
    if print_progress:
        print(f'{connid}', end='', flush=True)
    cmd_args.connid = connid
    cmd_args.handle = handle
    cmd_args.bindata = packet
    udp_cmd = g3_cmd.UDPData()
    udp_cmd.parse_args(cmd_args)
    udp_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, udp_cmd, timeout=5)
    udp_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("G3UDP-DATA unsuccessful.")
        return (False, fields['status'])
    return (True, fields['status'])
