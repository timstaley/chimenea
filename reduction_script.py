#!/usr/bin/env python
from __future__ import absolute_import
import optparse
import os
import sys
import logging
import logging.handlers
import datetime


import chimenea.utils as utils
from chimenea.pipeline import reduce_listings

def handle_args():
    """
    Defines command line arguments.

    Default values can be tweaked here.
    """
    default_output_dir = os.path.expanduser("~/ami_results")
    default_casa_dir = None

    usage = """usage: %prog [options] datasets_to_process.json\n"""
    parser = optparse.OptionParser(usage)

    parser.add_option("-o", "--output-dir", default=default_output_dir,
                      help="Path to output directory (default is : " +
                           default_output_dir + ")")

    parser.add_option("--casa-dir", default=default_casa_dir,
                      help="Path to CASA directory, default: " +
                           str(default_casa_dir))
    m_help = 'Specify a list of RA,DEC co-ordinate pairs to monitor' \
             ' (decimal degrees, no spaces)'
    parser.add_option('-m', '--monitor-coords', help=m_help, default=None)
    parser.add_option('-l', '--monitor-list',
                      help='Specify a file containing a list of monitor coords.',
                      default=None)

    options, args = parser.parse_args()
    options.output_dir = os.path.expanduser(options.output_dir)
    if len(args) != 1:
        parser.print_help()
        sys.exit(1)
    print "Reducing files listed in:", args[0]
    return options, args[0]


def setup_logging(reduction_timestamp):
    """
    Set up basic (INFO level) and debug logfiles
    """
    log_filename = 'chimenea_log_'+reduction_timestamp
    date_fmt = "%y-%m-%d (%a) %H:%M:%S"

    from colorlog import ColoredFormatter

    std_formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s',
                                      date_fmt)


    debug_formatter = logging.Formatter(
                            '%(asctime)s:%(name)s:%(levelname)s:%(message)s',
                            # '%(asctime)s:%(levelname)s:%(message)s',
                            date_fmt)

    color_formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s:%(levelname)-8s%(reset)s %(blue)s%(message)s",
            datefmt=date_fmt,
            reset=True,
            log_colors={
                    'DEBUG':    'cyan',
                    'INFO':     'green',
                    'WARNING':  'yellow',
                    'ERROR':    'red',
                    'CRITICAL': 'red',
            }
    )

    info_logfile = logging.handlers.RotatingFileHandler(log_filename,
                            maxBytes=5e5, backupCount=10)
    info_logfile.setFormatter(std_formatter)
    info_logfile.setLevel(logging.INFO)
    debug_logfile = logging.handlers.RotatingFileHandler(log_filename + '.debug',
                            maxBytes=5e5, backupCount=10)
    debug_logfile.setFormatter(debug_formatter)
    debug_logfile.setLevel(logging.DEBUG)

    stdout_log = logging.StreamHandler()
    stdout_log.setFormatter(color_formatter)
    stdout_log.setLevel(logging.INFO)
    stdout_log.setLevel(logging.DEBUG)


    logger = logging.getLogger()
    logger.handlers=[]
    logger.setLevel(logging.DEBUG)
    logger.addHandler(info_logfile)
    logger.addHandler(debug_logfile)
    logger.addHandler(stdout_log)
    logging.getLogger('drivecasa').setLevel(logging.ERROR) #Suppress drivecasa debug log.
    logging.getLogger('tkp').setLevel(logging.ERROR) #Suppress SF / coords debug log.




##=======================================================================
if __name__ == "__main__":
    timestamp = datetime.datetime.now().strftime("%y-%m-%dT%H%M%S")
    setup_logging(timestamp)
    logger=logging.getLogger()
    options, listings_file = handle_args()
    monitor_coords = utils.parse_monitoringlist_positions(options)
    logger.info("Monitoring coords:\n %s", str(monitor_coords))
    reduce_listings(listings_file, options.output_dir, monitor_coords,
                    timestamp)
    sys.exit(0)

