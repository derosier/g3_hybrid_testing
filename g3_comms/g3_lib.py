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

def get_dbgtool(device):
    # Set the connection
    dbgtool_cmd = g3_comms.g3_cmd.DBGToolCmd()
    dbgtool_cmd.parse_args(None)
    dbgtool_cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, dbgtool_cmd)
    dbgtool_cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    try:
        if not fields['error_code'] == 0:
            logging.error("HOSTIF-DBGTOOL unsuccessful.")
            return (False, fields)
    except KeyError:
        logging.error("HOSTIF-DBGTOOL unsuccessful.")
        return (False, fields)
    return (True, fields)

def get_panid(device):
    (status, fields) = get_dbgtool(device)
    if status:
        return fields['pan_id']
    else:
        return 0xffff

def get_shortid(device):
    (status, fields) = get_dbgtool(device)
    if status:
        return fields['short_id']
    else:
        return 0xffff

def get_nvm(device, section, attribute):
    cmd_args = argparse.Namespace()
    cmd_args.nvmcmd = 'read'
    cmd_args.section = section
    if section == 'plc':
        try:
            cmd_args.offset = g3_comms.g3_consts.NVM_PLC_OFFSETS[attribute]
            cmd_args.size = g3_comms.g3_consts.NVM_PLC_SIZE[attribute]
        except KeyError:
            logging.error(f"Invalid field for PLC NVM {attribute}")
            return 'G3_PARAMETER_ERROR'
    else:
        logging.error(f"Unsupported nvm section {section} for get_nvm()")
        return 'G3_PARAMETER_ERROR'

    logging.debug(f"NVMCmd with {cmd_args}")
    cmd = g3_cmd.NVMCmd()
    cmd.parse_args(cmd_args)
    cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, cmd)
    cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("HOSTIF-NVM unsuccessful.")
        return fields['status']
    return fields['data']

def set_nvm(device, section, offset, data):
    cmd_args = argparse.Namespace()
    cmd_args.nvmcmd = 'write'
    cmd_args.section = section
    cmd_args.offset = offset
    cmd_args.bindata = data
    cmd = g3_cmd.NVMCmd()
    cmd.parse_args(cmd_args)
    cmd.setup_rx(g3_comms.g3_msgs.msg_decode_list)
    fields = g3_comms.g3_tx.send_and_wait(device, cmd)
    cmd.clean_rx(g3_comms.g3_msgs.msg_decode_list)
    if not check_status_ok(fields):
        logging.error("HOSTIF-NVM unsuccessful.")
        return (False, fields['status'])
    return (True, fields['status'])

def set_nvm_psk(device, psk_index, data):
    if psk_index < 0 or psk_index > 1:
        logging.error(f"Invalid PSK index {psk_index}")
        return (False, 'G3_PARAMETER_ERROR')

    if psk_index == 0:
        (status, status_str) = set_nvm(device, 'plc', g3_comms.g3_consts.NVM_PLC_OFFSETS['KEY0'], data)
    else:
        (status, status_str) = set_nvm(device, 'plc', g3_comms.g3_consts.NVM_PLC_OFFSETS['KEY1'], data)
    if not status:
        logging.error(f"Setting KEY{psk_index} unsuccessful.")
        return (False, status_str)

    if psk_index == 0:
        (status, status_str) = set_nvm(device, 'plc', g3_comms.g3_consts.NVM_PLC_OFFSETS['KEY0FREE'], b'\x00')
    else:
        (status, status_str) = set_nvm(device, 'plc', g3_comms.g3_consts.NVM_PLC_OFFSETS['KEY1FREE'], b'\x01')
    if not status:
        logging.error(f"Setting KEY{psk_index}FREE unsuccessful.")
        return (False, status_str)
    return (True, status_str)

def set_nvm_psk_index(device, psk_index):
    if psk_index < 0 or psk_index > 1:
        logging.error(f"Invalid PSK index {psk_index}")
        return (False, 'G3_PARAMETER_ERROR')
    data = psk_index.to_bytes(1, byteorder='little')
    (status, status_str) = set_nvm(device, 'plc', g3_comms.g3_consts.NVM_PLC_OFFSETS['ACTIVEKEYIDX'], data)
    if not status:
        logging.error("Setting ACTIVEKEYIDX unsuccessful.")
        return (False, status_str)
    return (True, status_str)

def set_nvm_panid(device, value):
    data = value.to_bytes(2, byteorder='little')
    (status, status_str) = set_nvm(device, 'plc', g3_comms.g3_consts.NVM_PLC_OFFSETS['PANID'], data)
    if not status:
        logging.error("Setting PANID unsuccessful.")
        return (False, status_str)
    return (True, status_str)

def set_nvm_shortaddr(device, value):
    data = value.to_bytes(2, byteorder='little')
    (status, status_str) = set_nvm(device, 'plc', g3_comms.g3_consts.NVM_PLC_OFFSETS['SHORTADDR'], data)
    if not status:
        logging.error("Setting SHORTADDR unsuccessful.")
        return (False, status_str)
    return (True, status_str)

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
    logging.debug(f"Serial port baud rate updated to {speed}")
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
