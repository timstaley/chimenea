"""
Defines the ObsInfo class and its component members.
"""

from driveami import keys as meta_keys

class CleanMaps(object):
    """
    Just a bag of attributes, representing data-products from Clean.
    """
    def __init__(self, image=None, model=None, residual=None, psf=None,
                 mask=None, flux=None):
        self.image = image
        self.model = model
        self.residual = residual
        self.psf = psf
        self.mask = mask
        self.flux = flux


class ObsInfo(object):
    """
    Info relating to a single epochal observation.

    Used to carry around the paths of the many data by-products in
    nested form.

    By composing this information into a class, we allow for slightly
    neater code.
    """
    class MsFits(object):
        """
        Attribute storing paths to MeasurementSet or FITS copy of clean maps.
        """
        def __init__(self):
            self.ms = CleanMaps()
            self.fits = CleanMaps()

    def __init__(self, name, group, metadata, uvfits=None):
        #Typically contains the metadata from a processed AMI rawfile:
        self.meta = metadata

        self.name = name
        self.group = group
        self.uv_fits = uvfits
        self.uv_ms = None
        self.maps_dirty = ObsInfo.MsFits()
        self.maps_open = ObsInfo.MsFits()
        self.maps_masked = ObsInfo.MsFits()
        self.rms_dirty=None
        self.rms_best=None
        self.rms_delta=float('inf')

    @staticmethod
    def from_processed_ami_info(ami_info_dict):
        """
        Load the relevant attributes from a dict of AMI-dataset metadata.
        """
        d = ami_info_dict
        return ObsInfo(name = d[meta_keys.obs_name],
                       group= d[meta_keys.group_name],
                       metadata=d,
                       uvfits=d[meta_keys.target_uvfits])