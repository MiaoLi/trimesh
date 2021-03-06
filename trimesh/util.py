import numpy as np
import time
import logging

from sys import version_info

if version_info.major >= 3:
    basestring = str

_TOL_ZERO = 1e-12

def unitize(points, check_valid=False):
    '''
    Flexibly turn a list of vectors into a list of unit vectors.
    
    Arguments
    ---------
    points:       (n,m) or (j) input array of vectors. 
                  For 1D arrays, points is treated as a single vector
                  For 2D arrays, each row is treated as a vector
    check_valid:  boolean, if True enables valid output and checking

    Returns
    ---------
    unit_vectors: (n,m) or (j) length array of unit vectors

    valid:        (n) boolean array, output only if check_valid.
                   True for all valid (nonzero length) vectors, thus m=sum(valid)
    '''
    points       = np.array(points)
    axis         = len(points.shape) - 1
    length       = np.sum(points ** 2, axis=axis) ** .5
    if check_valid:
        valid = np.greater(length, _TOL_ZERO)
        if axis == 1: 
            unit_vectors = (points[valid].T / length[valid]).T
        elif len(points.shape) == 1 and valid: 
            unit_vectors = points / length
        else:         
            unit_vectors = []
        return unit_vectors, valid        
    else: 
        unit_vectors = (points.T / length).T
    return unit_vectors

def transformation_2D(offset=[0.0,0.0], theta=0.0):
    '''
    2D homogeonous transformation matrix
    '''
    T = np.eye(3)
    s = np.sin(theta)
    c = np.cos(theta)

    T[0,0:2] = [ c, s]
    T[1,0:2] = [-s, c]
    T[0:2,2] = offset
    return T

def euclidean(a, b):
    '''
    Euclidean distance between vectors a and b
    '''
    return np.sum((np.array(a) - b)**2) ** .5

def is_file(obj):
    return hasattr(obj, 'read')

def is_string(obj):
    return isinstance(obj, basestring)

def is_sequence(obj):
    '''
    Returns True if obj is a sequence.
    '''
    seq = (not hasattr(obj, "strip") and
           hasattr(obj, "__getitem__") or
           hasattr(obj, "__iter__"))

    seq = seq and not isinstance(obj, dict)
    # numpy sometimes returns objects that are single float64 values
    # but sure look like sequences, so we check the shape
    if hasattr(obj, 'shape'):
        seq = seq and obj.shape != ()
    return seq

def make_sequence(obj):
    '''
    Given an object, if it is a sequence return, otherwise
    add it to a length 1 sequence and return.

    Useful for wrapping functions which sometimes return single 
    objects and other times return lists of objects. 
    '''
    if is_sequence(obj): return np.array(obj)
    else:                return np.array([obj])

def is_ccw(points):
    '''
    Given an (n,2) set of points, return True if they are counterclockwise
    '''
    xd = np.diff(points[:,0])
    yd = np.sum(np.column_stack((points[:,1], 
                                 points[:,1])).reshape(-1)[1:-1].reshape((-1,2)), axis=1)
    area = np.sum(xd*yd)*.5
    return area < 0

def diagonal_dot(a, b):
    '''
    Dot product by row of a and b.

    Same as np.diag(np.dot(a, b.T)) but without the monstrous 
    intermediate matrix.
    '''
    result = (np.array(a)*b).sum(axis=1)
    return result

def three_dimensionalize(points, return_2D=True):
    '''
    Given a set of (n,2) or (n,3) points, return them as (n,3) points

    Arguments
    ----------
    points:    (n, 2) or (n,3) points
    return_2D: boolean flag

    Returns
    ----------
    if return_2D: 
        is_2D: boolean, True if points were (n,2)
        points: (n,3) set of points
    else:
        points: (n,3) set of points
    '''
    points = np.array(points)
    shape = points.shape
 
    if len(shape) != 2:
        raise ValueError('Points must be 2D array!')

    if shape[1] == 2:
        points = np.column_stack((points, np.zeros(len(points))))
        is_2D = True
    elif shape[1] == 3:
        is_2D = False
    else:
        raise ValueError('Points must be (n,2) or (n,3)!')

    if return_2D: 
        return is_2D, points
    return points

def grid_arange_2D(bounds, step):
    '''
    Return a 2D grid with specified spacing

    Arguments
    ---------
    bounds: (2,2) list of [[minx, miny], [maxx, maxy]]
    step:   float, separation between points
    
    Returns
    -------
    grid: (n, 2) list of 2D points
    '''
    x_grid = np.arange(*bounds[:,0], step = step)
    y_grid = np.arange(*bounds[:,1], step = step)
    grid   = np.dstack(np.meshgrid(x_grid, y_grid)).reshape((-1,2))
    return grid

