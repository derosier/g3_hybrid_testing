import logging

msg_decode_list = []

def decodeMsg(msg):
    if msg is None:
        return
    logging.debug(f"decodeMsg raw: {msg}")
    for decoder in msg_decode_list:
        if msg['cmd'] == decoder.g3_id:
            logging.debug("Found supported message")
            decoder.decode(msg)
            decoder.pr_decode()
            break
