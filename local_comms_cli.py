import logging
import argparse

import iperf_msgs

import g3_comms.g3_msgs
import g3_comms.g3_tx
from g3_comms import g3_lib

import local_comms_consts as LCC

_G_cli_running = True
def cli_shutdown():
    global _G_cli_running
    _G_cli_running = False

# These are the commands accessable no matter which state we're running in
lc_cli_parser = argparse.ArgumentParser(exit_on_error=False)
lc_cli_subparsers = lc_cli_parser.add_subparsers(dest='cmd')
lc_cli_subparsers.add_parser('hello', help='Just a test')
sp_log = lc_cli_subparsers.add_parser('log', help='Set log level')
sp_log.add_argument("verbosity", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
sp_testpacket = lc_cli_subparsers.add_parser('txtest', help='Send test packet')
sp_testpacket.add_argument("dest", type=int, help="Destination Short Address")
sp_testpacket.add_argument("-c", "--count", type=int, default=1, help="Number of test packets to send.")
sp_status = lc_cli_subparsers.add_parser('status', help='Print out system status')

# Add any Coordinator-only commands
def add_coordinator_parsers():
#     global lc_cli_subparsers
    pass

# Add any Device-only commands
def add_device_parsers():
#     global lc_cli_subparsers
    pass

cli_args = lc_cli_parser.parse_args([])

# Custom overrides for Argparser when we're in interactive mode
# We have to have this and the following or the parser can error out, throwing an exception
# and hanging the program if the user enters a commandline error.  The other parts to make
# this work properly:
#     * hooking this with the line: `argparse.ArgumentParser.exit = interactive_parser_error`
#     * parser.exit_on_error = False
#     * the args being global and preset with `parser.parse_args(...)`
#     * where we run this, wrap in a try: and catch argparse.ArgumentError and ParserException
class ParserException(Exception):
    "Raised on parser error exit"

def interactive_parser_error(self=None, status=0, message=None): #pylint: disable=unused-argument
    cli_args.cmd = None
    if message:
        print(f"{message}")
    raise ParserException()

def do_txtest(serial_device, connman, sa_dest, numpackets):
    logging.debug(f"do_txtest({sa_dest}, {numpackets})")
    # Setup connection to sa_dest
    connid = connman.new_conn(serial_device, sa_dest, LCC.LC_CONTROL_PORT, LCC.LC_CONTROL_PORT)

    for i in range(0, numpackets):
        # Encode a g3_iperf ping packet
        msg_buffer = iperf_msgs.MSG_DATA[:400]
        ping_packet = iperf_msgs.encode_ping_packet(connman.my_short_address, i, msg_buffer)

        # Send the packet
        (send_ok, status) = g3_lib.send_udp(serial_device, connid, i, ping_packet)
        if not send_ok:
            logging.error(f"Error sending ping: {status}")

    # Cleanup connection
    connman.del_connection(serial_device, connid)

def do_status(serial_device, connman, runinfo):
    panid = g3_lib.get_panid(serial_device)
    sa = g3_lib.get_shortid(serial_device)
    print(f"PAN ID: {panid}")
    print(f"Short address: {sa}")

    connman.print_conn_list()
    print(f"{runinfo}")

def cli_main(serial_device, connman, runinfo):
    global cli_args
    global _G_cli_running
    argparse.ArgumentParser.exit = interactive_parser_error

    while _G_cli_running:
        # Process and run commands
        logging.debug(f"all args {cli_args}")
        if cli_args.cmd:
            if cli_args.cmd =='hello':
                print("Hi!")
            elif cli_args.cmd == 'quit':
                _G_cli_running = False
                break
            elif cli_args.cmd == 'log':
                print(f"Setting logging verbosity to {cli_args.verbosity.upper()}")
                logging.getLogger().setLevel(cli_args.verbosity.upper())
                if cli_args.verbosity.upper() == "DEBUG":
                    # A couple of internal debug filtering flags exist in g3_comms to hold verbosity down. If we're
                    # in DEBUG mode, right now we want to see these messages, so let's enable these flags.
                    g3_comms.g3_msgs.print_msg = True
                    g3_comms.g3_tx.cmd_verbose = True
                else:
                    g3_comms.g3_msgs.print_msg = False
                    g3_comms.g3_tx.cmd_verbose = False
            elif cli_args.cmd == 'txtest':
                do_txtest(serial_device, connman, cli_args.dest, cli_args.count)
            elif cli_args.cmd == 'status':
                do_status(serial_device, connman, runinfo)
            else:
                print(f"Unknown command: {cli_args}")

        # Print a prompt and get input, loop until we get input.
        # An `enter` key on nothing will reissue the prompt
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

        cli_args.cmd = None # clear this out, because if we don't we'll repeat the last command on error or help
        if user_input.strip() in ('quit', 'end', 'exit'):
            break
        if user_input.strip() in ('?', 'help'): # -h and --help will work, but they're part of the parser
            lc_cli_parser.print_help()
            continue
        try:
            cli_args = lc_cli_parser.parse_args(user_input.split())
        except argparse.ArgumentError:
            print('Invalid command input')
        except ParserException:
            pass # we want to catch it, but we handle messages in the error function.
