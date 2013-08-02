#!/usr/bin/env python
import optparse
import os
import sys
import logging
import json
import itertools
import subprocess
import drivecasa
from drivecasa.keys import clean_results as clean_keys
from ami import keys as ami_keys
import amisurvey

from tkp.accessors import FitsImage
from tkp.accessors import sourcefinder_image_from_accessor
from tkp.accessors import writefits as tkp_writefits
from tkp.sourcefinder.utils import generate_result_maps

ami_clean_args = {   "spw": '0:3~7',
          "imsize": [512, 512],
          "cell": ['5.0arcsec'],
          "pbcor": False,
#           "weighting": 'natural',
#             "weighting": 'briggs',
#             "robust": 0.5,
          "weighting":'uniform',
          "psfmode": 'clark',
          "imagermode": 'csclean',
          }


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
                                                 overwrite=False))


        # Concatenate the data to create a master image:
        concat_vis = drivecasa.commands.concat(script, good_vis,
                       out_basename='concat_' + grp_name,
                       out_dir=os.path.join(casa_output_dir, 'dirty'),
                       overwrite=False)


        # Do a dirty clean to get a first, rough estimate of the noise level.
        dirty_maps = drivecasa.commands.clean(script, vis_path=concat_vis,
                          niter=0, threshold_in_jy=1,
                          other_clean_args=ami_clean_args,
                          out_dir=casa_output_dir,
                          overwrite=True)

        # Dump a FITS version of the dirty map
        dirty_fits = drivecasa.commands.export_fits(script,
                                image_path=dirty_maps[clean_keys.image],
                                out_dir=fits_output_dir,
                                overwrite=False)

        # Ok, run what we have so far:
        stderr, errors = drivecasa.run_script(script, working_dir=casa_output_dir,
                                             log2term=True,
                                             raise_on_severe=False)
        print "Got the following errors (probably all ok)"
        for e in errors:
            print e

        init_rms_est = get_image_rms_estimate(dirty_maps[clean_keys.image])

        # Iteratively run open box cleaning until RMS levels out:
        # NB we only clean to 3*RMS which should prevent extended iteration
        # Also we do not overwrite after the initial run, hence taking advantage
        # of casapy iterative cleaning.
        # (See the casapy manual or the commands.clean docstring for details).
        prev_rms_est = init_rms_est
        print "Init RMS:", init_rms_est
        clean_count = 0
        while True:
            script = []
            if clean_count is 0:
                overwrite = True
            else:
                overwrite = False
            open_clean_maps = drivecasa.commands.clean(script, vis_path=concat_vis,
                                   niter=500,
                                   threshold_in_jy=init_rms_est * 3,
                                   mask='',
                                   other_clean_args=ami_clean_args,
                                   out_dir=os.path.join(casa_output_dir,
                                                'open_clean'),
                                   overwrite=overwrite)
            stderr, errors = drivecasa.run_script(script, working_dir=casa_output_dir,
                                     log2term=True,
                                     raise_on_severe=True)

            cleaned_rms_est = get_image_rms_estimate(open_clean_maps[clean_keys.image])
            clean_count += 1

            print "Iter", clean_count, "; Cleaned RMS:", cleaned_rms_est
            if cleaned_rms_est <= prev_rms_est * 1.25:
                print "Stopping after ", clean_count, "open cleans."
                break
            else:
                prev_rms_est = cleaned_rms_est

        script = []
        open_clean_fits = drivecasa.commands.export_fits(script,
                                     image_path=open_clean_maps[clean_keys.image],
                                     out_dir=fits_output_dir)
        stderr, errors = drivecasa.run_script(script, working_dir=casa_output_dir,
                                             log2term=True)


        # Perform sourcefinding:


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

def get_image_rms_estimate(path_to_casa_image):
    map = amisurvey.load_casa_imagedata(path_to_casa_image)
    return amisurvey.sigmaclip.rms_with_clipped_subregion(map, sigma=3, f=3)

def find_significant_source_positions(path_to_fits_image,
                                      detection_thresh=6,
                                      analysis_thresh=4,
                                      back_size=64,
                                      margin=128,
                                      radius=0,
                                      ):
    sf_config = {
        "back_sizex": back_size,
        "back_sizey": back_size,
        "margin": margin,
        "radius": radius,
        "deblend": True,
        "deblend_nthresh": 32,
        "force_beam": False
        }

    sfimg = sourcefinder_image_from_accessor(FitsImage(path_to_fits_image),
                                             **sf_config)
    results = sfimg.extract(detection_thresh, analysis_thresh)
    for i, r in enumerate(results):
        print i, ":", r,
        print "Sig:", r.sig


def output_preamble_to_log(groups):
    logger.info("*************************")
    logger.info("Processing groups:")
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

