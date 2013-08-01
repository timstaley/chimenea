#!/usr/bin/env python
import optparse
import os
import sys
import logging
import json
import itertools
import subprocess
import drivecasa
from ami import keys as ami_keys

def handle_args():
    """
    Default values are defined here.
    """
    default_output_dir = os.path.expanduser("/data2/ami_results")
    default_casa_dir = None
    usage = """usage: %prog [options] datasets_to_process.json\n"""
    parser = optparse.OptionParser(usage)

    parser.add_option("-o", "--output-dir", default=default_output_dir,
                      help="Path to output directory (default is : " +
                            default_output_dir + ")")

    parser.add_option("--casa-dir", default=default_casa_dir,
                   help="Path to CASA directory, default: " +
                                str(default_casa_dir))

    options, args = parser.parse_args()
    options.output_dir = os.path.expanduser(options.output_dir)
    if len(args) != 1:
        parser.print_help()
        sys.exit(1)
    print "Reducing files listed in:", args[0]
    return options, args[0]

def main(options, listings_file):
    print "Processing listings in:", listings_file
    listings = load_listings(listings_file)
    groups = get_grouped_file_listings(listings)
    output_preamble_to_log(groups)


    for grp_name in sorted(groups.keys()):
        casa_output_dir = os.path.join(options.output_dir, grp_name, 'casa')
        fits_output_dir = os.path.join(options.output_dir, grp_name, 'images')
        files_info = groups[grp_name]
        grp_dir = os.path.join(os.path.expanduser(options.output_dir),
                               str(grp_name))

        # Reject those with extreme rain modulation:
        good_files = []
        rain_rejected = []
        for f in files_info:
            rain_amp_mod = f[ami_keys.rain]
            if (rain_amp_mod > 0.8 and rain_amp_mod < 1.2):
                good_files.append(f)
            else:
                rain_rejected.append(f)
                print "Rejected file", f[ami_keys.obs_name],
                print " due to rain value", rain_amp_mod

        script = []
        good_vis = []
        for f in good_files:
            good_vis.append(
                drivecasa.commands.import_uvfits(script,
                                                 f[ami_keys.target_uvfits],
                                                 out_dir=casa_output_dir,
                                                 overwrite=True))

        concat_vis = drivecasa.commands.concat(script, good_vis,
                                               out_basename='concat_' + grp_name,
                                               out_dir=casa_output_dir)



        dirty_maps = drivecasa.commands.clean(script, vis_path=concat_vis,
                          niter=0, threshold_in_mjy=1,
                          other_clean_args=drivecasa.default_clean_args.ami,
                          out_dir=casa_output_dir,
                          overwrite=True)
        drivecasa.run_script(script, working_dir=casa_output_dir)



#             for f in files_info:
#                 try:
#                     logging.info('Processing observation: %s', f[ami_keys.obs_name])
#                     drivecasa.process_observation(f, grp_dir, casa_dir)
#                 except (ValueError, IOError):
#                     logging.warn("Hit exception imaging target: " + f[ami_keys.obs_name])
#                     continue
    return groups

def load_listings(listings_path):
    unicode_listings = json.load(open(listings_file))
    # JSON Stores everything as unicode. This screws up CASA, so we need to
    # convert it back:
    ascii_listings = {}
    for obs in unicode_listings:
        ascii_listings[str(obs)] = unicode_listings[obs]
    for obs_info in ascii_listings.values():
        for k in obs_info.keys():
            if type(obs_info[k]) is unicode:
                obs_info[k] = str(obs_info[k])
    return ascii_listings


def get_grouped_file_listings(listings):
    grp_names = list(set([i[ami_keys.group_name] for i in listings.values()]))
    groups = {}
    for g_name in grp_names:
        grp = [i for i in listings.values() if i[ami_keys.group_name] == g_name]
        groups[g_name] = grp
    return groups


def output_preamble_to_log(groups):
    logger.info("*************************")
    logger.info("Processing with casapy:")
    for key in sorted(groups.keys()):
        logger.info("%s:", key)
        for f in groups[key]:
            logger.info("\t %s", f[ami_keys.obs_name])
        logger.info("--------------------------------")
    logger.info("*************************")

##=======================================================================
if __name__ == "__main__":
    logging.basicConfig(format='%(levelname)s:%(message)s',
                    filemode='w',
                    filename="drive-casa.log",
                    level=logging.DEBUG)
    logger = logging.getLogger()
    log_stdout = logging.StreamHandler(sys.stdout)
    log_stdout.setLevel(logging.INFO)
    logger.addHandler(log_stdout)
    options, listings_file = handle_args()
    print "OPTIONS", options
    main(options, listings_file)
    sys.exit(0)

