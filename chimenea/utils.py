"""
Boring bits of code that make things happen, but aren't scientifically
significant.
"""

from StringIO import StringIO
import math
from collections import namedtuple
import logging
import simplejson as json
import pyrap.tables
from chimenea.obsinfo import ObsInfo
import chimenea.config
import drivecasa
logger = logging.getLogger()

MaskAp = namedtuple("MaskAp", "ra dec radius_deg")

def load_casa_imagedata(path_to_ms):
    """Loads the pixel data as a numpy array"""
    tbl = pyrap.tables.table(path_to_ms, ack=False)
    map = tbl[0]['map'].squeeze()
    map = map.transpose()
    return map


def fk5_ellipse_regions_from_extractedsources(sourcelist):
    """
    Return a string containing a DS9-compatible region file describing all the
    sources in sourcelist.
    """
    output = StringIO()
    print >> output, "# Region file format: DS9 version 4.1"
    print >> output, "global color=green dashlist=8 3 width=1 font=\"helvetica 10 normal\" select=1 highlite=1 dash=0 fixed=0 edit=1 move=1 delete=1 include=1 source=1"
    print >> output, "fk5"
    for source in sourcelist:
        print >> output, "ellipse(%f, %f, %f, %f, %f)" % (
            source.ra.value,
            source.dec.value,
            source.smaj_asec.value / 3600.,
            source.smin_asec.value / 3600.,
            math.degrees(source.theta) + 90
        )
    return output.getvalue()

def fk5_circle_regions_from_MaskAps(aperture_list):
    """
    Return a string containing a DS9-compatible region file describing the simple
    circular mask aperture objects.
    """
    output = StringIO()
    print >> output, "# Region file format: DS9 version 4.1"
    print >> output, "global color=green dashlist=8 3 width=1 font=\"helvetica 10 normal\" select=1 highlite=1 dash=0 fixed=0 edit=1 move=1 delete=1 include=1 source=1"
    print >> output, "fk5"
    for ap in aperture_list:
        print >> output, "circle(%f, %f, %f)" % (
            ap.ra,
            ap.dec,
            ap.radius_deg,
        )
    return output.getvalue()

def parse_monitoringlist_positions(opts):
    """Loads a list of monitoringlist (RA,Dec) tuples from cmd line opts object.

    Processes the flags "--monitor-coords" and "--monitor-list"
    NB This is just a dumb function that does not care about units,
    those should be matched against whatever uses the resulting values...
    """
    monitor_coords = []
    if opts.monitor_coords:
        try:
            monitor_coords.extend(json.loads(opts.monitor_coords))
        except ValueError:
            logger.error("Could not parse monitor-coords from command line:"
                         "string passed was:\n%s", opts.monitor_coords
                         )
            raise
    if opts.monitor_list:
        try:
            mon_list = json.load(open(opts.monitor_list))
            monitor_coords.extend(mon_list)
        except ValueError:
            logger.error("Could not parse monitor-coords from file: "
                              + opts.monitor_list)
            raise
    return monitor_coords

def load_listings(listings_path):
    """
    Loads a list of ObsInfo objects from a json file
    """
    # simplejson loads plain strings as simple 'str' objects:
    ami_listings = json.load(open(listings_path))
    all_obs = []
    for ami_rawfile, ami_obs in ami_listings.iteritems():
        all_obs.append(ObsInfo.from_processed_ami_info(ami_obs))
    return all_obs

def get_grouped_file_listings(all_obs):
    """
    Groups a list of ObsInfo objects by ``group`` attribute.

    Returns: Dict mapping groupname -> list of ObsInfo
    """
    grp_names = list(set([obs.group for obs in all_obs]))
    groups_dict = {}
    for g_name in grp_names:
        grp = [obs for obs in all_obs if obs.group == g_name]
        groups_dict[g_name] = grp
    return groups_dict

def generate_mask(chimconfig,
                  extracted_sources=None,
                  monitoring_coords=None,
                  regionfile_path=None
                  ):
    assert  isinstance(chimconfig, chimenea.config.ChimConfig)
    conf=chimconfig
    masked_sources = [s for s in extracted_sources
                      if s.sig > chimconfig.mask_source_sigma ]
    mask_apertures = []
    for ms in masked_sources:
        mask_apertures.append(
            MaskAp(ra = ms.ra.value,
                   dec = ms.dec.value,
                   radius_deg=conf.mask_ap_radius_degrees))
    if monitoring_coords:
        for mc in monitoring_coords:
            mask_apertures.append(
                MaskAp(ra=mc[0], dec=mc[1],
                       radius_deg=conf.mask_ap_radius_degrees))

    if regionfile_path is not None:
        with open(regionfile_path, 'w') as regionfile:
                regionfile.write(fk5_circle_regions_from_MaskAps(mask_apertures))

    mask_coords = [(str(s.ra) + 'deg', str(s.dec) + 'deg')
                       for s in mask_apertures]
    mask = drivecasa.utils.get_circular_mask_string(
        mask_coords,
        aperture_radius=str(conf.mask_ap_radius_degrees) + "deg")

    return mask, mask_apertures