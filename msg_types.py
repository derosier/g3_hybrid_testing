import logging
import struct

from g3_comms.g3_crc import crc16

####################################################################################################
##  Message types
####################################################################################################

MSG_TYPE_NONE  = 0x00

# Generic and iperf message types
MSG_TYPE_START = 0x01
MSG_TYPE_DONE = 0x02
MSG_TYPE_PING = 0x03
MSG_TYPE_PONG = 0x04

# local comms messages
MSG_TYPE_LC_REQUEST_ID = 0x11
MSG_TYPE_LC_RESPOND_ID = 0x12
MSG_TYPE_LC_LCN_INFORMATION = 0x13
MSG_TYPE_LC_LCN_INFO_CONFIRM = 0x14
MSG_TYPE_LC_SWITCH_NETWORK = 0x15
MSG_TYPE_LC_PAIR_CLEAR = 0x16

# error or similar
MSG_TYPE_NACK = 0x84
MSG_TYPE_ERROR = 0xFE
MSG_TYPE_INVALID = 0xFF


####################################################################################################
##  Message Subtypes
####################################################################################################

# generic
MSG_SUBTYPE_NONE = 0x00

# iperf subtype constants
MSG_DIR_NONE = MSG_SUBTYPE_NONE
MSG_DIR_OUT = 0x01
MSG_DIR_RESP = 0x02

####################################################################################################
##  Message parameters
####################################################################################################
MSG_PARAM_NONE = 0x0000


####################################################################################################
##  Misc constants
####################################################################################################
MAX_DEST = 0xFFFF
MSG_MAX_PACKETS = 10000

####################################################################################################
##  Packet header structure and functions
####################################################################################################

# Packet formats are all similar, we put all the fields for all the messages in there
# and just ignore the ones that aren't relevant.
# B  | Type
# B  | Subtype
# H  | Sender short_id
# H  | Destination short_id
# H  | Packet sequence Number
# H  | Max Packet Number/Reserved
# H  | Message specific parameter/Reserved
# H  | Length
# xB | Data
# H  | CRC16 - CRC of all bytes in this packet except the CRC
#
# We'll use a data length of 400 bytes. See MSG_LEN

# By always using init_packet_fields() we avoid checking `except KeyValue` logic. So to simplify
# our other functions, let's always use this to init the fields. Also important as we won't always
# use all the fields, so we have to have them, but they might need to be set at defaults.
def init_packet_fields(sender_address, dest_addr = MAX_DEST):
    fields = {}
    fields['type'] = MSG_TYPE_NONE
    fields['subtype'] = MSG_SUBTYPE_NONE
    fields['sender_id'] = sender_address
    fields['dest_id'] = dest_addr
    fields['packet_num'] = 0
    fields['max_num'] = MSG_MAX_PACKETS
    fields['param'] = MSG_PARAM_NONE
    fields['data'] = b''
    fields['crc'] = 0
    fields['computed_crc'] = 0
    return fields

MSG_HEAD_FORMAT = "<BBHHHHHH"
MSG_DATA_FORMAT = "{length}s"
MSG_CRC_FORMAT = "H"

def encode_packet(fields):
    length = len(fields['data'])
    msg = struct.pack(f"<BBHHHHHH{length}s",
                      fields['type'], fields['subtype'],
                      fields['sender_id'], fields['dest_id'],
                      fields['packet_num'], fields['max_num'],
                      fields['param'], length,
                      fields['data'])
    computed_crc = crc16.bit_by_bit_fast(msg)
    complete_msg = msg + struct.pack(MSG_CRC_FORMAT, computed_crc)
    return complete_msg

def decode_packet(data):
    fields = {}
    fmt = MSG_HEAD_FORMAT
    header = struct.unpack_from(fmt, data)
    fields['type'] = header[0]
    fields['subtype'] = header[1]
    fields['sender_id'] = header[2]
    fields['dest_id'] = header[3]
    fields['packet_num'] = header[4]
    fields['max_num'] = header[5]
    fields['param'] = header[6]
    length = header[7]
    offset = struct.calcsize(fmt)
    fmt = f"<{length}s"
    fields['data'] = struct.unpack_from(fmt, data, offset)[0]
    offset = offset + struct.calcsize(fmt)
    fields['crc'] = struct.unpack_from(MSG_CRC_FORMAT, data, offset)[0]
    fields['computed_crc'] = crc16.bit_by_bit_fast(data[0:offset])
    logging.debug(f"CRC computed on data packet {fields['computed_crc']:04x}, CRC Rx {fields['crc']:04x}")
    return fields
