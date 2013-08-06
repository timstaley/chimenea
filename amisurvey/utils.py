import pyrap.tables

def load_casa_imagedata(path_to_ms):
    """Loads the pixel data as a numpy array"""
    tbl = pyrap.tables.table(path_to_ms, ack=False)
    map = tbl[0]['map'].squeeze()
    map = map.transpose()
    return map