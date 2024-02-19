import struct

from msg_types import * # pylint: disable=wildcard-import, unused-wildcard-import

# MSG_TYPE_LC_REQUEST_ID
# Use this packet to request the UUID and other identification information from a node.
def encode_lc_request_id_packet(sender_addr, dest_addr):
    fields = init_packet_fields(sender_addr, dest_addr)
    fields['type'] = MSG_TYPE_LC_REQUEST_ID
    return encode_packet(fields)

# MSG_TYPE_LC_RESPOND_ID
# Use this packet to respond to an identification request by the MSG_TYPE_LC_REQUEST_ID message.
# It contains the following information encoded in the data:
#  G3 EUI-64
#  Ethernet MAC EUI-48
#  Module UUID in [length][data]
#  Key in [length][data]
#  length is 16 bit
def encode_lc_response_id_packet(sender_addr, dest_addr, id_info):
    fields = init_packet_fields(sender_addr, dest_addr)
    fields['type'] = MSG_TYPE_LC_RESPOND_ID
    uuid_len = len(id_info['uuid'])
    key_len = len(id_info['key'])
    fmt = f"<Q6sH{uuid_len}sH{key_len}s"
    fields['data'] = struct.pack(fmt, id_info['g3_mac'], id_info['eth_mac'],
                                 uuid_len, id_info['uuid'].encode('utf-8'), key_len, id_info['key'].encode('utf-8'))
    return encode_packet(fields)

# It is expected that the generic `decode_packet()` be called first, and then you use this to
# decode the fields['data'] field.
def decode_lc_response_id_data(data):
    fields = {}
    offset = 0
    fmt = "<Q6sH"
    rawdata = struct.unpack_from(fmt, data)
    fields['g3_mac'] = rawdata[0]
    fields['eth_mac'] = rawdata[1]
    uuid_len = rawdata[2]
    offset = offset + struct.calcsize(fmt)
    fmt = f"<{uuid_len}sH"
    rawdata = struct.unpack_from(fmt, data, offset)
    fields['uuid'] = rawdata[0]
    key_len = rawdata[1]
    offset = offset + struct.calcsize(fmt)
    fmt = f"<{key_len}s"
    rawdata = struct.unpack_from(fmt, data, offset)
    fields['key'] = rawdata[0]
    return fields

# MSG_TYPE_LC_LCN_INFORMATION
# This packet sends the network information necessary to configure a network. We always identify
# networks, by the 'panid', so we'll send it in the 'param' field even though that's redundant
# with a field in the network information.
# 'data' format is:
# H  | PAN ID
# Q  | Session key timestamp
# H  | Key length
# Xs | Session Key data
def encode_lc_network_information_packet(sender_addr, dest_addr, lcn_info):
    fields = init_packet_fields(sender_addr, dest_addr)
    fields['type'] = MSG_TYPE_LC_LCN_INFORMATION
    fields['param'] = lcn_info['pan']
    key_len = len(lcn_info['session_key'])
    fmt = f"<HdH{key_len}s"
    fields['data'] = struct.pack(fmt, lcn_info['pan'], lcn_info['key_created'], key_len,
                                      lcn_info['session_key'])
    return encode_packet(fields)

# It is expected that the generic `decode_packet()` be called first, and then you use this to
# decode the fields['data'] field.
def decode_lc_network_information_data(data):
    fields = {}
    offset = 0
    fmt = "<HdH"
    rawdata = struct.unpack_from(fmt, data)
    fields['pan'] = rawdata[0]
    fields['key_created'] = rawdata[1]
    key_len = rawdata[2]
    offset = offset + struct.calcsize(fmt)
    fmt = f"<{key_len}s"
    rawdata = struct.unpack_from(fmt, data, offset)
    fields['session_key'] = rawdata[0]
    return fields

# MSG_TYPE_LC_LCN_INFO_CONFIRM
# Use this packet to confirm that it received the network information for the network
# identified by 'panid'.
def encode_lc_lcn_comfirm_packet(sender_addr, dest_addr, panid):
    fields = init_packet_fields(sender_addr, dest_addr)
    fields['type'] = MSG_TYPE_LC_LCN_INFO_CONFIRM
    fields['param'] = panid
    return encode_packet(fields)

# MSG_TYPE_LC_SWITCH_NETWORK
# Use this packet to request a node to switch to a network that we identify by the 'panid'.
def encode_lc_switch_network_packet(sender_addr, dest_addr, panid):
    fields = init_packet_fields(sender_addr, dest_addr)
    fields['type'] = MSG_TYPE_LC_SWITCH_NETWORK
    fields['param'] = panid
    return encode_packet(fields)

# MSG_TYPE_LC_PAIR_CLEAR
# Use this packet to ask a paired node to clear its LCN pairing. To avoid random accidents, we
# put a 'key' value into the parameter field that should be checked.
def encode_lc_pair_clear_packet(sender_addr, dest_addr, key):
    fields = init_packet_fields(sender_addr, dest_addr)
    fields['type'] = sender_addr
    fields['param'] = key
    return encode_packet(fields)
