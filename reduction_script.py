#!/usr/bin/env python
import optparse
import os
import sys
import logging
import simplejson as json
import itertools
import subprocess
from StringIO import StringIO
import math

import drivecasa
from drivecasa.keys import clean_results as clean_keys
from driveami import keys as ami_keys
import amisurvey
from amisurvey.keys import obs_info as obs_keys

from tkp.accessors import FitsImage
from tkp.accessors import sourcefinder_image_from_accessor
from tkp.accessors import writefits as tkp_writefits
from tkp.sourcefinder.utils import generate_result_maps
import tkp.bin.pyse

ami_clean_args = {   "spw": '0:3~7',
          "imsize": [512, 512],
          "cell": ['5.0arcsec'],
          "pbcor": False,
#           "weighting": 'natural',
             "weighting": 'briggs',
             "robust": 0.5,
#          "weighting":'uniform',
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
    print "Processing all_obs in:", listings_file
    all_obs = load_listings(listings_file)
    obs_groups = get_grouped_file_listings(all_obs)
    output_preamble_to_log(obs_groups)

    for grp_name in sorted(obs_groups.keys()):
        casa_output_dir = os.path.join(options.output_dir, grp_name, 'casa')
        fits_output_dir = os.path.join(options.output_dir, grp_name, 'images')
        casa_logfile = os.path.join(casa_output_dir, 'casalog.txt')

        casa = drivecasa.Casapy(working_dir=casa_output_dir,
                                casa_logfile=casa_logfile)

        logger.info(' '.join(("Processing", grp_name,
                             ", logfile at: ", casa_logfile)))

        grp_obs = obs_groups[grp_name]
        grp_dir = os.path.join(os.path.expanduser(options.output_dir),
                               str(grp_name))

        good_obs, rejected = reject_bad_obs(grp_obs)

        script, concat_obs = import_and_concatenate(good_obs, casa_output_dir)

        script.extend(make_dirty_map(concat_obs, casa_output_dir, fits_output_dir))
        for obs in good_obs:
            script.extend(make_dirty_map(obs, casa_output_dir, fits_output_dir))

#         Ok, run what we have so far:
        casa_out, errors = casa.run_script(script, raise_on_severe=False)
        logger.debug("Got the following errors (probably all ok)")
        for e in errors:
            logger.debug(e)
        # Now we can grab an estimate of the RMS for each map:

        concat_obs[obs_keys.dirty_rms_est] = get_image_rms_estimate(
                            concat_obs[obs_keys.dirty_maps][clean_keys.image])
        for obs in good_obs:
            dmap = obs[obs_keys.dirty_maps][clean_keys.image]
            obs[obs_keys.dirty_rms_est] = get_image_rms_estimate(dmap)

        # Ok, let's do an open clean on the concat map, to try and create a
        # deep source catalogue:
        script = make_open_clean_map(concat_obs, casa_output_dir, fits_output_dir)
        casa_out, errors = casa.run_script(script, raise_on_severe=False)


        # Perform sourcefinding, determine mask:
        sources = run_sourcefinder(concat_obs[obs_keys.open_clean_fits])
        write_ds9_regionfile(sources,
                             os.path.join(fits_output_dir, 'all_sources.reg'))
        mask_thresh = 5.5
        masked_sources = [s for s in sources if s.sig > mask_thresh]
        write_ds9_regionfile(masked_sources,
                             os.path.join(fits_output_dir, 'mask_sources.reg'))

        mask_coords = [(str(s.ra.value) + 'deg', str(s.dec.value) + 'deg')
                       for s in masked_sources]
        mask = drivecasa.utils.get_circular_mask_string(mask_coords,
                                             aperture_radius="5pix")
        logger.info("Mask:\n" + mask)

        # Now go and do masked and open cleans for everything:
        script = []

        script.extend(
          make_masked_clean_map(concat_obs, mask, casa_output_dir, fits_output_dir))
        for obs in good_obs:
            script.extend(
              make_open_clean_map(obs, casa_output_dir, fits_output_dir))
            script.extend(
              make_masked_clean_map(obs, mask, casa_output_dir, fits_output_dir))

        # Go!
        casa_out, errors = casa.run_script(script, raise_on_severe=False)
    return obs_groups

def load_listings(listings_path):
    # simplejson loads plain strings as simple 'str' objects:
    ami_listings = json.load(open(listings_path))
    all_obs = []
    for ami_rawfile, ami_obs in ami_listings.iteritems():
        all_obs.append({
                        obs_keys.name:ami_obs[ami_keys.obs_name],
                        obs_keys.metadata:ami_obs,
                        obs_keys.uvfits:ami_obs[ami_keys.target_uvfits],
                        obs_keys.group:ami_obs[ami_keys.group_name],
                        })
    return all_obs

def get_grouped_file_listings(all_obs):
    grp_names = list(set([obs[obs_keys.group] for obs in all_obs]))
    groups = {}
    for g_name in grp_names:
        grp = [obs for obs in all_obs if obs[obs_keys.group] == g_name]
        groups[g_name] = grp
    return groups

def reject_bad_obs(obs_list):
    """Returns 2 lists: (passed,failed)"""
            # Reject those with extreme rain modulation:
    good_files = []
    rain_rejected = []
    for obs in obs_list:
        rain_amp_mod = obs[obs_keys.metadata][ami_keys.rain]
        if (rain_amp_mod > 0.8 and rain_amp_mod < 1.2):
            good_files.append(obs)
        else:
            rain_rejected.append(obs)
            print "Rejected file", obs[obs_keys.name],
            print " due to rain value", rain_amp_mod
    return good_files, rain_rejected


def import_and_concatenate(obs_list, casa_output_dir):
    """
    Import uvfits, create a concatenated obs.
    *Returns:*
      - tuple: (script, concat_obs_info)
    """
    groups = set([obs[obs_keys.group] for obs in obs_list])
    assert len(groups) == 1
    group_name = groups.pop()
    script = []
    for obs in obs_list:
        obs[obs_keys.vis ] = drivecasa.commands.import_uvfits(script,
                                             obs[obs_keys.uvfits],
                                             out_dir=casa_output_dir,
                                             overwrite=True)


    # Concatenate the data to create a master image:
    concat_obs = {}
    concat_obs[obs_keys.name] = group_name + '_concat'
    concat_obs[obs_keys.vis] = drivecasa.commands.concat(
                                     script,
                                     [obs[obs_keys.vis] for obs in obs_list],
                                     out_basename=concat_obs[obs_keys.name],
                                     out_dir=casa_output_dir,
                                     overwrite=True)
    return script, concat_obs




def clean_and_export_fits(obs_info, maps_out_dir, fits_output_dir,
                          niter=500,
                          mask='',
                          threshold=None,
                          fits_basename=None):
    script = []
    if niter == 0:
        # Doesn't make a difference, so we just set an arbitrary valid value:
        threshold = 1
    maps = drivecasa.commands.clean(script,
                                    vis_path=obs_info[obs_keys.vis],
                                    niter=niter,
                                    threshold_in_jy=threshold,
                                    mask=mask,
                                    other_clean_args=ami_clean_args,
                                    out_dir=maps_out_dir,
                                    overwrite=True)
    obs_info[obs_keys.open_clean_maps] = maps
    # Dump a FITS version of the dirty map
    if fits_basename is None:
        fits_outpath = None
    else:
        fits_outpath = os.path.join(fits_output_dir, fits_basename + '.fits')
    fits = drivecasa.commands.export_fits(script,
                                        image_path=maps[clean_keys.image],
                                        out_dir=fits_output_dir,
                                        out_path=fits_outpath,
                                        overwrite=True)
    return script, maps, fits

def make_dirty_map(obs_info, casa_output_dir, fits_output_dir):
    # Do a dirty clean to get a first, rough estimate of the noise level.
    dirty_maps_dir = os.path.join(casa_output_dir, 'dirty')

    script, maps, fits = clean_and_export_fits(obs_info,
                                               dirty_maps_dir,
                                               fits_output_dir,
                                               niter=0)
    obs_info[obs_keys.dirty_maps] = maps
    obs_info[obs_keys.dirty_fits] = fits
    return script

def make_open_clean_map(obs_info, casa_output_dir, fits_output_dir):
    open_clean_dir = os.path.join(casa_output_dir, 'open_clean')
    fits_basename = obs_info[obs_keys.name] + '_open'
    clean_thresh = obs_info[obs_keys.dirty_rms_est] * 3

    script, maps, fits = clean_and_export_fits(obs_info,
                                               open_clean_dir,
                                               fits_output_dir,
                                               threshold=clean_thresh,
                                               fits_basename=fits_basename)
    obs_info[obs_keys.open_clean_maps] = maps
    obs_info[obs_keys.open_clean_fits] = fits
    return script

def make_masked_clean_map(obs_info, mask, casa_output_dir, fits_output_dir):
    masked_clean_dir = os.path.join(casa_output_dir, 'masked_clean')
    fits_basename = obs_info[obs_keys.name] + '_masked'
    clean_thresh = obs_info[obs_keys.dirty_rms_est] * 3
    script, maps, fits = clean_and_export_fits(obs_info,
                                               masked_clean_dir,
                                               fits_output_dir,
                                               mask=mask,
                                               threshold=clean_thresh,
                                               fits_basename=fits_basename
                                               )
    obs_info[obs_keys.masked_clean_maps] = maps
    obs_info[obs_keys.masked_clean_fits] = fits
    return script


def get_image_rms_estimate(path_to_casa_image):
    map = amisurvey.load_casa_imagedata(path_to_casa_image)
    return amisurvey.sigmaclip.rms_with_clipped_subregion(map, sigma=3, f=3)

def run_sourcefinder(path_to_fits_image,
                      detection_thresh=5,
                      analysis_thresh=3,
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
    return results

def fk5_regions(sourcelist):
    """
    Return a string containing a DS9-compatible region file describing all the
    sources in sourcelist.
    """
    output = StringIO()
    print >> output, "# Region file format: DS9 version 4.1"
    print >> output, "global color=green dashlist=8 3 width=1 font=\"helvetica 10 normal\" select=1 highlite=1 dash=0 fixed=0 edit=1 move=1 delete=1 include=1 source=1"
    print >> output, "fk5"
    for source in sourcelist:
        # NB, here we convert from internal 0-origin indexing to DS9 1-origin indexing
        print >> output, "ellipse(%f, %f, %f, %f, %f)" % (
            source.ra.value,
            source.dec.value,
            source.smaj_asec.value * 2 / 3600.,
            source.smin_asec.value * 2 / 3600.,
            math.degrees(source.theta) + 90
        )
    return output.getvalue()

def write_ds9_regionfile(sources, out_path):
    with open(out_path, 'w') as regionfile:
        regionfile.write(fk5_regions(sources))


def output_preamble_to_log(groups):
    logger.info("*************************")
    logger.info("Processing groups:")
    for key in sorted(groups.keys()):
        logger.info("%s:", key)

        pointings = [f[obs_keys.metadata][ami_keys.pointing_fk5]
                        for f in groups[key] ]
        pointings = set((i[0], i[1]) for i in pointings)
        print "\t ", len(pointings), "different pointings:",
        print pointings
        print
        for f in groups[key]:
            pointing = f[obs_keys.metadata][ami_keys.pointing_fk5]
            ra, dec = pointing[0], pointing[1]
            logger.info("\t %s, \t (%.4f,%.4f)", f[obs_keys.name], ra, dec),
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

