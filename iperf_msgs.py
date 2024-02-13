import logging
import struct

from g3_comms.g3_crc import crc16

MSG_TYPE_NONE  = 0x00
MSG_TYPE_START = 0x01
MSG_TYPE_DONE = 0x02
MSG_TYPE_PING = 0x03
MSG_TYPE_PONG = 0x04
MSG_TYPE_NACK = 0x84
MSG_TYPE_ERROR = 0xFF
MSG_TYPE_INVALID = 0xFF

MSG_DIR_NONE = 0x00
MSG_DIR_OUT = 0x01
MSG_DIR_RESP = 0x02

MSG_MAX_PACKETS = 10000

# 1200 bytes below
# There's a MTU limit for the UDP packets of 1270.
MSG_LEN = 1200
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
def init_packet_fields(sender_address):
    fields = {}
    fields['type'] = MSG_TYPE_NONE
    fields['direction'] = MSG_DIR_NONE
    fields['sender_id'] = sender_address
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

def encode_start_packet(sender_address):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_START
    fields['direction'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    return encode_packet(fields)

def encode_start_reponse(sender_address, num_packets):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_START
    fields['direction'] = MSG_DIR_RESP
    fields['max_num'] = num_packets
    return encode_packet(fields)

def encode_ping_packet(sender_address, packet_num, msg_buffer):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_PING
    fields['direction'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    fields['packet_num'] = packet_num
    fields['data'] = msg_buffer
    return encode_packet(fields)

def encode_resp_packet(sender_address, ping_fields):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_PONG
    fields['direction'] = MSG_DIR_RESP
    fields['max_num'] = ping_fields['max_num']
    fields['packet_num'] = ping_fields['packet_num']
    fields['data'] = ping_fields['data']
    return encode_packet(fields)

def encode_nack_packet(sender_address, expected, packet_num):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_NACK
    fields['direction'] = expected
    fields['packet_num'] = packet_num
    return encode_packet(fields)

def encode_done_packet(sender_address, packets_sent):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_DONE
    fields['direction'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    fields['packet_num'] = packets_sent
    return encode_packet(fields)

def valid_start_packet(packet):
    logging.debug(f"    valid_start_packet({packet})")
    # first, validate CRC is good!
    if packet['crc'] != packet['computed_crc']:
        return False
    # second, direction
    if packet['direction'] != MSG_DIR_OUT:
        return False
    if packet['type'] != MSG_TYPE_START:
        return False
    return True
