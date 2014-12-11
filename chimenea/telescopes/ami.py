"""Settings and routines specific to AMI-LA"""
from __future__ import absolute_import
from driveami import keys as meta_keys

from chimenea.config import SourcefinderConfig, CleanConfig, ChimConfig

import logging
logger = logging.getLogger(__name__)

image_pixel_size = 512

ami_clean_args= {
    "spw": '0:0~5',
    "imsize": [image_pixel_size, image_pixel_size],
    "cell": ['5.0arcsec'],
    "pbcor": False,
    # "weighting": 'natural',
    "weighting": 'briggs',
    "robust": 0.5,
    #          "weighting":'uniform',
    "psfmode": 'clark',
    "imagermode": 'csclean',
}

clean_conf = CleanConfig(niter=500, sigma_threshold=3,
                         other_args=ami_clean_args)

sf_conf = SourcefinderConfig(detection_thresh=5., analysis_thresh=3.,
                             back_size=64,
                             margin=128,
                             radius=None)


ami_chimconfig = ChimConfig(clean_conf, sf_conf,
                            max_recleans=3,
                            reclean_rms_convergence=0.05,
                            mask_source_sigma = 5.5,
                            mask_ap_radius_degrees = 60./3600,
                            )

default_rain_min, default_rain_max = 0.8, 1.2

def reject_bad_obs(obs_list,
                   rain_min=default_rain_min,
                   rain_max=default_rain_max):
    """
    Run quality control on a list of ObsInfo.

    Currently just filters on rain gauge values.

    Returns 2 lists: [passed],[failed]
    """

    good_files = []
    rain_rejected = []
    for obs in obs_list:
        rain_amp_mod = obs.meta[meta_keys.rain]
        if (rain_amp_mod > rain_min and rain_amp_mod < rain_max):
            good_files.append(obs)
        else:
            rain_rejected.append(obs)
            logger.info("Rejected file %s due to rain value %s" %
                        (obs.name,rain_amp_mod))
    return good_files, rain_rejected