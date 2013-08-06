

class obs_info(object):
    """
    We marshall relevant info on each observation into dictionaries.
    These are the keys.
    """
    name = 'name'  # String name of the obs (usually = filename minus extension)
    group = 'group'  # Name of the group to which this observation belongs
    metadata = 'metadata'  # Contains a sub-dict of all the AMI metadata
    uvfits = 'uvfits'
    vis = 'vis'
    dirty_maps = 'dirty_maps'
    dirty_fits = 'dirty_fits'
    dirty_rms_est = 'dirty_rms_est'
    clean_rms_est = 'clean_rms_est'
    open_clean_maps = 'open_clean_maps'
    open_clean_fits = 'open_clean_fits'
    masked_clean_maps = 'masked_clean_maps'
    masked_clean_fits = 'masked_clean_fits'

