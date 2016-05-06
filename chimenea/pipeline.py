from __future__ import absolute_import
import os

import chimenea
from chimenea import utils
import chimenea.subroutines as subs
from tkp.accessors.detection import casa_detect
import logging

logger = logging.getLogger(__name__)

def process_observation_group(obs_list,
                              chimconfig,
                              monitor_coords,
                              casa_output_dir,
                              fits_output_dir,
                              casa_instance):

    # Import UVFITs to MS, concatenate
    script, concat_ob = subs.import_and_concatenate(obs_list,
                                                     casa_output_dir)

    assert isinstance(chimconfig, chimenea.config.ChimConfig)

    # Make dirty maps
    for obs in obs_list + [concat_ob]:
        script.extend(subs.clean_and_export_fits(
            obs,
            casa_output_dir,
            fits_output_dir,
            threshold=1,
            niter=0,
            mask='',
            modelimage='',
            other_clean_args=chimconfig.clean.other_args))

    # Concatenating many images can take a long time, so we extend the timeout
    concat_timeout = casa_instance.child.timeout * len(obs_list)
    logger.info("*** Concatenating and making dirty maps ***")
    casa_out, errors = casa_instance.run_script(script, raise_on_severe=True,
                                                timeout=concat_timeout)
    if errors:
        logger.warning("Got the following errors (probably all ok)")
        for e in errors:
            logger.warning(e)

    logger.info("*** Getting initial estimates of RMS from dirty maps ***")
    for obs in obs_list+[concat_ob]:
        dmap = obs.maps_dirty.ms.image
        obs.rms_dirty_naive= subs.get_naive_image_rms_estimate(dmap)
        obs.rms_dirty= subs.get_correlated_image_rms_estimate(dmap)
        obs.rms_history.append(obs.rms_dirty)
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
    mask, mask_apertures, mask_sources = utils.generate_mask(
        chimconfig,
        extracted_sources=sources,
        monitoring_coords=monitor_coords,
        regionfile_path=os.path.join(fits_output_dir, 'mask_aps.reg')
    )
    logger.info("Generated mask:\n" + mask)


    # Assuming mask valid, i.e. not an empty field:
    if len(mask_apertures):
        logger.info("*** Running masked clean on each epoch ***")
        # Reset the concat_ob best rms estimate to that of dirty map,
        # to avoid over-cleaning.
        concat_ob.rms_best = concat_ob.rms_dirty
        # Run iterative masked cleans on epochal obs, and get updated RMS est:
        for obs in obs_list+[concat_ob]:
            subs.iterative_clean(obs,
                                 chimconfig,
                                 mask=mask,
                                 casa_output_dir=casa_output_dir,
                                 fits_output_dir=fits_output_dir,
                                 casa_instance=casa_instance)
            if mask_sources:
                obs.meta['masked_sources'] = [s.serialize(0,0)
                                              for s in mask_sources]

    logger.info("*** Running open clean on each epoch ***")
    # Finally, run a single open-clean on each epoch, to the RMS limit
    # determined from the masked clean.
    # If we ran a masked clean, then also create a 'hybrid' image,
    # initialized with the model from the masked clean,
    # then open-cleaned in addition.
    script=[]
    for obs in obs_list:
        modelimage = ''
        if len(mask_apertures):
            modelimage = obs.maps_masked.ms.model

        script.extend(
            subs.clean_and_export_fits(
                obs,
                casa_output_dir, fits_output_dir,
                threshold=chimconfig.clean.sigma_threshold * obs.rms_best,
                niter=chimconfig.clean.niter,
                mask='',
                modelimage='',
                other_clean_args=chimconfig.clean.other_args
            ))

        script.extend(
            subs.clean_and_export_fits(
                obs,
                casa_output_dir, fits_output_dir,
                threshold=chimconfig.clean.sigma_threshold * obs.rms_best,
                niter=chimconfig.clean.niter,
                mask='',
                modelimage=modelimage,
                other_clean_args=chimconfig.clean.other_args
            ))
    casa_out, errors = casa_instance.run_script(script, raise_on_severe=True)

    if chimconfig.pb_curve:
        logger.info("*** Applying primary beam correction ***")
        pb_exportfits_script = []
        for obs in obs_list+[concat_ob]:
                subs.apply_primary_beam_correction(
                    obs,
                    chimconfig,
                    casa_script=pb_exportfits_script)
        casa_instance.run_script(pb_exportfits_script)

    return obs_list, concat_ob

