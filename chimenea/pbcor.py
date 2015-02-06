import numpy as np
import os
import shutil
import pyrap
import pyrap.images
from chimenea.obsinfo import ObsInfo

import logging
logger = logging.getLogger(__name__)

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

# def get_pixel_scale_arcmin(path_to_casa_map):
#     table = pyrap.tables.table(path_to_casa_map,
#                              ack=False
#                              )
#     units = table.getkeyword('coords')['direction0']['units']
#     assert units[0]==units[1]
#     assert units[0]=='rad'
#     cdelt = table.getkeyword('coords')['direction0']['cdelt']
#     assert abs(cdelt[1])==abs(cdelt[0])
#     pix_scale_rad = abs(cdelt[0])
#     return pix_scale_rad*180/np.pi*60

def make_mask(shape, centre, cutoff_radius_pix):
    y,x = np.ogrid[-centre[0]:shape[0]-centre[0], -centre[1]:shape[1]-centre[1]]
    r=cutoff_radius_pix
    mask = x*x + y*y > r*r
    return mask

def generate_primary_beam_response_map(flux_map_path,
                             pb_sensitivity_curve,
                             cutoff_radius):
    """
    Generates a primary-beam response map.

    Args:
        flux_map: Path to the (inaccurate) default CASA-generated flux map.
        pb_sensitivity_curve: Primary beam sensitivity as a function of radius
            in units of image pixels. (Should be 1.0 at the exact centre).
        cutoff_radius: Radius at which to mask the output image (avoids
            extremely high corrected values for noise fluctuations at large
            radii). Units: image pixels.
    Returns:
        pbmap (pyrap.images.image): Pyrap image object containing the 'flux'
            map (i.e. primary beam response values).
    """
    logger.debug("Correcting PB map at {}".format(flux_map_path))
    img = pyrap.images.image(flux_map_path)
    pix_array = img.getdata()
    rawshape = pix_array.shape
    pix_array = pix_array.squeeze()
    centre = _central_position(pix_array.shape)
    pbmap = _correction_map(pb_sensitivity_curve,pix_array.shape, centre)
    img.putdata(pbmap.reshape(rawshape))
    mask = make_mask(pix_array.shape,centre,cutoff_radius)
    pbmap = np.ma.array(data=pbmap, mask=mask)
    img.putmask(mask.reshape(rawshape))
    return pbmap

def generate_pb_corrected_image(image_path, pbcor_image_path,
                                pb_response_map):
    logger.debug("Applying PB correction to {}".format(image_path))
    logger.debug("Will save corrected map to {}".format(pbcor_image_path))
    if os.path.isdir(pbcor_image_path):
        shutil.rmtree(pbcor_image_path)
    shutil.copytree(image_path, pbcor_image_path)
    img = pyrap.images.image(pbcor_image_path)
    pix_array = img.getdata()
    rawshape = pix_array.shape
    pix_array = pix_array.squeeze()
    pbcor_pix_array = pix_array/pb_response_map
    img.putdata(pbcor_pix_array.data.reshape(rawshape))
    img.putmask(pbcor_pix_array.mask.reshape(rawshape))

def apply_pb_correction(obs,
                        pb_sensitivity_curve,
                        cutoff_radius):
    """
    Updates the primary beam response maps for cleaned images in an ObsInfo object.

    Args:
        obs (ObsInfo): Observation to generate maps for.
        pb_sensitivity_curve: Primary beam sensitivity as a function of radius
            in units of image pixels. (Should be 1.0 at the exact centre).
        cutoff_radius: Radius at which to mask the output image (avoids
            extremely high corrected values for noise fluctuations at large
            radii). Units: image pixels.
    """
    assert isinstance(obs, ObsInfo)

    def update_pb_map_for_img(flux_map_path):
        pbmap = generate_primary_beam_response_map(flux_map_path,
                                          pb_sensitivity_curve,
                                          cutoff_radius)
        return pbmap

    def process_clean_maps(clean_maps):
        pbmap = update_pb_map_for_img(clean_maps.flux)
        img_path = clean_maps.image
        pb_img_path = img_path+'.pbcor'
        generate_pb_corrected_image(img_path, pb_img_path,
                                    pbmap)
        clean_maps.pbcor = pb_img_path

    if obs.maps_masked.ms.image:
        process_clean_maps(obs.maps_masked.ms)
    if obs.maps_open.ms.image:
        process_clean_maps(obs.maps_open.ms)