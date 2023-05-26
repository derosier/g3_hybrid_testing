#!/usr/bin/env python3

import logging
import argparse
import threading
import signal

import serial

import g3_comms.g3_rx
import g3_comms.g3_tx
import g3_comms.g3_msgs
from g3_comms import g3_resp
from g3_comms import g3_cmd

default_port="/dev/ttyACM0"

parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(dest='cmd')
parser.add_argument("-p", "--port", default=default_port, help=f"Serial port, default {default_port}")
parser.add_argument("-V", "--verbosity", default="INFO", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-d", "--dump", action="store_true", help="Dump all messages recieved, don't return after sending message")
parser.add_argument("-c", "--count", type=int, default=0, help="Number of times to repeat a command or to recieve messages")
parser.add_argument("-t", "--timeout", type=int, default=5, help="Command wait for response timeout, default 5 seconds.")
parser.add_argument("-i", "--interactive", action="store_true", help="Do an interactive cli session.")
parser.add_argument("-n", "--dryrun", action="store_true", help="Process but don't send messages.")

# Instantiate a global instance of every response we want to process on Rx
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.HWResetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.DBGToolResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3GetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3SetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.SWResetResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3SnifferInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3PhyData())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3PhyDataInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3PhyAck())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3PhyAckInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3PhyRf())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3PhyRfInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootSrvStartResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootSrvJoinInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootDevStartResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootDevPANSortInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootGetPSKInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.BootSrvSetPSKResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3EchoResp())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3EchoRepInd())
g3_comms.g3_msgs.msg_decode_list.append(g3_resp.G3EchoReqInd())

# Instantiate a global instance of every command we might want to send
g3_comms.g3_msgs.msg_cmds['hwreset'] = g3_cmd.HWResetCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['dbgtool'] = g3_cmd.DBGToolCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['get'] = g3_cmd.G3GetCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['set'] = g3_cmd.G3SetCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['swreset'] = g3_cmd.SWResetCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['phydata'] = g3_cmd.PhyDataCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['phyack'] = g3_cmd.PhyAckCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['phyrf'] = g3_cmd.PhyRfCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['bootsrvstart'] = g3_cmd.BootSrvStartCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['bootdevstart'] = g3_cmd.BootDevStartCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['bootsetpsk'] = g3_cmd.BootSrvSetPSKCmd(subparsers)
g3_comms.g3_msgs.msg_cmds['echo'] = g3_cmd.ICMPEchoCmd(subparsers)

args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

def shutdown_handler(signum, frame): # pylint: disable=unused-argument
    g3_comms.g3_rx.G3Rx.quit()

# custom overrides for Argparser when we're in interactive mode
class ParserException(Exception):
    "Raised on parser error exit"

def interactive_parser_error(self=None, status=0, message=None): #pylint: disable=unused-argument
    args.cmd = None
    if message:
        print(f"{message}")
    raise ParserException()

def main():
    global args
    logging.debug("*** Starting cli")
    logging.debug(f"args: {args}")

    port = args.port
    logging.info(f'Using port {port}')

    signal.signal(signal.SIGINT, shutdown_handler)

    logging.debug(f"Registered messages for decode: {g3_comms.g3_msgs.msg_decode_list}")
    logging.debug(f"Registered commands to tx: {g3_comms.g3_msgs.msg_cmds.keys()}")
    device = serial.Serial(port, baudrate=115200, timeout=0)
    logging.info(f"Opened serial port {device.name}")

    if args.interactive:
        args.dump = True
        parser.exit_on_error = False
        argparse.ArgumentParser.exit = interactive_parser_error

    dryrun = args.dryrun # lock this in

    rx_protocol = g3_comms.g3_rx.G3Rx(device)
    rx_thread = threading.Thread(target=rx_protocol.run)
    rx_thread.start()

    while True:
        # Now that we can Rx responses, now process and run commands
        logging.debug(f"Command entered {args.cmd}")
        if args.cmd:
            if args.dump and not args.interactive:
                print("--dump enabled, enter ^C to exit")
            try:
                try:
                    g3_comms.g3_msgs.msg_cmds[args.cmd].parse_args(args)
                except ValueError:
                    print("Unable to convert data input")
                else:
                    g3_comms.g3_msgs.msg_cmds[args.cmd].setup_rx(g3_comms.g3_msgs.msg_decode_list)
                    if dryrun:
                        msg = g3_comms.g3_tx.form_msg(g3_comms.g3_msgs.msg_cmds[args.cmd])
                        print(f"Dry run, message encoded: {msg}")
                    else:
                        g3_comms.g3_tx.send_and_wait(device, g3_comms.g3_msgs.msg_cmds[args.cmd], timeout=args.timeout)
            except KeyError:
                print(f"Unrecognized command {args.cmd}. Exiting.")
            if not args.dump:
                g3_comms.g3_rx.G3Rx.quit()
        elif not args.interactive:
            print("No command, in dump mode, enter ^C to exit")

        if not args.interactive:
            break

        # We're in interactive mode. So, print a prompt and get input, loop until we get input.
        # in other words, an `enter` key on nothing will reissue the prompt
        while True:
            try:
                user_input = input('-> ')
            except EOFError: # This is ^d
                user_input = 'quit'

            # Handle a couple of "commands" without adding them to our parser.
            if len(user_input.strip()) == 0:
                continue    # if the user hits enter, redo the last command
            break

        if user_input.strip() in ('.'):
            continue    # if the user enters '.', redo the last command

        args.cmd = None # clear this out, because if we don't we'll repeat the last command on error or help
        if user_input.strip() in ('quit', 'end', 'exit'):
            g3_comms.g3_rx.G3Rx.quit()
            break
        if user_input.strip() in ('?', 'help'): # -h and --help will work, but they're part of the parser
            parser.print_help()
            continue
        user_input = '-d -i ' + user_input # Got to be sure to keep us in dump and interactive mode
        try:
            args = parser.parse_args(user_input.split())
        except argparse.ArgumentError:
            print('Invalid command input')
        except ParserException:
            pass # we want to catch it, but we handle messages in the error function.

    # Cleanup and quit
    rx_thread.join()

if __name__ == "__main__":
    main()
