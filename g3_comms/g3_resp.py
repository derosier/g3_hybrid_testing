import logging
import struct

class G3Resp():
    g3_id = 0xFE  # this is not used in the doc
    g3_name = 'UNKNOWN'
    def __init__(self):
        self.callback = None
        self.cb_context = None
        self.raw_msg = b''
        self.raw_fields = b''
        self.fields = {}

    def decode(self, msg):
        self.raw_msg = msg
        self.fields['error_code'] = struct.unpack_from("<B", msg['data'])[0]

    def pr_decode(self):
        logging.debug(f'Msg {self.g3_name} (0x{self.g3_id:02x}): {self.fields}')

    def set_hook(self, callback, context):
        logging.debug(f'{self.g3_name} setting callback to {context}.{callback}')
        self.callback = callback
        self.cb_context = context

    def call_hook(self):
        if self.callback is not None:
            self.callback(self.cb_context, self.g3_name, self.fields)

class HWResetResp(G3Resp):
    g3_id = 0x01
    g3_name = 'HOSTIF-HWRESET'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<B", msg['data'], 1)
        self.raw_fields = raw_fields
        if raw_fields[0] == 1:
            self.fields['security_code'] = 'get/set'
        elif raw_fields[0] == 2:
            self.fields['security_code'] = 'all'
        else:
            self.fields['security_code'] = 'none'

class DBGToolResp(G3Resp):
    g3_id = 0x15
    g3_name = 'HOSTIF-DBGTOOL'
    def decode(self, msg):
        super().decode(msg)
        raw_fields = struct.unpack_from("<IIIQIBBBBBHH", msg['data'], 1)
        self.raw_fields = raw_fields
        self.fields['g3info'] = raw_fields[0]
        self.fields['lib_version'] = raw_fields[1]
        self.fields['rte_version'] = raw_fields[2]
        self.fields['mac'] = raw_fields[3]
        self.fields['spi_flash_id'] = raw_fields[4]
        self.fields['uart'] = raw_fields[5]
        self.fields['led'] = raw_fields[6]
        if raw_fields[7] == 0x00:
            self.fields['platform'] = 'INVALID'
        elif raw_fields[7] == 0x01:
            self.fields['platform'] = 'STCOMET/STCOM'
        elif raw_fields[7] == 0x02:
            self.fields['platform'] = 'ST8500'
        elif raw_fields[7] == 0xFF:
            self.fields['platform'] = 'none'
        else:
            self.fields['platform'] = 'UNKNOWN 0x[raw_fields[7]:02x]'
        self.fields['rf_connect'] = raw_fields[8]
        self.fields['platform_mode'] = raw_fields[9]
        self.fields['pan_id'] = raw_fields[10]
        self.fields['short_id'] = raw_fields[11]

    def pr_decode(self):
        print(f'Reply {self.g3_name}: {self.fields}')
