"""
Subroutines, mostly composed from multiple drivecasa calls.

Some scientifically important arguments are encoded as the defaults here.
"""

import os
import logging

import drivecasa
from chimenea.obsinfo import ObsInfo, CleanMaps
import chimenea.utils as utils
import chimenea.sigmaclip
import chimenea.config
from tkp.accessors import sourcefinder_image_from_accessor
from tkp.accessors import FitsImage

logger = logging.getLogger(__name__)



def import_and_concatenate(obs_list, casa_output_dir):
    """
    Import uvfits, create a concatenated obs.
    *Returns:*
      - tuple: (script, concat_obs_info)
    """
    groups = set([obs.group for obs in obs_list])
    assert len(groups) == 1
    group_name = groups.pop()
    script = []
    for obs in obs_list:
        assert isinstance(obs, ObsInfo)
        obs.uv_ms = drivecasa.commands.import_uvfits(script,
                                             obs.uv_fits,
                                             out_dir=casa_output_dir,
                                             overwrite=True)


    # Concatenate the data to create a master image:
    concat_obs = ObsInfo(name = group_name + '_concat',
                         group = group_name,
                         metadata=None)

    concat_obs.uv_ms = drivecasa.commands.concat(
                                     script,
                                     [obs.uv_ms for obs in obs_list],
                                     out_basename=concat_obs.name,
                                     out_dir=casa_output_dir,
                                     overwrite=True)
    return script, concat_obs

def clean_and_export_fits(obs_info,
                          casa_output_dir, fits_output_dir,
                          threshold,
                          niter,
                          mask,
                          other_clean_args):
    """
    Runs clean. Uses a little logic on the arguments to perform
    output-path determination magic.

    **Args**:

    - obs_info: ObsInfo object
    - casa_output_dir, fits_output_dir: obvious
    - threshold: Clean threshold, in Janskys.
    - niter: Max number of iterations per Clean invocation, passed to CASA-Clean.
    - mask: String representing the mask apertures, passed to CASA-Clean.


    *Returns:* script
    """
    assert isinstance(obs_info, ObsInfo)
    logger.debug('Scripting clean for %s, niter=%s, threshold=%sJy',
                 obs_info.name, niter, threshold)
    script = []
    fits_basename=None
    # Determine if we're running the dirty, open-clean or masked clean
    # Then set paths accordingly:
    if niter == 0:
        #Dirty map generation
        maps_dir =  os.path.join(casa_output_dir, 'dirty')
        msfits_attr = 'maps_dirty'
    elif mask =='':
        #Open Clean
        maps_dir = os.path.join(casa_output_dir, 'open_clean')
        msfits_attr = 'maps_open'
        fits_basename = obs_info.name + '_open'
    else:
        #Masked clean
        maps_dir = os.path.join(casa_output_dir, 'masked_clean')
        msfits_attr = 'maps_masked'
        fits_basename = obs_info.name + '_masked'

    maps = drivecasa.commands.clean(script,
                                    vis_path=obs_info.uv_ms,
                                    niter=niter,
                                    threshold_in_jy=threshold,
                                    mask=mask,
                                    other_clean_args=other_clean_args,
                                    out_dir=maps_dir,
                                    overwrite=True)

    msfits = getattr(obs_info,msfits_attr)
    msfits.ms = CleanMaps(**maps._asdict())

    if fits_basename is None:
        fits_outpath = None
    else:
        fits_outpath = os.path.join(fits_output_dir, fits_basename + '.fits')
    exported_fits = drivecasa.commands.export_fits(script,
                                        image_path=maps.image,
                                        out_dir=fits_output_dir,
                                        out_path=fits_outpath,
                                        overwrite=True)
    msfits.fits.image = exported_fits
    return script


def run_sourcefinder(path_to_fits_image,
                     sourcefinder_config
                      ):

    sfconf = sourcefinder_config
    image_config = {
        "back_size_x": sfconf.back_size,
        "back_size_y": sfconf.back_size,
        "margin": sfconf.margin,
        "radius": sfconf.radius,
        }

    sfimg = sourcefinder_image_from_accessor(FitsImage(path_to_fits_image),
                                             **image_config)
    results = sfimg.extract(sfconf.detection_thresh, sfconf.analysis_thresh,
                            deblend_nthresh=sfconf.deblend_nthresh,
                            force_beam=sfconf.force_beam)
    return results

def get_image_rms_estimate(path_to_casa_image):
    map = utils.load_casa_imagedata(path_to_casa_image)
    return chimenea.sigmaclip.rms_with_clipped_subregion(map, sigma=3, f=3)

def iterative_clean(obs,
                    chimconfig,
                    mask,
                    casa_output_dir,
                    fits_output_dir,
                    casa_instance):
    assert isinstance(obs, ObsInfo)
    assert isinstance(chimconfig, chimenea.config.ChimConfig)
    casa = casa_instance

    logging.info("Iteratively cleaning %s", obs.name)
    # Always run first clean:
    reclean_iter = 0
    obs.rms_delta = float('inf')
    while (reclean_iter < chimconfig.max_recleans and
                   obs.rms_delta > chimconfig.reclean_rms_convergence):
        logging.debug("Reclean cycle %s", reclean_iter)
        reclean_iter+=1
        script = []

        script.extend(
            clean_and_export_fits(obs,
                           casa_output_dir, fits_output_dir,
                           threshold=obs.rms_best*chimconfig.clean.sigma_threshold,
                           niter=chimconfig.clean.niter,
                           mask=mask,
                           other_clean_args=chimconfig.clean.other_args
                            ))
        casa_out, errors = casa.run_script(script, raise_on_severe=True)

        # Get new estimate of RMS for each map:
        logger.debug("Re-estimating RMS...")
        if not mask:
            map = obs.maps_open.ms.residual
        else:
            map = obs.maps_masked.ms.residual
        new_rms = get_image_rms_estimate(map)
        obs.rms_delta = (obs.rms_best - new_rms ) / obs.rms_best
        logger.debug("%s; RMS est, old: %s, new:%s, delta:%s",
                     obs.name, obs.rms_best, new_rms, obs.rms_delta)
        obs.rms_best=new_rms
        if (obs.rms_delta<0):
            logger.warn("%s RMS *increased* after clean, delta: %s",
                        obs.name, obs.rms_delta)
    return