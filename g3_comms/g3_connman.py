import logging
import argparse # for Namespace object
import binascii

import g3_comms.g3_tx
import g3_comms.g3_cmd
import g3_comms.g3_msgs

class ConnMan():
    MAX_CONN = 0xA
    SELF_ID_MSGS = ('G3BOOT-DEV-START', 'HOSTIF-DBGTOOL')
    def __init__(self, msg_list, subparsers=None):
        self.msg_list = msg_list
        if subparsers:
            self.parser = self._add_parser(subparsers)
        # connections data structure is a dictonary where the connection id is the key
        # and each connection is represented by a dictionary with the following elements:
        #    {remote_addr, remote_port, local_port}
        #    Note that addresses are short IDs, we create IPv6 on the fly as necesary
        self.connections = {}
        # 0xffff is used in the firmware for unassigned. init to those
        self.my_short_address = 0xffff
        self.pan = 0xffff
        self.mac = b''
        self.initialized = False

    # internal functions and callbacks
    def _add_parser(self, subparsers):
        parser = subparsers.add_parser('connman', help='Commands for the connection manager')
        self.subparsers = parser.add_subparsers(dest='conncmd')
        self.subparsers.add_parser('info', help="Print internal information")
        self.subparsers.add_parser('list', help="List all connections")
        self.subparsers.add_parser('clear', help="Clear all connections")
        self.subparsers.add_parser('reload', help="Reset internal state and reload from board")
        self.subparsers.add_parser('zeroaddr', help="debug to set shortid to zero")
        newparser = self.subparsers.add_parser('new', help="Create a new connection")
        newparser.add_argument('--addr',  type=int, help='Short address, 16 bit')
        newparser.add_argument('--port', type=int, default=0, help='Remote port')
        newparser.add_argument('--local', type=int, default=0, help='Local port')
        delparser = self.subparsers.add_parser('del', help="Remove a connection")
        delparser.add_argument('connid',  type=int, help='Connection ID to remove. Must be between 0 and 10')
        return parser

    # Need to run setup before this is used, but it can't be part of the __init__() because if
    # we set the hooks where we setup parsers, the logger is configured weird. So moving this
    # fixes that problem. Also, we need an open serial device to get the data. The final requirement
    # is that the rx_thread must be running because we actually run commands from this function.
    def init_setup(self, device):
        if self.initialized:
            logging.error("Called ConnMan.init_setup twice.")
            return
        # Setup the Rx messages to call the call-back and notify us of pan and short id
        # changes.
        for msg in self.msg_list:
            for id_msg in ConnMan.SELF_ID_MSGS:
                if msg.g3_name == id_msg:
                    msg.set_hook(self._info_callback, self)
        self.req_info(device)
        self.load_all_connections(device)
        self.initialized = True

    # The callback is called from the received message hook and because of the way it is done
    # the first parameter will be the actual Resp object. We can ignore this. The next arguments:
    #    self - This is the context set when the hook is set and should be our actual real 'self'
    #    name - The name of the message rx, which would be G3Resp.g3_name
    #    fields - the parsed fields from the message
    def _info_callback(_, self, name, fields): # pylint: disable=no-self-argument
        logging.debug(f"ConnMan._info_callback({self}, {name}, {fields})")
        if name in ConnMan.SELF_ID_MSGS:
            self.my_short_address = fields['short_id']
            self.pan = fields['pan_id']
        if name in ('HOSTIF-DBGTOOL'):
            self.mac = fields['mac']

    # data access and helper methods
    def _add_conn(self, connid, d_short_addr, d_port, l_port):
        self.connections[connid] = {'remote_addr':d_short_addr, 'remote_port':d_port, 'local_port': l_port}

    def _del_conn(self, connid):
        try:
            del self.connections[connid]
        except KeyError:
            logging.error(f"Unable to delete connection id {connid}, not found.")

    def _clear_conn(self):
        self.connections.clear()

    def find_free_conn(self):
        for i in range(0,ConnMan.MAX_CONN+1):
            if i not in self.connections:
                return i
        logging.warning("All connections are consumed")
        return None

    def valid_connection_fields(self, fields):
        try:
            return bool(fields['remote_addr'] != bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00") or fields['remote_port'] != 0 or fields['local_port'] != 0)
        except KeyError:
            return False

    # operation methods
    def req_info(self, device):
        # Set the connection
        dbgtool_cmd = g3_comms.g3_cmd.DBGToolCmd()
        dbgtool_cmd.parse_args(None)
        # still need to setup_rx() because the wait part of send-and-wait needs it.
        dbgtool_cmd.setup_rx(self.msg_list)
        g3_comms.g3_tx.send_and_wait(device, dbgtool_cmd)
        dbgtool_cmd.clean_rx(self.msg_list)

    def get_connection(self, device, connid):
        args = argparse.Namespace()
        args.connid = connid
        getconn_cmd = g3_comms.g3_cmd.UDPConnGetCmd()
        getconn_cmd.parse_args(args)
        # still need to setup_rx() because the wait part of send-and-wait needs it.
        getconn_cmd.setup_rx(self.msg_list)
        fields = g3_comms.g3_tx.send_and_wait(device, getconn_cmd)
        getconn_cmd.clean_rx(self.msg_list)
        return fields

    # note that addr is the short-address.  This is converted to an ipv6 when we send the message
    def set_connection(self, device, connid, addr, remote_port, local_port): #pylint: disable=too-many-arguments
        args = argparse.Namespace()
        args.addr = addr
        args.rport = remote_port
        args.port = local_port
        args.connid = connid
        # Set the connection
        udp_conn_cmd = g3_comms.g3_cmd.UDPConnSetCmd()
        udp_conn_cmd.parse_args(args)
        udp_conn_cmd.setup_rx(self.msg_list)
        fields = g3_comms.g3_tx.send_and_wait(device, udp_conn_cmd)
        udp_conn_cmd.clean_rx(self.msg_list)
        return fields

    def load_all_connections(self, device):
        for i in range(0,ConnMan.MAX_CONN+1):
            conn = self.get_connection(device, i)
            if not conn:
                logging.warning("Timeout loading all connections, halting.")
                break
            if self.valid_connection_fields(conn):
                self._add_conn(i, g3_comms.g3_msgs.hi_short_addr_from_ipaddr(conn['remote_addr']),
                                 conn['remote_port'], conn['local_port'])

    # cli commands
    def print_conn_header(self):
        print(f"id | dest addr | {'dest ipv6 address':^39} | dest port | local port")

    def print_conn(self, conn):
        d_s_a = self.connections[conn]['remote_addr']
        d_p = self.connections[conn]['remote_port']
        l_p = self.connections[conn]['local_port']
        d_ip = binascii.hexlify(g3_comms.g3_msgs.hi_ipv6_set_ipaddr(self.connections[conn]['remote_addr'], self.pan), ':', 2).decode('utf-8')
        print(f"{conn:2} | {d_s_a:9} | {d_ip:39} | {d_p:9} | {l_p:10}")

    def print_conn_list(self):
        print("Active connections")
        print("==================")
        self.print_conn_header()
        for conn in self.connections: # pylint: disable=consider-using-dict-items
            self.print_conn(conn)

    def print_info(self):
        print("Internal information")
        print("====================")
        print(f"short address: {self.my_short_address}")
        print(f"pan: {self.pan}")
        print(f"mac: {self.mac}")

    def new_conn(self, device, addr, remote_port, local_port):
        new_id = self.find_free_conn()
        if new_id is not None:
            fields = self.set_connection(device, new_id, addr, remote_port, local_port)
            if fields['status'] != 'G3_SUCCESS':
                logging.error(f"Error when setting connection, status: {fields['status']}")
                new_id = None
            else:
                self._add_conn(new_id, addr, remote_port, local_port)
        else:
            logging.warning("Unable to add new connection.")
        return new_id

    def reload_connections(self, device):
        self.my_short_address = 0xffff
        self.pan = 0xffff
        self.mac = b''
        self.connections.clear()
        self.req_info(device)
        self.load_all_connections(device)

    def del_connection(self, device, connid):
        if not 0 <= connid <= ConnMan.MAX_CONN:
            logging.warning("Invalid connection id to delete {connid}")
            return
        connection = self.get_connection(device, connid)
        if not self.valid_connection_fields(connection):
            # already clear, ignore this one
            return
        addr = -1
        remote_port = 0
        local_port = 0
        fields = self.set_connection(device, connid, addr, remote_port, local_port)
        if fields['status'] != 'G3_SUCCESS':
            logging.error(f"Error when deleting connection, status: {fields['status']}")
        else:
            self._del_conn(connid)

    def clear_connections(self, device):
        # This is very expensive, because at the very least we'll request all connections!
        for i in range(0,ConnMan.MAX_CONN+1):
            self.del_connection(device, i)
        self.connections.clear()

    def do_cmds(self, device, args):
        if args.conncmd in ('list', 'l'):
            self.print_conn_list()
        elif args.conncmd in ('info'):
            self.print_info()
        elif args.conncmd in ('new', 'n'):
            self.new_conn(device, args.addr, args.port, args.local)
        elif args.conncmd in ('zeroaddr'):
            self.my_short_address = 0
        elif args.conncmd in ('reload'):
            self.reload_connections(device)
        elif args.conncmd in ('del'):
            self.del_connection(device, args.connid)
        elif args.conncmd in ('clear'):
            self.clear_connections(device)
