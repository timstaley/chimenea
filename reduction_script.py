#!/usr/bin/env python
from __future__ import absolute_import
import optparse
import os
import sys
import logging
import logging.handlers
import datetime

from driveami import keys as meta_keys
import drivecasa

from chimenea.obsinfo import ObsInfo
import chimenea.subroutines as subs
import chimenea.utils as utils

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

def reduce_listings(listings_file, output_dir, monitor_coords,
                    reduction_timestamp):
    """
    Perform data reduction on observations listed in ``listings_file``.

    **Args:**

    - listings_file: Path to json file containing observations info.
    - output_dir: Outputs here, futher divided into 'casa' and 'images' folders.
    - monitor_coords: a list of (RA,Dec) tuples which we want to add to our clean
      mask.
    - reduction_timestamp: Timestamp used when naming logfiles.
    """
    ### Variables that may need changing:
    ami_clean_args = {   "spw": '0:0~5',
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

    rain_min, rain_max = 0.8, 1.2

    clean_iter = 500
    clean_n_sigma = 3

    max_recleans = 3
    max_acceptable_delta = 0.05

    sourcefinder_detect, sourcefinder_analysis = 5.0,3.0

    mask_source_sigma = 5.5
    mask_ap_radius_degrees = 60./3600




    ##=============================================================

    logger = logging.getLogger()
    logger.info( "Processing all_obs in: %s", listings_file)
    all_obs = utils.load_listings(listings_file)
    groups = utils.get_grouped_file_listings(all_obs)
    output_preamble_to_log(groups)

    for group_name in sorted(groups.keys()):
        #Setup output directories:
        grp_dir = os.path.join(os.path.expanduser(output_dir), str(group_name))
        casa_output_dir = os.path.join(grp_dir, 'casa')
        fits_output_dir = os.path.join(grp_dir, 'images')

        casa_logfile = os.path.join(casa_output_dir,
                            ''.join(('casalog_',reduction_timestamp,'.txt')))
        casa = drivecasa.Casapy(working_dir=casa_output_dir,
                                casa_logfile=casa_logfile)

        logger.info("Processing %s", group_name)
        logger.info("CASA Logfile at: %s",casa_logfile)


        #Filter those obs with extreme rain values
        good_obs, rejected = subs.reject_bad_obs(groups[group_name],
                                                 rain_min, rain_max)

        #Import UVFITs to MS, concatenate, make dirty maps
        script, concat_ob = subs.import_and_concatenate(good_obs,
                                                         casa_output_dir)
        for obs in good_obs+[concat_ob]:
            script.extend(subs.clean_and_export_fits(obs,
                                             casa_output_dir,
                                             fits_output_dir,
                                             threshold=1,
                                             niter=0,
                                             mask='',
                                             other_clean_args=ami_clean_args))

        # Ok, run what we have so far:
        logger.info("*** Concatenating and making dirty maps ***")
        casa_out, errors = casa.run_script(script, raise_on_severe=True)
        if errors:
            logger.warning("Got the following errors (probably all ok)")
            for e in errors:
                logger.warning(e)

        # Now we can grab an estimate of the RMS for each map:
        logger.info("*** Getting initial estimates of RMS from dirty maps ***")
        for obs in good_obs+[concat_ob]:
            dmap = obs.maps_dirty.ms.image
            obs.rms_dirty= subs.get_image_rms_estimate(dmap)
            obs.rms_best = obs.rms_dirty
            logger.debug("%s; dirty map RMS est: %s", obs.name, obs.rms_dirty)


        logger.info("*** Performing iterative open clean on concat image ***")
        # Do iterative open clean on concat vis to create deep image:
        subs.iterative_clean(concat_ob,
                             clean_iter=clean_iter,
                             mask='',
                             rms_threshold_multiple=clean_n_sigma,
                             other_clean_args=ami_clean_args,
                             max_acceptable_rms_delta=max_acceptable_delta,
                             max_recleans=max_recleans,
                             casa_output_dir=casa_output_dir,
                             fits_output_dir=fits_output_dir,
                             casa_instance=casa)

        # Perform sourcefinding on the open-clean concat map,to try and create a
        # deep source catalogue. Use it to determine mask:
        logger.info("Sourcefinding on concat image...")
        sources = subs.run_sourcefinder(concat_ob.maps_open.fits.image,
                                        detection_thresh=sourcefinder_detect,
                                        analysis_thresh=sourcefinder_analysis
                                        )

        with open(os.path.join(fits_output_dir, 'extracted_sources.reg'), 'w') as regionfile:
            regionfile.write(utils.fk5_ellipse_regions_from_extractedsources(sources))

        mask, mask_apertures = utils.generate_mask(
            aperture_radius_degrees=mask_ap_radius_degrees,
            extracted_sources=sources,
            extracted_source_sigma_thresh=mask_source_sigma,
            monitoring_coords=monitor_coords,
            regionfile_path=os.path.join(fits_output_dir, 'mask_aps.reg')
        )

        logger.info("Generated mask:\n" + mask)


        # Assuming mask valid, i.e. not an empty field:
        # Run iterative masked cleans on epochal obs, and get updated RMS est:
        logger.info("*** Running masked clean on each epoch ***")

        # Reset the concat_ob best rms estimate to that of dirty map,
        # to avoid over-cleaning.
        concat_ob.rms_best = concat_ob.rms_dirty

        if len(mask_apertures):
            for obs in good_obs+[concat_ob]:
                subs.iterative_clean(obs,
                                     clean_iter=clean_iter,
                                     mask=mask,
                                     rms_threshold_multiple=clean_n_sigma,
                                     other_clean_args=ami_clean_args,
                                     max_acceptable_rms_delta=max_acceptable_delta,
                                     max_recleans=max_recleans,
                                     casa_output_dir=casa_output_dir,
                                     fits_output_dir=fits_output_dir,
                                     casa_instance=casa)

        # Finally, run a single open-clean on each epoch, to the RMS limit
        # determined from the masked clean.
        logger.info("*** Running open clean on each epoch ***")
        script=[]
        for obs in good_obs:
            script.extend(
                subs.clean_and_export_fits(obs,
                                       casa_output_dir,fits_output_dir,
                                       threshold=clean_n_sigma*obs.rms_best,
                                       niter=clean_iter,
                                       mask='',
                                       other_clean_args=ami_clean_args
            ))
        casa_out, errors = casa.run_script(script, raise_on_severe=True)

    return groups




##=======================================================================

def setup_logging(reduction_timestamp):
    """
    Set up basic (INFO level) and debug logfiles
    """
    log_filename = 'amisurvey_log_'+reduction_timestamp
    date_fmt = "%y-%m-%d (%a) %H:%M:%S"

    std_formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s',
                                      date_fmt)
    debug_formatter = logging.Formatter(
                            '%(asctime)s:%(name)s:%(levelname)s:%(message)s',
                            # '%(asctime)s:%(levelname)s:%(message)s',
                            date_fmt)

    info_logfile = logging.handlers.RotatingFileHandler(log_filename,
                            maxBytes=5e5, backupCount=10)
    info_logfile.setFormatter(std_formatter)
    info_logfile.setLevel(logging.INFO)
    debug_logfile = logging.handlers.RotatingFileHandler(log_filename + '.debug',
                            maxBytes=5e5, backupCount=10)
    debug_logfile.setFormatter(debug_formatter)
    debug_logfile.setLevel(logging.DEBUG)

    stdout_log = logging.StreamHandler()
    stdout_log.setFormatter(std_formatter)
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

def output_preamble_to_log(groups):
    """
    Prettyprint the group listings
    """
    logger=logging.getLogger()
    logger.info("*************************")
    logger.info("Processing groups:")
    for key in sorted(groups.keys()):
        logger.info("%s:", key)

        pointings = [f.meta[meta_keys.pointing_degrees] for f in groups[key] ]
        pointings = set((i[0], i[1]) for i in pointings)
        logger.info("%s different pointings:" % len(pointings))
        logger.info(str(pointings))
        for f in groups[key]:
            pointing = f.meta[meta_keys.pointing_degrees]
            ra, dec = pointing[0], pointing[1]
            logger.info("\t %s,  (%.4f,%.4f)", f.name.ljust(24), ra, dec),
        logger.info("--------------------------------")
    logger.info("*************************")

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

