import numpy as np
import amisurvey.utils as utils
import pyrap
import pyrap.images


default_ami_central_freq = 15.37e9

def ami_sigma_arcmin(freq_hz):
    return 24.905/(freq_hz*1e-9) + 0.79


class GaussianCurve():
    def __init__(self, sigma):
        self.sigma=sigma
    def correction(self, r):
        return np.exp( -(r/self.sigma)**2 / 2.)


def _pixel_radius_map(array_shape, pointing_centre):
    cx, cy = pointing_centre
    def radius(x,y):
        return np.sqrt( (x-cx)**2 + (y-cy)**2 )
    return np.fromfunction(radius, array_shape)

def _correction_map(pixel_radius_correction, array_shape, pointing_centre):
    """
    Args
    ----
    curve: function f(r)
        mapping radius *in pixels* from centre -> pb. corr. value.
    shape: numpy.ndarray.shape
        Shape of the numpy array to generate (2D)
    pointing_centre: tuple (x,y)
        x,y co-ordinates of the pointing centre
        (NB uses zero-based indexing a'la numpy)
    """
    radius_map = _pixel_radius_map(array_shape, pointing_centre)
    correction_map = pixel_radius_correction(radius_map)
    return correction_map

def _central_position(shape):
    return (shape[0]/2. - 0.5, shape[1]/2. - 0.5)

def get_pixel_scale_arcmin(path_to_casa_map):
    table = pyrap.tables.table(path_to_casa_map,
                             ack=False
                             )
    units = table.getkeyword('coords')['direction0']['units']
    assert units[0]==units[1]
    assert units[0]=='rad'
    cdelt = table.getkeyword('coords')['direction0']['cdelt']
    assert abs(cdelt[1])==abs(cdelt[0])
    pix_scale_rad = abs(cdelt[0])
    return pix_scale_rad*180/np.pi*60

def make_mask(shape, centre, radius_pix):
    y,x = np.ogrid[-centre[0]:shape[0]-centre[0], -centre[1]:shape[1]-centre[1]]
    r=radius_pix
    mask = x*x + y*y > r*r
    return mask

def correct_primary_beam_map(path_to_casa_flux_map):
    arcmin_per_pix = get_pixel_scale_arcmin(path_to_casa_flux_map)
    pb_sigma_arcmin = ami_sigma_arcmin(default_ami_central_freq)
    sigma_pix = pb_sigma_arcmin/arcmin_per_pix
    curve = GaussianCurve(sigma=sigma_pix)

    img = pyrap.images.image(path_to_casa_flux_map)
    map = img.getdata()
    rawshape = map.shape
    map = map.squeeze()
    centre = _central_position(map.shape)
    pbmap = _correction_map(curve.correction,map.shape, centre)
    img.putdata(pbmap.reshape(rawshape))
    mask = make_mask(map.shape,centre,5*sigma_pix)
    pbmap = np.ma.array(data=pbmap, mask=mask)
    img.putmask(mask.reshape(rawshape))
    return pbmap
