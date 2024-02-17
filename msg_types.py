MSG_TYPE_NONE  = 0x00

# Generic and iperf message types
MSG_TYPE_START = 0x01
MSG_TYPE_DONE = 0x02
MSG_TYPE_PING = 0x03
MSG_TYPE_PONG = 0x04

# local comms messages


# error or similar
MSG_TYPE_NACK = 0x84
MSG_TYPE_ERROR = 0xFF
MSG_TYPE_INVALID = 0xFF



# iperf direction constants
MSG_DIR_NONE = 0x00
MSG_DIR_OUT = 0x01
MSG_DIR_RESP = 0x02
