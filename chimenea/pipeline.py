from __future__ import absolute_import
import os
import drivecasa
from driveami import keys as meta_keys
import chimenea
from chimenea import utils
import chimenea.subroutines as subs
import logging

import chimenea.telescopes.ami as ami

logger = logging.getLogger(__name__)

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
                            'casalog_{}.txt'.format(reduction_timestamp))
        commands_logfile = os.path.join(casa_output_dir,
                             'casa_commands_{}.txt'.format(reduction_timestamp))
        casa = drivecasa.Casapy(casa_logfile=casa_logfile,
                                commands_logfile=commands_logfile,
                                working_dir=casa_output_dir,)
        logger.info("Processing %s", group_name)
        logger.info("CASA logfile at: %s",casa_logfile)
        logger.info("Commands logfile at: %s",commands_logfile)

        #Filter those obs with extreme rain values
        good_obs, rejected = ami.reject_bad_obs(groups[group_name])
        process_observation_group(good_obs,
                                  ami.ami_chimconfig,
                                  monitor_coords,
                                  casa_output_dir,
                                  fits_output_dir,
                                  casa)
    return groups


def process_observation_group(good_obs,
                              chimconfig,
                              monitor_coords,
                              casa_output_dir,
                              fits_output_dir,
                              casa_instance):

    logger.info("*** Concatenating and making dirty maps ***")
    # Import UVFITs to MS, concatenate
    script, concat_ob = subs.import_and_concatenate(good_obs,
                                                     casa_output_dir)

    assert isinstance(chimconfig, chimenea.config.ChimConfig)

    # Make dirty maps
    for obs in good_obs + [concat_ob]:
        script.extend(subs.clean_and_export_fits(
            obs,
            casa_output_dir,
            fits_output_dir,
            threshold=1,
            niter=0,
            mask='',
            other_clean_args=chimconfig.clean.other_args))
    casa_out, errors = casa_instance.run_script(script, raise_on_severe=False)
    if errors:
        logger.warning("Got the following errors (probably all ok)")
        for e in errors:
            logger.warning(e)

    logger.info("*** Getting initial estimates of RMS from dirty maps ***")
    for obs in good_obs+[concat_ob]:
        dmap = obs.maps_dirty.ms.image
        obs.rms_dirty= subs.get_image_rms_estimate(dmap)
        obs.rms_best = obs.rms_dirty
        logger.debug("%s; dirty map RMS est: %s", obs.name, obs.rms_dirty)


    logger.info("*** Performing iterative open clean on concat image ***")
    # Do iterative open clean on concat vis to create deep image:
    subs.iterative_clean(concat_ob,
                         chimconfig,
                         mask='',
                         casa_output_dir=casa_output_dir,
                         fits_output_dir=fits_output_dir,
                         casa_instance=casa_instance)


    logger.info("Sourcefinding on concat image...")
    # Perform sourcefinding on the open-clean concat map,to try and create a
    # deep source catalogue.
    sources = subs.run_sourcefinder(concat_ob.maps_open.fits.image,
                                    chimconfig.sourcefinding)
    regionfile = os.path.join(fits_output_dir, 'extracted_sources.reg')
    with open(regionfile, 'w') as f:
        f.write(utils.fk5_ellipse_regions_from_extractedsources(sources))

    #Use it to determine mask:
    mask, mask_apertures = utils.generate_mask(
        chimconfig,
        extracted_sources=sources,
        monitoring_coords=monitor_coords,
        regionfile_path=os.path.join(fits_output_dir, 'mask_aps.reg')
    )
    logger.info("Generated mask:\n" + mask)



    logger.info("*** Running masked clean on each epoch ***")
    # Assuming mask valid, i.e. not an empty field:
    if len(mask_apertures):
        # Reset the concat_ob best rms estimate to that of dirty map,
        # to avoid over-cleaning.
        concat_ob.rms_best = concat_ob.rms_dirty
        # Run iterative masked cleans on epochal obs, and get updated RMS est:
        for obs in good_obs+[concat_ob]:
            subs.iterative_clean(obs,
                                 chimconfig,
                                 mask=mask,
                                 casa_output_dir=casa_output_dir,
                                 fits_output_dir=fits_output_dir,
                                 casa_instance=casa_instance)

    logger.info("*** Running open clean on each epoch ***")
    # Finally, run a single open-clean on each epoch, to the RMS limit
    # determined from the masked clean.
    script=[]
    for obs in good_obs:
        script.extend(
            subs.clean_and_export_fits(
                obs,
                casa_output_dir, fits_output_dir,
                threshold=chimconfig.clean.sigma_threshold * obs.rms_best,
                niter=chimconfig.clean.niter,
                mask='',
                other_clean_args=chimconfig.clean.other_args
            ))
    casa_out, errors = casa_instance.run_script(script, raise_on_severe=False)

