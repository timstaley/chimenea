"""Various dumb 'struct' classes to hold configuration parameters"""

class SourcefinderConfig(object):
    def __init__(self,
                 detection_thresh, analysis_thresh,
                 back_size,
                 margin,
                 radius=None,
                 deblend_nthresh=32,
                 force_beam=False
    ):
        """Config variables relating to source extraction"""
        # For passing to the TKP PySE source-extractor:
        self.detection_thresh = detection_thresh
        self.analysis_thresh = analysis_thresh
        self.back_size = back_size
        self.margin = margin
        self.radius = radius
        self.deblend_nthresh = deblend_nthresh
        self.force_beam = force_beam



class CleanConfig(object):
    """Config variables relating to the Clean algorithm"""
    def __init__(self,
                 niter,
                 sigma_threshold,
                 other_args):
        self.niter = niter
        self.sigma_threshold = sigma_threshold
        self.other_args = other_args


class ChimConfig(object):
    """
    All the scientifically significant variables for a chimenea reduction run.
    """

    def __init__(self, clean_conf, sf_conf,
                 max_recleans,
                 reclean_rms_convergence,
                 mask_source_sigma,
                 mask_ap_radius_degrees,
                 pb_correction_curve,
                 pb_cutoff_pix
                 ):
        assert isinstance(clean_conf, CleanConfig)
        assert isinstance(sf_conf, SourcefinderConfig)
        self.clean= clean_conf
        self.sourcefinding = sf_conf
        self.max_recleans = max_recleans
        self.reclean_rms_convergence = reclean_rms_convergence

        self.mask_source_sigma = mask_source_sigma
        self.mask_ap_radius_degrees = mask_ap_radius_degrees

        self.pb_curve= pb_correction_curve
        self.pb_cutoff = pb_cutoff_pix

