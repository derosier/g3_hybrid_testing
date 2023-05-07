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
