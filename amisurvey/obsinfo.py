"""
Defines the ObsInfo class and its component members.
"""

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
        self.name = name
        self.group = group
        self.meta = metadata
        self.uv_fits = uvfits
        self.uv_ms = None
        self.dirty_maps = ObsInfo.MsFits()
        self.open_clean_maps = ObsInfo.MsFits()
        self.masked_clean_maps = ObsInfo.MsFits()
        self.dirty_rms=None
        self.best_rms=None

