# Useful constants maps

# Table 12. G3 platform modes. pg 15
G3_MODE = {
    'phy': 0,
    'mac': 1,
    'adp': 2,
    'boot': 3,
    'ipv6_adp': 4,
    'ipv6_boot': 5,
}

# reverse lookup for Table 12
G3_MODE_R = {y: x for x, y in G3_MODE.items()}

# Table 24. Error Code field. pg 40
G3_ERROR = {
    0x00: 'Success',
    0x01: 'Wrong CRC on received command',
    0x02: 'Wrong Synchro field',
    0x03: 'Wrong Length field',
    0x04: 'Wrong Command ID field',
    0x05: 'HW reset is being to be performed by internal HW watchdog',
    0x06: 'HW reset is being to be performed due to an error in the RTE that cannot be recovered',
    0x07: 'HW reset is being to be performed due to the lack of activity in the RTE',
    0x08: 'Timeout Expired on received command',
    0x09: 'Wrong security mode',
    0x0A: 'Error on authentication',
    0x0B: 'Wrong command received in the current state',
    0x0C: 'Error occurred during initialization'
}

# Table 25. Status and results codes. pp 41-45
G3_RESULTS = {
    0x00: 'G3_SUCCESS',
    0x01: 'G3_WRONG_CRC',
    0x02: 'G3_WRONG_MSG_LEN',
    0x03: 'G3_WRONG_CMD_ID',
    0x04: 'G3_WRONG_MODE',
    0x05: 'G3_NOT_EXPECTED',
    0x06: 'G3_WRONG_STATE',
    0x07: 'G3_WRONG_TRX_STATE',
    0x08: 'G3_NOT_ACCEPTABLE',
    0x09: 'G3_WRONG_TX_POWER',
    0x0A: 'G3_WRONG_MOD_SCHEME',
    0x0B: 'G3_WRONG_MOD_TYPE',
    0x0C: 'G3_WRONG_PREEMPHASIS',
    0x0D: 'G3_WRONG_TONEMAP',
    0x0E: 'G3_WRONG_TONEMASK',
    0x0F: 'G3_WRONG_FCH',
    0x10: 'G3_WRONG_VALUE_LEN',
    0x11: 'G3_WRONG_TEST_MODE',
    0x12: 'G3_QUEUE_FULL',
    0x13: 'G3_DATA_LIMIT_REACHED',
    0x14: 'G3_RESERVERD_CMD_ID',
    0x15: 'G3_RTE_INTERFACE_TIMEOUT',
    0x16: 'G3_TEST_FAILED',
    0x17: 'G3_TEST_NOT_ACTIVE',
    0x18: 'G3_TEST_ALREADY_ACTIVE',
    0x19: 'G3_TEST_NOT_IMPLEMENTED',
    0x1A: 'G3_TEST_NOT_IDLE',
    0x1B: 'G3_TEST_NOT_ACCEPTABLE',
    0x1C: 'G3_FAILED',
    0x1D: 'G3_TX_BUSY',
    0x1E: 'G3_RX_BUSY',
    0x1F: 'G3_CS_IDLE',
    0x20: 'G3_CS_BUSY',
    0x21: 'G3_PREVIOUS_REQUEST_FAILED',
    0x22: 'G3_NO_INDICATION',
    0x23: 'G3_PLME_CS_CONF_TMR_EXP',
    0x24: 'G3_PLME_SET_TRX1_KO',
    0x25: 'G3_PLME_SET_TRX1_TMR_EXP',
    0x26: 'G3_PLME_SET_TRX2_KO',
    0x27: 'G3_PLME_SET_TRX2_TMR_EXP',
    0x28: 'G3_PLME_SET_TRX3_KO',
    0x29: 'G3_PLME_SET_TRX3_TMR_EXP',
    0x2A: 'G3_PLME_SET_KO',
    0x2B: 'G3_PLME_SET_TMR_EXP',
    0x2C: 'G3_PD_DATA_CONF_FAILED',
    0x2D: 'G3_PD_DATA_CONF_TMR_EXP',
    0x2E: 'G3_SEGMENT_DISCARDED',
    0x2F: 'G3_WRONG_VALUE',
    0x30: 'G3_WRONG_ATTR_NUM',
    0x31: 'G3_WRONG_DT',
    0x32: 'G3_ACTION_NOT_IMPLEMENTED',
    0x33: 'G3_ACTION_UNKNOWN',
    0x34: 'G3_DT_ACKREQ_MISMATCH',
    0x35: 'G3_PLME_GET_CONF_TMR_EXP',
    0x36: 'G3_PD_ACK_CONF_FAILED',
    0x37: 'G3_PD_ACK_REQ_TMR_EXP',
    0x38: 'G3_RX_NACK',
    0x39: 'G3_ERR_SEG_COUNT',
    0x3A: 'G3_ERR_SEG_ID',
    0x3B: 'G3_ERR_SEG_CC',
    0x3C: 'G3_ERR_SEG_AR',
    0x3D: 'G3_TX_QUEUE_TO_SHORT',
    0x3E: 'G3_NO_EARLIER_SEG',
    0x3F: 'G3_ERR_SEQ_NUM',
    0x40: 'G3_INTERNAL_ERROR',
    0x41: 'G3_SEGMENT_TOO_LATE',
    0x42: 'G3_WRONG_TWORSBLOCKS',
    0x43: 'G3_NOT_IDLE',
    0x44: 'G3_WRONG_BAND',
    0x45: 'G3_NOT_SUPPORTED_BAND',
    0x46: 'G3_NOT_ACCEPTABLE_LEN',
    0x47: 'G3_PLC_DISABLED',
    0x48: 'G3_PHY_NOT_READY',
    0x49: 'G3_WRONG_LEN',
    0x4A: 'G3_BANDSETOK_ATTRSETKO',
    0x60: 'G3_BUSY',
    0x61: 'G3_INVALID_IPv6_FRAME',
    0x62: 'G3_INVALID_QOS',
    0x63: 'G3_BAD_CCM_OUTPUT',
    0x64: 'G3_ROUTE_ERROR',
    0x65: 'G3_BT_TABLE_FULL',
    0x66: 'G3_FRAME_NOT_BUFFERED',
    0x67: 'G3_STARTUP_FAILURE',
    0x68: 'G3_NOT_PERMITTED',
    0x69: 'G3_UNKNOWN_DEVICE',
    0x6A: 'G3_SENDING_DATA_ERROR',
    0x6B: 'G3_PARAMETER_ERROR',
    0x6C: 'G3_WRONG_DEVICE_TYPE',
    0x6D: 'G3_ADD_EVENT_ERROR',
    0x6E: 'G3_GET_EVENT_ERROR',
    0x6F: 'G3_MALLOC_FAIL',
    0x70: 'G3_RTEIPC_ERROR',
    0x71: 'G3_WRONG_MEDIA_TYPE',
    0x72: 'G3_UNAVAILABLE_MEDIA_TYPE',
    0x73: 'G3_DUTY_CYCLE_ERR',
    0x74: 'G3_DISABLED_MEDIA_TYPE',
    0x75: 'G3_RF_DISABLED',
    0xDB: 'G3_COUNTER_ERROR',
    0xDC: 'G3_IMPROPER_KEY_TYPE',
    0xDD: 'G3_IMPROPER_SECURITY_LEVEL',
    0xDE: 'G3_UNSUPPORTED_LEGACY',
    0xDF: 'G3_UNSUPPORTED_SECURITY',
    0xE0: 'G3_BEACON_LOSS',
    0xE1: 'G3_CHANNEL_ACCESS_FAILURE',
    0xE2: 'G3_DENIED',
    0xE3: 'G3_DISABLE_TRX_FAILURE',
    0xE4: 'G3_SECURITY_ERROR',
    0xE5: 'G3_FRAME_TOO_LONG',
    0xE6: 'G3_INVALID_GTS',
    0xE7: 'G3_INVALID_HANDLE',
    0xE8: 'G3_INVALID_PARAMETER',
    0xE9: 'G3_NO_ACK',
    0xEA: 'G3_NO_BEACON',
    0xEB: 'G3_NO_DATA',
    0xEC: 'G3_NO_SHORT_ADDRESS',
    0xED: 'G3_OUT_OF_CAP',
    0xEE: 'G3_PAN_ID_CONFLICT',
    0xEF: 'G3_REALIGNMENT',
    0xF0: 'G3_TRANSACTION_EXPIRED',
    0xF1: 'G3_TRANSACTION_OVERFLOW',
    0xF2: 'G3_TX_ACTIVE',
    0xF3: 'G3_UNAVAILABLE_KEY',
    0xF4: 'G3_UNSUPPORTED_ATTRIBUTE',
    0xF5: 'G3_INVALID_ADDRESS',
    0xF6: 'G3_ON_TIME_TOO_LONG',
    0xF7: 'G3_PAST_TIME',
    0xF8: 'G3_TRACKING_OFF',
    0xF9: 'G3_INVALID_INDEX',
    0xFA: 'G3_LIMIT_REACHED',
    0xFB: 'G3_READ_ONLY',
    0xFC: 'G3_SCAN_IN_PROGRESS',
    0xFD: 'G3_SUPERFRAME_OVERLAP'
}

