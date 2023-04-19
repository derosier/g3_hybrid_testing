#!/usr/bin/env python3

import logging
import argparse
import csv
import sys
from collections import namedtuple

parser = argparse.ArgumentParser()
parser.add_argument("-V", "--verbosity", default="INFO", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-n", "--dryrun", help="Run but don't produce CSV", action='store_true')
parser.add_argument("filename", nargs='?', default="-", help="Optional file to write out, STDOUT otherwise")
args = parser.parse_args()

lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

# Below indexes into both plc_header as well as plc_line_params
# keep these in the same order and with the indexes working OK.
TEST_NUM = 0
LP_PAIR = 1
LP_AGE = 2
LP_METAL = 3
LP_LENGTH = 4
LP_GAUGE = 5
LP_NODES = 6
LP_NOISE = 7
LP_COUPLED = 8

plc_header = [
              'Test Num',
              'Comm Pair',
              'Age',
              'Type',
              'Line Length',
              'Gauge',
              'Nodes',
              'Noise',
              'Coupling',
]

Value = namedtuple("Value", "value, use, metric, time, test_set")

# The below structure defines the variables and their properties that we generate all the
# combinations of variables to create the test cases from. We have list that contains the
# individual variable sets, and in each of those, a list of the actual variable values.
# Each value is then a tuple that contains the actual value as well as meta-data used to
# compute meta-data for each test case.
# So...:
# everything [
#     independant variable list [
#         value tuple (
#             value,
#             use,
#             priority metric,
#             time cost,
#             test set {VV, model, smoke}
#         , True, 100, 10, {'VV', 'model', 'smoke'}), ...
#     ], ...
# ]
#
plc_line_params = [
    [], # used to line up with the header, ignore this one
    # Comm legs
    [Value('L-N', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('L1-L2', True, 100, 10, {'VV', 'model', 'smoke'})],
    # Wiring Age
    [Value('modern', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('30 years', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('60 years', True, 100, 10, {'VV', 'model', 'smoke'})],
    # Wire type
    [Value('Aluminum', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('Copper', True, 100, 10, {'VV', 'model', 'smoke'})],
    # Wire length in meters
    [Value(1, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(10, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(20, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(30, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(50, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(100, True, 100, 10, {'VV', 'model', 'smoke'})],
    # Wire gauge in AWG
    [Value(6, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(8, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(10, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(12, True, 100, 10, {'VV', 'model', 'smoke'}),
     Value(14, True, 100, 10, {'VV', 'model', 'smoke'})],
    # Node types and line loads
    [Value('none', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('breaker', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('relay', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('bus work', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('LED', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('CFL', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('Induction Motor', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('Power Strip', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('Surge Protector', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('Dimmer Switch+light', True, 100, 10, {'VV', 'model', 'smoke'})],
    # Interference and noise
    [Value('none', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('EN 50160:2010', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('IEC 61000-4-13', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('Enhase', True, 100, 10, {'VV', 'model', 'smoke'})],
    # Number of wires coupling
    [Value('none', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('2', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('5', True, 100, 10, {'VV', 'model', 'smoke'})],
]

LP_Params = namedtuple("LP_Params", "pair, age, metal, length, guage, nodes, noise, coupled")

def make_plc_test(test_num, lp_params):
    # First filter out anything we aren't going to use. If 'use' is false in ANY of the parameters
    # we don't want to use it.
    for param in lp_params:
        if param.use is False:
            return None

    # Now construct the test case
    test = { plc_header[TEST_NUM]: test_num,
             plc_header[LP_PAIR]: lp_params.pair,
             plc_header[LP_AGE]: lp_params.age,
             plc_header[LP_METAL]: lp_params.metal,
             plc_header[LP_LENGTH]: lp_params.length,
             plc_header[LP_GAUGE]: lp_params.guage,
             plc_header[LP_NODES]: lp_params.nodes,
             plc_header[LP_NOISE]: lp_params.noise,
             plc_header[LP_COUPLED]: lp_params.coupled,
    }
    return test
#pylint: enable=too-many-arguments

def gen_plc_tests():
    #pylint: disable=too-many-nested-blocks
    test_num = 1
    tests = []

    # First pass is a naive attempt to generate all combinations.
    for pair in plc_line_params[LP_PAIR]:
        for age in plc_line_params[LP_AGE]:
            for metal in plc_line_params[LP_METAL]:
                for length in plc_line_params[LP_LENGTH]:
                    for guage in plc_line_params[LP_GAUGE]:
                        for nodes in plc_line_params[LP_NODES]:
                            for noise in plc_line_params[LP_NOISE]:
                                for coupled in plc_line_params[LP_COUPLED]:
                                    lp_params = LP_Params(pair,
                                                          age,
                                                          metal,
                                                          length,
                                                          guage,
                                                          nodes,
                                                          noise,
                                                          coupled)
                                    atest = make_plc_test(test_num, lp_params)
                                    logging.debug(f"Test: {atest}")
                                    if atest is None:
                                        continue
                                    tests.append(atest)
                                    test_num += 1
    logging.info(f"{test_num-1} tests generated")
    return tests

def write_plc_tests(filename, tests):
    #pylint: disable=consider-using-with
    logging.debug(f"Writing full set of tests to {filename}")
    logging.debug("Suppressing output due to --dryrun")

    if args.dryrun:
        return

    if filename == '-':
        csvfile = sys.stdout
    else:
        csvfile = open(filename, 'w', newline='',  encoding="utf-8")

    writer = csv.DictWriter(csvfile, fieldnames=plc_header)
    writer.writeheader()
    for atest in tests:
        writer.writerow(atest)

def main():
    logging.debug("*** Starting gen_test_cases.py")

    logging.debug(f"PLC Line Parameters: {plc_line_params}")
    logging.debug(f"Writing to file {args.filename}")

    plc_tests = gen_plc_tests()
    write_plc_tests(args.filename, plc_tests)

if __name__ == "__main__":
    main()
