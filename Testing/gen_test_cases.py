#!/usr/bin/env python3

import logging
import argparse
import csv
import sys
from collections import namedtuple

parser = argparse.ArgumentParser()
parser.add_argument("-V", "--verbosity", default="INFO", help="Logging verbosity. [CRITICAL, ERROR, WARNING, INFO, DEBUG]")
parser.add_argument("-n", "--dryrun", help="Run but don't produce CSV", action='store_true')
parser.add_argument("-P", "--noPLC", help="Suppress PLC output", action='store_true')
parser.add_argument("-R", "--noRF", help="Suppress RF output", action='store_true')
parser.add_argument("-s", "--set", help="Filter output by test set", choices={'VV', 'model', 'smoke'})
parser.add_argument("filename", nargs='?', default="-", help="Optional file name prefix to write out, STDOUT otherwise")
args = parser.parse_args()
print(args.set)
lineformat = "%(asctime)s: [%(levelname)s] %(message)s"
logging.basicConfig(format=lineformat, level=args.verbosity.upper(),
                    datefmt="%H:%M:%S")

Value = namedtuple("Value", "value, use, metric, time, test_set")
MetaData = namedtuple("MetaData", "priority, time_cost, vv, model, smoke")

MD_PRIORITY = 0
MD_TIME = 1
MD_VV = 2
MD_MODEL = 3
MD_SMOKE = 4

# Test case meta-data
meta_data_header = [
                    'Priority',
                    'Time',
                    'Test: VV',
                    'Test: model',
                    'Test: smoke'
]

def calculate_meta_data(params):
    # Run through the common meta-data for all the variables and compute the necessary
    # meta-data.
    test_set = {'VV', 'model', 'smoke'} # Base set of all
    priority = 0
    time_cost = 0
    for param in params:
        # First filter out anything we aren't going to use. If 'use' is false in ANY of the
        # parameters we don't want to use it.
        if param.use is False:
            return None

        # Filter test sets. For something to be in a given test set, all the variables need to have
        # that test set set.
        test_set = test_set & param.test_set

        # Calculate priority metric. This is simple addition, higher is better
        priority = priority + param.metric

        # Calculate time-cost. We average the time, for now just sum it up.
        time_cost = time_cost + param.time

    # post processing
    time_cost = time_cost / len(params)
    if len(test_set) == 0: # If not included in any test set, filter it out
        return None
    if (args.set is not None) and (args.set not in test_set): # Filter it IN if we set the cmd-line param
        return None
    ts_VV = 'VV' in test_set
    ts_model = 'model' in test_set
    ts_smoke = 'smoke' in test_set

    return MetaData(priority, time_cost, ts_VV, ts_model, ts_smoke)

####################################################################################################
# PLC variable parameters
####################################################################################################

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
    [Value('L-N', True, 1000, 10, {'VV', 'model', 'smoke'}),
     Value('L1-L2', False, 500, 10, {'VV', 'model', 'smoke'})],
    # Wiring Age
    [Value('modern', True, 100, 10, {'VV', 'model', 'smoke'}),
     Value('30 years', False, 100, 10, {'model'}),
     Value('60 years', False, 100, 10, {'model'})],
    # Wire type
    [Value('Aluminum', False, 100, 10, {'VV', 'model'}),
     Value('Copper', True, 100, 10, {'VV', 'model', 'smoke'})],
    # Wire length in meters
    [Value(1, True, 50, 10, {'VV', 'model', 'smoke'}),
     Value(10, True, 40, 10, {'model'}),
     Value(20, True, 30, 10, {'model'}),
     Value(30, False, 30, 10, {'model'}),
     Value(50, True, 40, 10, {'VV', 'model'}),
     Value(100, True, 50, 10, {'VV', 'model', 'smoke'})],
    # Wire gauge in AWG
    [Value(6, True, 20, 10, {'VV', 'model', 'smoke'}),
     Value(8, False, 0, 10, {'model'}),
     Value(10, False, 0, 10, {'model'}),
     Value(12, True, 20, 10, {'VV', 'model', 'smoke'}),
     Value(14, True, 0, 10, {'model'})],
    # Node types and line loads
    [Value('none', True, 500, 10, {'VV', 'model', 'smoke'}),
     Value('breaker', True, 500, 10, {'VV', 'model', 'smoke'}),
     Value('relay', True, 500, 10, {'VV', 'model', 'smoke'}),
     Value('bus work', True, 100, 10, {'model'}),
     Value('LED', True, 300, 10, {'VV', 'smoke'}),
     Value('CFL', False, 300, 10, {'model'}),
     Value('Induction Motor', True, 100, 10, {'model'}),
     Value('Power Strip', True, 100, 10, {'model'}),
     Value('Surge Protector', True, 100, 10, {'VV', 'model'}),
     Value('Dimmer Switch+light', True, 100, 10, {'model'})],
    # Interference and noise
    [Value('none', True, 500, 10, {'VV', 'model', 'smoke'}),
     Value('EN 50160:2010', True, 100, 10, {'VV', 'model'}),
     Value('IEC 61000-4-13', True, 100, 10, {'VV', 'model'}),
     Value('Enphase', True, 50, 10, {'model'})],
    # Number of wires coupling
    [Value('none', True, 500, 10, {'VV', 'model', 'smoke'}),
     Value('2', False, 100, 10, {'model'}),
     Value('5', True, 100, 10, {'model'})],
]

