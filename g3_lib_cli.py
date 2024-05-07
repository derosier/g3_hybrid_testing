import logging
import pprint

from g3_comms import g3_lib
from g3_comms.g3_msgs import parse_data
import g3_comms.g3_consts

# HOWTO: add new commands
#
# When adding new commands, add a new subparser in _add_parser(). If there's no arguments, there's
# no need to "keep" a handle to the subparser being added. After the command is added, it's
# *critical* to add the command name to `implmented_cmds`. Without this step, g3_cli will not
# recognize this as a command and dispatch it.
#
# Implementation note -> I tried to find a programatic way to generate this list, but it was
# non-trivial and it's easier to maintain this list than take the time to come up with a solution.
implmented_cmds = ['get-panid', 'get-sa', 'get-nvm-help', 'get-nvm',
                   'set-nvm-psk', 'set-nvm-pskidx', 'set-nvm-panid', 'set-nvm-sa', 'media',
                   'get-plc-txpwr', 'set-plc-txpwr', 'get-plc-ackpwr', 'set-plc-ackpwr']

class LibCLI():
    def __init__(self, subparsers):
        if subparsers:
            self._add_parser(subparsers)

    # internal functions and callbacks
    def _add_parser(self, subparsers):
        subparsers.add_parser('get-panid', help='Get the currently running PANID')
        subparsers.add_parser('get-sa', help='Get the currently running Short Address')
        subparsers.add_parser('get-nvm-help', help='Get a field from NVM')
        getnvmparser = subparsers.add_parser('get-nvm', help='Get a field from NVM')
        getnvmparser.add_argument('field', help="Name of the field to get")
        pskparser = subparsers.add_parser('set-nvm-psk', help='Set the PSK in the NVM')
        pskparser.add_argument('psk', help="16 byte PSK as hex with '0x' in little endian byte order")
        pskparser.add_argument('--idx', type=int, default=0, help="Index of PSK slot to set, 0 or 1")
        pskidxparser = subparsers.add_parser('set-nvm-pskidx', help='Set the active PSK in the NVM')
        pskidxparser.add_argument('idx', type=int, help="Set PSK index, 0 or 1")
        panparser = subparsers.add_parser('set-nvm-panid', help='Set the PANID NVM')
        panparser.add_argument('panid', type=int, help="PANID to set in the NVM")
        saparser = subparsers.add_parser('set-nvm-sa', help='Set the Short Address NVM')
        saparser.add_argument('sa', type=int, help="Short Address to set in the NVM")
        mediaparser = subparsers.add_parser('media', help='Get or change the media')
        # weird, but in order for a default to work with choices, need the nargs and const parameters.
        # https://stackoverflow.com/questions/40324356/python-argparse-choices-with-a-default-choice
        mediaparser.add_argument("mediatype", default='get', nargs='?', const='get', choices=('all', 'plc', 'rf', 'get'), help="Select media to use.")
        subparsers.add_parser('get-plc-txpwr', help='Get the maximum TX power for the PLC')
        plctxpwr_parser = subparsers.add_parser('set-plc-txpwr', help='Set the maximum TX power for the PLC')
        plctxpwr_parser.add_argument('plctxpwr', type=int, choices=range(0, 0x21), help="TX power integer <= 32")
        subparsers.add_parser('get-plc-ackpwr', help='Get the maximum TX power for the PLC')
        plctxpwr_parser = subparsers.add_parser('set-plc-ackpwr', help='Set the maximum TX power for the PLC')
        plctxpwr_parser.add_argument('plcackpwr', type=int, choices=range(0, 0x21), help="TX power integer <= 32")

    def list_nvm_fields(self):
        print("NVM field names for PLC:")
        pprint.pprint(list(g3_comms.g3_consts.NVM_PLC_OFFSETS))

    def do_cmds(self, device, args): # pylint: disable=too-many-branches
        if args.cmd == 'get-panid':
            pan = g3_lib.get_panid(device)
            print(f"PAN Id: {pan}")
        elif args.cmd == 'get-sa':
            sa = g3_lib.get_shortid(device)
            print(f"Short Address: {sa}")
        elif args.cmd == 'get-nvm-help':
            self.list_nvm_fields()
        elif args.cmd == 'get-nvm':
            data = g3_lib.get_nvm(device, 'plc', args.field)
            print(f"{args.field}: {data}")
        elif args.cmd == 'set-nvm-psk':
            psk = parse_data(args.psk)
            (ok, status) = g3_lib.set_nvm_psk(device, args.idx, psk)
            if ok:
                print(f"Set PSK {args.idx} OK")
            else:
                print(f"Unable to set PSK: {status}")
        elif args.cmd == 'set-nvm-pskidx':
            (ok, status) = g3_lib.set_nvm_psk_index(device, args.idx)
            if ok:
                print(f"Set PSK Index to {args.idx} OK")
            else:
                print(f"Unable to set PSK Index: {status}")
        elif args.cmd == 'set-nvm-panid':
            (ok, status) = g3_lib.set_nvm_panid(device, args.panid)
            if ok:
                print(f"Set PANID {args.panid} OK")
            else:
                print(f"Unable to set PANID: {status}")
        elif args.cmd == 'set-nvm-sa':
            (ok, status) = g3_lib.set_nvm_shortaddr(device, args.sa)
            if ok:
                print(f"Set Short Address {args.sa} OK")
            else:
                print(f"Unable to set Short Address: {status}")
        elif args.cmd == 'media':
            if args.mediatype == 'get':
                (media_ok, got_media) = g3_lib.get_media(device)
            elif args.mediatype == 'rf':
                (media_ok, _) = g3_lib.set_media(device, g3_comms.g3_consts.G3_MEDIA_RF)
            elif args.mediatype == 'plc':
                (media_ok, _) = g3_lib.set_media(device, g3_comms.g3_consts.G3_MEDIA_PLC)
            elif args.mediatype == 'all':
                (media_ok, _) = g3_lib.set_media(device, g3_comms.g3_consts.G3_MEDIA_ALL)

            if media_ok:
                if args.mediatype == 'get':
                    try:
                        print(f"Media is set to {g3_comms.g3_consts.G3_MEDIA_STRING[got_media]}")
                    except KeyError:
                        print(f"Unknown media setting {got_media}")
            else:
                print("Error getting or setting media")
        elif args.cmd == 'get-plc-txpwr':
            pwr = g3_lib.get_plc_txpwr(device)
            print(f"PLC max TX Power: {pwr}")
        elif args.cmd == 'set-plc-txpwr':
            pwr_hexstr = '0x' + f'{args.plctxpwr:02x}'
            (ok, status) = g3_lib.set_plc_txpwr(device, pwr_hexstr)
            if ok:
                print(f"PLC max TX Power {args.plctxpwr} OK")
            else:
                print(f"Unable to set PLC max TX Power: {status}")
        elif args.cmd == 'get-plc-ackpwr':
            pwr = g3_lib.get_plc_ackpwr(device)
            print(f"PLC max ACK Power: {pwr}")
        elif args.cmd == 'set-plc-ackpwr':
            pwr_hexstr = '0x' + f'{args.plcackpwr:02x}'
            (ok, status) = g3_lib.set_plc_ackpwr(device, pwr_hexstr)
            if ok:
                print(f"PLC max ACK Power {args.plcackpwr} OK")
            else:
                print(f"Unable to set PLC max ACK Power: {status}")
        else:
            logging.error(f"Incorrect G3Lib command {args.cmd}")
