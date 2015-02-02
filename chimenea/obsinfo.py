"""
Defines the ObsInfo class and its component members.
"""
import json

class CleanMaps(object):
    """
    Just a bag of attributes, representing data-products from Clean.
    """
    def __init__(self, image=None, model=None, residual=None, psf=None,
                 mask=None, flux=None, pbcor=None):
        self.image = image
        self.model = model
        self.residual = residual
        self.psf = psf
        self.mask = mask
        self.flux = flux
        self.pbcor = pbcor



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
        self.rms_delta=None

    def __repr__(self):
        return json.dumps(self, cls=ObsInfo.Encoder, indent=4, sort_keys=True)


    class Encoder(json.JSONEncoder):
        def default(self,obj):
            for someclass in serializable:
                if isinstance(obj, someclass):
                    return {someclass.__name__:obj.__dict__}
            return json.JSONEncoder.default(self,obj)


    class Decoder(json.JSONDecoder):
        def __init__(self, **kwargs):
            # super(ObsInfo.Decoder, self).__init__(object_hook=self.as_obsinfo,
            #                                       **kwargs)
            json.JSONDecoder.__init__(self, object_hook=self.as_obsinfo,
                                      **kwargs)

        @staticmethod
        def as_obsinfo(dct):
            for someclass in serializable:
                if someclass.__name__ in dct:
                    o = someclass.__new__(someclass)
                    o.__dict__.update(dct[someclass.__name__])
                    return o
            return dct

serializable = [ObsInfo,ObsInfo.MsFits,CleanMaps]