LP_Params = namedtuple("LP_Params", "pair, age, metal, length, guage, nodes, noise, coupled")

def make_plc_test(test_num, lp_params):
    # process metadata
    metadata = calculate_meta_data(lp_params)
    if metadata is None:
        return None

    # Now construct the test case
    test = { plc_header[TEST_NUM]: test_num,
             plc_header[LP_PAIR]: lp_params.pair.value,
             plc_header[LP_AGE]: lp_params.age.value,
             plc_header[LP_METAL]: lp_params.metal.value,
             plc_header[LP_LENGTH]: lp_params.length.value,
             plc_header[LP_GAUGE]: lp_params.guage.value,
             plc_header[LP_NODES]: lp_params.nodes.value,
             plc_header[LP_NOISE]: lp_params.noise.value,
             plc_header[LP_COUPLED]: lp_params.coupled.value,
             meta_data_header[MD_PRIORITY]: metadata.priority,
             meta_data_header[MD_TIME]: metadata.time_cost,
             meta_data_header[MD_VV]: 'VV' if metadata.vv else '',
             meta_data_header[MD_MODEL]: 'model' if metadata.model else '',
             meta_data_header[MD_SMOKE]: 'smoke' if metadata.smoke else '',
    }
    return test

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
                                    if atest is None:
                                        continue
                                    logging.debug(f"Test: {atest}")
                                    tests.append(atest)
                                    test_num += 1
    logging.info(f"{test_num-1} tests generated")
    return tests

####################################################################################################
# RF variable parameters
####################################################################################################
# Below indexes into both plc_header as well as plc_line_params
# keep these in the same order and with the indexes working OK.
# TEST_NUM = 0 -> defined above
RF_LOCATION = 1
RF_DISTANCE = 2
RF_OBSTACLE = 3
RF_NOISE = 4

rf_header = [
              'Test Num',
              'Location and weather',
              'Distance',
              'Obstacle',
              'Noise',
]

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
# The Obstacles portion wraps a dict that is used to use two different spaces, indoor vs other.
# the correct one to use will be selected by the location field value.
rf_line_params = [
    [], # used to line up with the header, ignore this one
    # Location/Weather
    [Value('indoor', True, 500, 10, {'VV', 'model', 'smoke'}),
     Value('outdoor', True, 500, 10, {'VV', 'model'}),
     Value('rain', False, 100, 10, {'model'}),
     Value('fog', False, 100, 10, {'model'})],
    # Distance
    [Value(1, False, 50, 10, {'VV', 'model', 'smoke'}),
     Value(10, True, 40, 10, {'model'}),
     Value(20, True, 30, 10, {'model'}),
     Value(30, False, 30, 10, {'model'}),
     Value(50, True, 40, 10, {'VV', 'model'}),
     Value(100, True, 50, 10, {'VV', 'model', 'smoke'})],
    # Obstacles
    {
    'indoor':
        [Value('none', True, 500, 10, {'VV', 'model', 'smoke'}),
         Value('closed door', True, 400, 10, {'VV', 'model'}),
         Value('sheetrock wood-stud wall', True, 400, 10, {'VV', 'model'}),
         Value('masonry wall', True, 400, 10, {'model'}),
         Value('sheetrock metal-stud wall', True, 300, 10, {'model'}),
         Value('floor up', True, 300, 10, {'model'}),
         Value('floor down', False, 100, 10, {'model'}),
         Value('metal cabinet', True, 100, 10, {'model'}),
         Value('living room', True, 500, 10, {'VV', 'model'}),
         Value('office', True, 100, 10, {'model'})],
    'outdoor':
        [Value('none', False, 500, 10, {'VV', 'model', 'smoke'}),
         Value('indoor to outdoor', True, 500, 10, {'VV', 'model'}),
         Value('wooden shed', True, 100, 10, {'model'}),
         Value('metal shed', True, 100, 10, {'model'}),
         Value('mixed barn', True, 100, 10, {'model'}),
         Value('wooden fence', True, 100, 10, {'model'}),
         Value('wire fence', True, 100, 10, {'model'}),
         Value('windows', True, 100, 10, {'model'}),
         Value('trees', True, 100, 10, {'model'}),
         Value('bushes', True, 100, 10, {'model'})],
    },
    # Interference and noise
    [Value('none', True, 500, 10, {'VV', 'model', 'smoke'}),
     Value('microwave', True, 50, 10, {'model'}),
     Value('802.15.4', True, 100, 10, {'model'}),
     Value('LoRa', True, 100, 10, {'model'})],
]

