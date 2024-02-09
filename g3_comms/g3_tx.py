import logging
import struct
import threading

from g3_comms.g3_crc import crc16

_G_wait = threading.Event()
_G_returned_fields = {}

cmd_verbose = False

# Arguments:
#    name - The name of the message rx, which would be G3Resp.g3_name
#    fields - the parsed fields from the message
def cb_wait(name, fields):
    global _G_returned_fields
    logging.debug(f"cb_wait called with ({name}, {fields})")
    _G_returned_fields = fields
    _G_wait.set()

def encap_msg(g3_id, data):
    header = struct.pack("<BB BHBI", 0x16, 0x16, # sync fields
                            g3_id, # cmd id
                            len(data), # the length of the data
                            0x0, 0) # security mode, counter
    msg = header + data
    # Since we're not using security, there's no TAG bytes
    computed_crc = crc16.bit_by_bit_fast(msg)
    complete_msg = msg + struct.pack("<H", computed_crc)
    return complete_msg

def form_msg(cmd):
    msg_data = cmd.encode_cmd()
    return encap_msg(cmd.g3_id, msg_data)

def send(device, cmd):
    if cmd_verbose:
        logging.info(f"Sending command {cmd.g3_name}")
    else:
        logging.debug(f"Sending command {cmd.g3_name}")
    msg = form_msg(cmd)
    logging.debug(f"{msg}")
    byte_count = device.write(msg)
    logging.debug(f"Wrote {byte_count} bytes to port")
    if byte_count != len(msg):
        logging.error("Error when sending command")

def send_and_wait(device, cmd, timeout=1):
    logging.debug(f"Sending command {cmd.g3_name} wait with timeout {timeout}")
    _G_wait.clear()
    cmd.set_cb(cb_wait)
    send(device, cmd)
    if not _G_wait.wait(timeout):
        # Timed out instead of finished
        logging.warning(f"Command {cmd.g3_name} response timed out.")
        return {}
    return _G_returned_fields
