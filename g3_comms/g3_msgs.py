import logging

msg_decode_list = []
msg_cmds = {}

def decodeMsg(msg):
    if msg is None:
        return
    logging.debug(f"decodeMsg raw: {msg}")
    for decoder in msg_decode_list:
        if msg['cmd'] == decoder.g3_id:
            logging.debug("Found supported message")
            decoder.decode(msg)
            decoder.pr_decode()
            decoder.call_hook()
            break
    else: # no break
        print(f"Message recived but unknown; Raw: {msg}")

def hi_ipv6_set_ipaddr(short_addr, pan_id=30749):
    logging.debug(f"encoding ipv6 address from short {short_addr} on pan {pan_id}")
    ipv6 = bytes.fromhex("FE 80 00 00 00 00 00 00")
    ipv6 = ipv6 + pan_id.to_bytes(2, "big")[1:2]
    ipv6 = ipv6 + pan_id.to_bytes(2, "big")[0:1]
    ipv6 = ipv6 + bytes.fromhex("00 FF FE 00")
    ipv6 = ipv6 + short_addr.to_bytes(2, "big")[1:2]
    ipv6 = ipv6 + short_addr.to_bytes(2, "big")[0:1]
    logging.debug(f"encoded ipv6 address {ipv6}")
    return ipv6
