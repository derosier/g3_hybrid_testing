import logging
import g3_comms.g3_consts as G3C

msg_decode_list = []
msg_cmds = {}
print_msg = False

def decodeMsg(msg):
    if msg is None:
        return
    logging.debug(f"decodeMsg raw: {msg}")
    for decoder in msg_decode_list:
        if msg['cmd'] == decoder.g3_id:
            logging.debug("Found supported message")
            decoder.valid_msg = msg['rx_status'] == 'OK'
            if decoder.valid_msg:
                decoder.decode(msg)
                if print_msg:
                    decoder.pr_decode()
            else:
                decoder.raw_msg = msg
            decoder.call_hook()
            break
    else: # no break
        logging.warning(f"Message recived but unknown; Raw: {msg}")

def parse_data(argdata):
    if argdata[:2] == '0x':
        data = bytes.fromhex(argdata[2:])
    else:
        data = bytes(argdata, 'utf-8')
    return data

def parse_over(argdata, maxvalue):
    isover = False
    if isinstance(maxvalue, str):
        maxvalue = int(maxvalue, 16)
    if argdata[:2] == '0x':
        data = int(argdata, 16)
        if data > maxvalue:
            isover = True
    else:
        raise TypeError
    return isover

def parse_under(argdata, minvalue):
    isunder = False
    if isinstance(minvalue, str):
        minvalue = int(minvalue, 16)
    if argdata[:2] == '0x':
        data = int(argdata, 16)
        if data < minvalue:
            isunder = True
    else:
        raise TypeError
    return isunder

def parse_equal(argdata, value):
    isequal = False
    if isinstance(value, str):
        value = int(value, 16)
    if argdata[:2] == '0x':
        data = int(argdata, 16)
        if data == value:
            isequal = True
    else:
        raise TypeError
    return isequal

def hi_ipv6_set_ipaddr(short_addr, pan_id=G3C.G3_DEFAULT_PAN):
    logging.debug(f"encoding ipv6 address from short {short_addr} on pan {pan_id}")
    if short_addr < 0:
        logging.debug("short_addr < 0, encoding a zero ipv6")
        return bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
    ipv6 = bytes.fromhex("FE 80 00 00 00 00 00 00")
    ipv6 = ipv6 + pan_id.to_bytes(2, "big")[0:1]
    ipv6 = ipv6 + pan_id.to_bytes(2, "big")[1:2]
    ipv6 = ipv6 + bytes.fromhex("00 FF FE 00")
    ipv6 = ipv6 + short_addr.to_bytes(2, "big")[0:1]
    ipv6 = ipv6 + short_addr.to_bytes(2, "big")[1:2]
    logging.debug(f"encoded ipv6 address {ipv6}")
    return ipv6

def hi_short_addr_from_ipaddr(ipv6):
    logging.debug(f"decoding short_addr from ipv6 address {ipv6}")
    if ipv6 == bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"):
        return -1
    short_addr = int.from_bytes(ipv6[14:], "big")
    logging.debug(f"decoded short_addr {short_addr}")
    return short_addr

def hi_pan_from_ipaddr(ipv6):
    logging.debug(f"decoding pan from ipv6 address {ipv6}")
    if ipv6 == bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"):
        return -1
    pan = int.from_bytes(ipv6[8:10], "big")
    logging.debug(f"decoded pan {pan}")
    return pan

def print_callbacks(msg_list, prefix=''):
    for msg in msg_list:
        print(f"{prefix}{msg.g3_name}: {msg.callbacks}")
