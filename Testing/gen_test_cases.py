#!/usr/bin/env python3

import logging
import argparse
import csv
import sys

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

plc_line_params = [
    [], # used to line up with the header, ignore this one
    ['L-N', 'L1-L2'],
    ['modern', '30 years', '60 years'], # wiring age
    ['Aluminum', 'Copper'],
    [1, 10, 20, 30, 50, 100], # Line length in meters
    [6, 8, 10, 12, 14], # wire gauge
    ['none', 'breaker', 'relay', 'bus work', 'LED', 'CFL', 'Induction Motor',
     'Power Strip', 'Surge Protector', 'Dimmer Switch+light'], # Nodes and line loads
    ['none', 'EN 50160:2010', 'IEC 61000-4-13', 'Enhase'], # Noise and interference
    ['none', '2', '5'], # Coupled lines
]

#pylint: disable=too-many-arguments
def make_plc_test(test_num, pair, age, metal, length,
                  guage, nodes, noise, coupled):
    test = { plc_header[TEST_NUM]: test_num,
             plc_header[LP_PAIR]: pair,
             plc_header[LP_AGE]: age,
             plc_header[LP_METAL]: metal,
             plc_header[LP_LENGTH]: length,
             plc_header[LP_GAUGE]: guage,
             plc_header[LP_NODES]: nodes,
             plc_header[LP_NOISE]: noise,
             plc_header[LP_COUPLED]: coupled,
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
                                    atest = make_plc_test(test_num,
                                                          pair,
                                                          age,
                                                          metal,
                                                          length,
                                                          guage,
                                                          nodes,
                                                          noise,
                                                          coupled)
                                    logging.debug(f"Test: {atest}")
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