G3LIB_VALUE_FORMAT = {
    1: "<B",
    2: "<H",
    4: "<I",
}

G3LIB_SNIFFER_FRAMETYPE = {
    0x00: "PHY DATA",
    0x01: "PHY ACK",
    0x02: "MAC BEACON",
    0x03: "MAC DATA",
    0x04: "MAC CMD",
    0x05: "PHY RF",
    0x06: "MAC RF ACK",
    0xFF: "UNKNOWN"
}

# Decode tables for G3PHY-DATA.Indication
G3_PHY_MODTYPE = {
    0: "Robust",
    1: "xBPSK",
    2: "xQPSK",
    3: "x8PSK"
}

# reverse lookup for G3_PHY_MODTYPE
G3_PHY_MODTYPE_R = {y: x for x, y in G3_PHY_MODTYPE.items()}

G3_PHY_MODSCHEME = {
    0: "Differential",
    1: "Coherent"
}

# reverse lookup for G3_PHY_MODSCHEME
G3_PHY_MODSCHEME_R = {y: x for x, y in G3_PHY_MODSCHEME.items()}

G3_PHY_DT = {
    0x00: "SOF no response",
    0x01: "SOF ACK expected"
}

G3_PHY_RSBLOCKS = {
    0: "Two RS Blocks",
    1: "One RS Block"
}

#######################
# NVM stuff
# Table 44. NVM operation for HOSTIF-NVM Pg 54
NVM_OPP = {
    'erase': 0,
    'read': 1,
    'write': 2,
}

# reverse lookup for Table 44
NVM_OPP_R = {y: x for x, y in NVM_OPP.items()}

# Table 45. NVM sections for HOSTIF-NVM Pg 54
NVM_SECTION = {
    'gen': 1,
    'plc': 2,
    'plcc': 3,
    'rf': 4,
}

# reverse lookup for Table 44
NVM_SECTION_R = {y: x for x, y in NVM_SECTION.items()}

#######################
# PIB table values
#
# IDs are 4 byte integers
# Data values are strings, hex strings if integers

G3_LIB_PECHANNELCONFIG_ID = 0x00003202
G3_MEDIA_ALL = "0x0F000000"
G3_MEDIA_PLC = "0x03000000"
G3_MEDIA_RF = "0x0C000000"