def grid_linspace_2D(bounds, count):
    '''
    Return a count*count 2D grid

    Arguments
    ---------
    bounds: (2,2) list of [[minx, miny], [maxx, maxy]]
    count:  int, number of elements on a side
    
    Returns
    -------
    grid: (count**2, 2) list of 2D points
    '''
    x_grid = np.linspace(*bounds[:,0], count = count)
    y_grid = np.linspace(*bounds[:,1], count = count)
    grid   = np.dstack(np.meshgrid(x_grid, y_grid)).reshape((-1,2))
    return grid

def replace_references(data, reference_dict):
    # Replace references in place
    view = np.array(data).view().reshape((-1))
    for i, value in enumerate(view):
        if value in reference_dict:
            view[i] = reference_dict[value]
    return view

def multi_dict(pairs):
    '''
    Given a set of key value pairs, create a dictionary. 
    If a key occurs multiple times, stack the values into an array.

    Can be called like the regular dict(pairs) constructor

    Arguments
    ----------
    pairs: (n,2) array of key, value pairs

    Returns
    ----------
    result: dict, with all values stored (rather than last with regular dict)

    '''
    result = dict()
    for k, v in pairs:
        if k in result:
            result[k].append(v)
        else:
            result[k] = [v]
    return result
    
def is_binary_file(file_obj):
    '''
    Returns True if file has non-ASCII characters (> 0x7F, or 127)
    Should work in both Python 2 and 3
    '''
    start  = file_obj.tell()
    fbytes = file_obj.read(1024)
    file_obj.seek(start)
    is_str = isinstance(fbytes, str)
    for fbyte in fbytes:
        if is_str: code = ord(fbyte)
        else:      code = fbyte
        if code > 127: return True
    return False

def decimal_to_digits(decimal, min_digits=None):
    digits = abs(int(np.log10(decimal)))
    if min_digits is not None:
        digits = np.clip(digits, min_digits, 20)
    return digits

def attach_to_log(log_level=logging.DEBUG, blacklist=[]):
    '''
    Attach a stream handler to all loggers, so their output can be seen
    on the console
    '''
    try: 
        from colorlog import ColoredFormatter
        formatter = ColoredFormatter(
            "%(log_color)s%(levelname)-8s%(reset)s %(filename)17s:%(lineno)-4s  %(blue)4s%(message)s",
            datefmt = None,
            reset   = True,
            log_colors = {'DEBUG':    'cyan',
                          'INFO':     'green',
                          'WARNING':  'yellow',
                          'ERROR':    'red',
                          'CRITICAL': 'red' } )
    except ImportError: 
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s (%(filename)s:%(lineno)3s) %(message)s", 
            "%Y-%m-%d %H:%M:%S")
    handler_stream = logging.StreamHandler()
    handler_stream.setFormatter(formatter)
    handler_stream.setLevel(log_level)

    for logger in logging.Logger.manager.loggerDict.values():
        if logger.__class__.__name__ != 'Logger': continue
        if (logger.name in ['TerminalIPythonApp',
                            'PYREADLINE'] or 
            logger.name in blacklist):
            continue
        logger.addHandler(handler_stream)
        logger.setLevel(log_level)
    np.set_printoptions(precision=5, suppress=True)

class TrackedArray(np.ndarray):
    '''
    Track changes in a numpy ndarray. 
    '''
    def __array_finalize__(self, obj):
        self._set_modified()
        if hasattr(obj, '_set_modified'):
            obj._set_modified(self._modified)

    def _set_modified(self, value=None):
        if value is None:
            self._modified = np.random.random()
        else: 
            self._modified = value

    def modified(self):
        result  = float(id(self))
        result *= self._modified
        if result < 1e8: result *= 1e6
        return int(result)
        
    def __hash__(self):
        return self.modified()

    def __setitem__(self, i, y):
        super(self.__class__, self).__setitem__(i, y)
        self._set_modified()
        
    def __setslice__(self, i, j, y):
        super(self.__class__, self).__setslice__(i, j, y)
        self._set_modified()

def tracked_array(array):
    '''
    Subclass a numpy ndarray to track changes
    '''
    return np.array(array).view(TrackedArray)

class Cache:
    def __init__(self, id_function):
        self.id_function = id_function
        self.id_current = None
        self.cache = {}
        
    def get(self, key):
        self.verify()
        if key in self.cache: 
            return self.cache[key]
        return None
        
    def verify(self):
        id_new = self.id_function()
        if id_new != self.id_current: 
            self.clear()
        self.id_current = id_new

    def clear(self):
        self.cache = {}

    def set(self, key, value):
        self.verify()
        self.cache[key] = value
        return value