RF_Params = namedtuple("RF_Params", "location, distance, obstacle, noise")

def make_rf_test(test_num, rf_params):
    # process metadata
    metadata = calculate_meta_data(rf_params)
    if metadata is None:
        return None

    # Now construct the test case
    test = { rf_header[TEST_NUM]: test_num,
             rf_header[RF_LOCATION]: rf_params.location.value,
             rf_header[RF_DISTANCE]: rf_params.distance.value,
             rf_header[RF_OBSTACLE]: rf_params.obstacle.value,
             rf_header[RF_NOISE]: rf_params.noise.value,
             meta_data_header[MD_PRIORITY]: metadata.priority,
             meta_data_header[MD_TIME]: metadata.time_cost,
             meta_data_header[MD_VV]: 'VV' if metadata.vv else '',
             meta_data_header[MD_MODEL]: 'model' if metadata.model else '',
             meta_data_header[MD_SMOKE]: 'smoke' if metadata.smoke else '',
    }
    return test

def gen_rf_tests():
    test_num = 1
    tests = []

    # First pass is a naive attempt to generate all combinations.
    for location in rf_line_params[RF_LOCATION]:
        if location.value == 'indoor':
            obstacle_set = rf_line_params[RF_OBSTACLE]['indoor']
        else:
            obstacle_set = rf_line_params[RF_OBSTACLE]['outdoor']
        for distance in rf_line_params[RF_DISTANCE]:
            for obstacle in obstacle_set:
                for noise in rf_line_params[RF_NOISE]:
                    rf_params = RF_Params(location,
                                          distance,
                                          obstacle,
                                          noise)
                    atest = make_rf_test(test_num, rf_params)
                    if atest is None:
                        continue
                    logging.debug(f"Test: {atest}")
                    tests.append(atest)
                    test_num += 1
    logging.info(f"{test_num-1} tests generated")
    return tests

def write_tests(filename, header, tests):
    #pylint: disable=consider-using-with
    logging.debug(f"Writing full set of tests to {filename}")

    if args.dryrun:
        logging.debug("Suppressing output due to --dryrun")
        return

    if filename.startswith('--'):
        csvfile = sys.stdout
    else:
        csvfile = open(filename, 'w', newline='',  encoding="utf-8")

    writer = csv.DictWriter(csvfile, fieldnames=header)
    writer.writeheader()
    for atest in tests:
        writer.writerow(atest)

def main():
    logging.debug("*** Starting gen_test_cases.py")

    logging.debug(f"PLC Line Parameters: {plc_line_params}")
    logging.debug(f"Writing to file {args.filename}")

    if not args.noPLC:
        print("************** PLC tests **************")
        plc_tests = gen_plc_tests()
        write_tests(args.filename + "-plc.csv", plc_header+meta_data_header, plc_tests)

    if not args.noRF:
        print("************** RF tests **************")
        rf_tests = gen_rf_tests()
        write_tests(args.filename + "-rf.csv", rf_header+meta_data_header, rf_tests)

if __name__ == "__main__":
    main()
