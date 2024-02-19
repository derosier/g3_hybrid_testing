import logging
import argparse

import g3_comms.g3_msgs
import g3_comms.g3_tx

_G_cli_running = True
def cli_shutdown():
    global _G_cli_running
    _G_cli_running = False

def cli_is_running():
    return _G_cli_running

# These are the commands accessable no matter which state we're running in
lc_cli_parser = argparse.ArgumentParser(exit_on_error=False)
lc_cli_subparsers = lc_cli_parser.add_subparsers(dest='cmd')
lc_cli_subparsers.add_parser('hello', help='Just a test')
sp_log = lc_cli_subparsers.add_parser('log', help='Set log level')
sp_log.add_argument("verbosity", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
sp_testpacket = lc_cli_subparsers.add_parser('txtest', help='Send test packet')
sp_testpacket.add_argument("dest", type=int, help="Destination Short Address")
sp_testpacket.add_argument("-c", "--count", type=int, default=1, help="Number of test packets to send.")
sp_idreqpacket = lc_cli_subparsers.add_parser('txidreq', help='Send ID Request packet')
sp_idreqpacket.add_argument("dest", type=int, help="Destination Short Address")
sp_idresppacket = lc_cli_subparsers.add_parser('txidresp', help='Send ID Response packet')
sp_idresppacket.add_argument("dest", type=int, help="Destination Short Address")
sp_status = lc_cli_subparsers.add_parser('status', help='Print out system status')
sp_pair = lc_cli_subparsers.add_parser('pair', help='Pair with new panel')
sp_pair.add_argument("uuid", help="UUID of the panel to allow onto the network. Form: 'G3MOD-PCM-000A-01:JJ-9999-F4CH9'")

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

def cli_main(mailbox):
    global cli_args
    global _G_cli_running
    argparse.ArgumentParser.exit = interactive_parser_error

    while _G_cli_running:
        # Process and run commands
        logging.debug(f"all args {cli_args}")
        if cli_args.cmd:
            if cli_args.cmd =='hello':
                print("Hi!")
                mailbox.put({'type': 'hello'})
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
                mailbox.put({'type': 'txtest', 'dest': cli_args.dest, 'count': cli_args.count})
            elif cli_args.cmd == 'txidreq':
                mailbox.put({'type': 'txidreq', 'dest': cli_args.dest})
            elif cli_args.cmd == 'txidresp':
                mailbox.put({'type': 'txidresp', 'dest': cli_args.dest})
            elif cli_args.cmd == 'status':
                mailbox.put({'type': 'status'})
            elif cli_args.cmd == "pair":
                mailbox.put({'type': 'pair', 'uuid': cli_args.uuid})
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
            _G_cli_running = False
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
    mailbox.put({'type': 'quit'})
