import logging

from msg_types import * # pylint: disable=wildcard-import, unused-wildcard-import

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

def encode_start_packet(sender_address):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_START
    fields['subtype'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    return encode_packet(fields)

def encode_start_reponse(sender_address, num_packets):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_START
    fields['subtype'] = MSG_DIR_RESP
    fields['max_num'] = num_packets
    return encode_packet(fields)

def encode_ping_packet(sender_address, packet_num, msg_buffer):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_PING
    fields['subtype'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    fields['packet_num'] = packet_num
    fields['data'] = msg_buffer
    return encode_packet(fields)

def encode_resp_packet(sender_address, ping_fields):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_PONG
    fields['subtype'] = MSG_DIR_RESP
    fields['max_num'] = ping_fields['max_num']
    fields['packet_num'] = ping_fields['packet_num']
    fields['data'] = ping_fields['data']
    return encode_packet(fields)

def encode_nack_packet(sender_address, expected, packet_num):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_NACK
    fields['subtype'] = expected
    fields['packet_num'] = packet_num
    return encode_packet(fields)

def encode_done_packet(sender_address, packets_sent):
    fields = init_packet_fields(sender_address)
    fields['type'] = MSG_TYPE_DONE
    fields['subtype'] = MSG_DIR_OUT
    fields['max_num'] = MSG_MAX_PACKETS
    fields['packet_num'] = packets_sent
    return encode_packet(fields)

def valid_start_packet(packet):
    logging.debug(f"    valid_start_packet({packet})")
    # first, validate CRC is good!
    if packet['crc'] != packet['computed_crc']:
        return False
    # second, subtype
    if packet['subtype'] != MSG_DIR_OUT:
        return False
    if packet['type'] != MSG_TYPE_START:
        return False
    return True
