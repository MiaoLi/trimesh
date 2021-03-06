'''
path.py

A library designed to work with vector paths.
'''

import numpy as np
import networkx as nx

from shapely.geometry import Polygon, Point
from copy import deepcopy
from collections import deque

from .simplify  import simplify
from .polygons  import polygons_enclosure_tree, is_ccw, medial_axis, polygon_hash
from .traversal import vertex_graph, closed_paths, discretize_path
from .io.export import export_path

from ..points    import plane_fit, transform_points
from ..geometry  import plane_transform
from ..grouping  import unique_rows
from ..units     import _set_units
from ..util      import decimal_to_digits, is_sequence
from ..constants import log, time_function
from ..constants import tol_path as tol


class Path(object):
    '''
    A Path object consists of two things:
    vertices: (n,[2|3]) coordinates, stored in self.vertices
    entities: geometric primitives (lines, arcs, and circles)
              that reference indices in self.vertices
    '''
    def __init__(self, 
                 entities = [], 
                 vertices = [],
                 metadata = None):
        '''
        entities:
            Objects which contain things like keypoints, as 
            references to self.vertices
        vertices:
            (n, (2|3)) list of vertices
        '''
        self.entities = np.array(entities)
        self.vertices = np.array(vertices)
        self.metadata = dict()

        if metadata.__class__.__name__ == 'dict':
            self.metadata.update(metadata)

        self._cache = {}

    @property
    def _cache_ok(self):
        processing = ('processing' in self._cache and 
                      self._cache['processing'])
        entity_ok = ('entity_count' in self._cache and 
                     (len(self.entities) == self._cache['entity_count']))
        ok = processing or entity_ok
        return ok

    def _geometry_id(self):
        return None
        
    def _cache_clear(self):
        self._cache = {}

    def _cache_verify(self):
        if not self._cache_ok:
            self._cache = {'entity_count': len(self.entities)}
            self.process()

    def _cache_get(self, key):
        self._cache_verify()
        if key in self._cache: 
            return self._cache[key]
        return None

    def _cache_put(self, key, value):
        self._cache_verify()
        self._cache[key] = value

    @property
    def paths(self):
        return self._cache_get('paths')

    @property
    def polygons_closed(self):
        return self._cache_get('polygons_closed')

    @property
    def root(self):
        return self._cache_get('root')

    @property
    def enclosure(self):
        return self._cache_get('enclosure')

    @property
    def enclosure_directed(self):
        return self._cache_get('enclosure_directed')

    @property
    def discrete(self):
        return self._cache_get('discrete')

    @property
    def scale(self):
        return np.max(np.ptp(self.vertices, axis=0))

    @property
    def bounds(self):
        return np.vstack((np.min(self.vertices, axis=0),
                          np.max(self.vertices, axis=0)))
    @property
    def box_size(self):
        return np.diff(self.bounds, axis=0)[0]

    @property
    def units(self):
        if 'units' in self.metadata:
            return self.metadata['units']
        else:
            return None
    
    @units.setter
    def units(self, units):
        self.metadata['units'] = units
            

    def set_units(self, desired, guess=False):
        _set_units(self, desired, guess)
        self._cache_clear()

    def transform(self, transform):
        self._cache = {}
        self.vertices = transform_points(self.vertices, transform)

    def rezero(self):
        self._cache = {}
        self.vertices -= self.vertices.min(axis=0)
        
    def merge_vertices(self):
        '''
        Merges vertices which are identical and replaces references
        '''
        digits = decimal_to_digits(tol.merge * self.scale, min_digits=1)
        unique, inverse = unique_rows(self.vertices, digits=digits)
        self.vertices = self.vertices[unique]
        for entity in self.entities: 
            entity.points = inverse[entity.points]

    def replace_vertex_references(self, replacement_dict):
        for entity in self.entities: entity.rereference(replacement_dict)

    def remove_entities(self, entity_ids):
        '''
        Remove entities by their index.
        '''
        if len(entity_ids) == 0: return
        kept = np.setdiff1d(np.arange(len(self.entities)), entity_ids)
        self.entities = np.array(self.entities)[kept]

    def remove_duplicate_entities(self):
        entity_hashes   = np.array([i.hash for i in self.entities])
        unique, inverse = unique_rows(entity_hashes)
        if len(unique) != len(self.entities):
            self.entities = np.array(self.entities)[unique]

    def vertex_graph(self):
        self._cache_verify()
        graph, closed = vertex_graph(self.entities)
        return graph

    def generate_closed_paths(self):
        '''
        Paths are lists of entity indices.
        '''
        paths = closed_paths(self.entities, self.vertices)
        self._cache_put('paths', paths)

    def referenced_vertices(self):
        referenced = deque()
        for entity in self.entities: 
            referenced.extend(entity.points)
        return np.array(referenced)
    
    def remove_unreferenced_vertices(self):
        '''
        Removes all vertices which aren't used by an entity
        Reindexes vertices from zero, and replaces references
        '''
        referenced       = self.referenced_vertices()
        unique_ref       = np.int_(np.unique(referenced))
        replacement_dict = dict()
        replacement_dict.update(np.column_stack((unique_ref, 
                                                 np.arange(len(unique_ref)))))
        self.replace_vertex_references(replacement_dict)
        self.vertices = self.vertices[[unique_ref]] 
        
    def discretize_path(self, path):
        '''
        Return a (n, dimension) list of vertices. 
        Samples arcs/curves to be line segments
        '''
        discrete = discretize_path(self.entities, self.vertices, path, scale=self.scale)
        return discrete
        
    def export(self, file_type='dict', file_obj=None):
        return export_path(self, 
                           file_type = file_type,
                           file_obj  = file_obj)

    def to_dict(self):
        export_dict = self.export(file_type='dict')
        return export_dict
        
    def process(self):
        self._cache['processing'] = True
        tic = time_function()        
        for func in self._process_functions():
            func()
        toc = time_function()
        self._cache['processing']   = False
        self._cache['entity_count'] = len(self.entities)
        return self

    def __add__(self, other):
        new_entities = deepcopy(other.entities)
        for entity in new_entities:
            entity.points += len(self.vertices)
        new_entities = np.append(deepcopy(self.entities), new_entities)
 
        new_vertices = np.vstack((self.vertices, other.vertices))
        new_meta     = deepcopy(self.metadata)
        new_meta.update(other.metadata)

        new_path = self.__class__(entities = new_entities,
                                  vertices = new_vertices,
                                  metadata = new_meta)
        return new_path
   
class Path3D(Path):
    def _process_functions(self): 
        return [self.merge_vertices,
                self.remove_duplicate_entities,
                self.remove_unreferenced_vertices,
                self.generate_closed_paths,
                self.generate_discrete]
               
    def generate_discrete(self):
        discrete = list(map(self.discretize_path, self.paths))
        self._cache_put('discrete', discrete)

    def to_planar(self, to_2D=None, normal=None, check=True):
        '''
        Check to see if current vectors are all coplanar.
        
        If they are, return a Path2D and a transform which will 
        transform the 2D representation back into 3 dimensions
        '''
        if to_2D is None:
            C, N = plane_fit(self.vertices)
            if normal is not None:
                N *= np.sign(np.dot(N, normal))
            to_2D = plane_transform(C,N)
 
        flat = transform_points(self.vertices, to_2D)
        
        if check and np.any(np.std(flat[:,2]) > tol.planar):
            log.error('points have z with deviation %f', np.std(flat[:,2]))
            raise NameError('Points aren\'t planar!')
            
        vector = Path2D(entities = deepcopy(self.entities), 
                        vertices = flat[:,0:2])
        to_3D  = np.linalg.inv(to_2D)

        return vector, to_3D

    def show(self, entities=False):
        if entities: self.plot_entities(show=True)
        else:        self.plot_discrete(show=True)

    def plot_discrete(self, show=False):
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        fig  = plt.figure()
        axis = fig.add_subplot(111, projection='3d')
        for discrete in self.discrete:
            axis.plot(*discrete.T)
        if show: plt.show()

    def plot_entities(self, show=False):
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        fig  = plt.figure()
        axis = fig.add_subplot(111, projection='3d')
        for entity in self.entities:
            vertices = self.vertices[entity.points]
            axis.plot(*vertices.T)        
        if show: plt.show()

class Path2D(Path):
    def _process_functions(self): 
        return [self.merge_vertices,
                self.remove_duplicate_entities,
                self.generate_closed_paths,
                self.generate_discrete,
                self.generate_enclosure_tree]
               
    @property
    def body_count(self):
        return len(self.root)

    @property
    def polygons_full(self):
        cached = self._cache_get('polygons_full')
        if cached:  return cached
        result = [None] * len(self.root)
        for index, root in enumerate(self.root):
            hole_index = self.connected_paths(root, include_self=False)
            holes = [p.exterior.coords for p in self.polygons_closed[hole_index]]
            shell = self.polygons_closed[root].exterior.coords
            result[index] = Polygon(shell  = shell,
                                    holes  = holes)
        self._cache_put('polygons_full', result)
        return result

    def area(self):
        '''
        Return the area of the polygons interior
        '''
        area = np.sum([i.area for i in self.polygons_full])
        return area
        
    def extrude(self, height, **kwargs):
        '''
        Extrude the current 2D path into a 3D mesh. 

        Arguments
        ----------
        height: float, how far to extrude the profile
        kwargs: passed directly to meshpy.triangle.build:
                triangle.build(mesh_info, 
                               verbose=False, 
                               refinement_func=None, 
                               attributes=False, 
                               volume_constraints=True, 
                               max_volume=None, 
                               allow_boundary_steiner=True, 
                               allow_volume_steiner=True, 
                               quality_meshing=True, 
                               generate_edges=None, 
                               generate_faces=False, 
                               min_angle=None)
        Returns
        --------
        mesh: trimesh object representing extruded polygon
        '''
        from ..creation import extrude_polygon
        result = [extrude_polygon(i, height, **kwargs) for i in self.polygons_full]
        if len(result) == 1: 
            return result[0]
        return result

    def medial_axis(self, resolution=None, clip=None):

        '''
        Find the approximate medial axis based
        on a voronoi diagram of evenly spaced points on the boundary of the polygon.

        Arguments
        ----------
        resolution: target distance between each sample on the polygon boundary
        clip:       [minimum number of samples, maximum number of samples]
                    specifying a very fine resolution can cause the sample count to
                    explode, so clip specifies a minimum and maximum number of samples
                    to use per boundary region. To not clip, this can be specified as:
                    [0, np.inf]

        Returns
        ----------
        medial:     Path2D object
        '''
        if resolution is None:
            resolution = self.scale / 1000.0
        medials = [medial_axis(i, resolution, clip) for i in self.polygons_full]
        return np.sum(medials)

    def generate_discrete(self):
        '''
        Turn a vector path consisting of entities of any type into polygons
        Uses shapely.geometry Polygons to populate self.polygons
        '''
        def path_to_polygon(path):
            discrete = discretize_path(self.entities, self.vertices, path, scale=self.scale)
            return Polygon(discrete)

        polygons = [None] * len(self.paths)
        for i, path in enumerate(self.paths):
            polygons[i] = path_to_polygon(path)
            # try to recover invalid polygons by zero- buffering
            if (not polygons[i].is_valid) or is_sequence(polygons[i]): 
                buffered = polygons[i].buffer(tol.merge*self.scale)

                if buffered.is_valid and not is_sequence(buffered):
                    unbuffered = buffered.buffer(-tol.merge*self.scale)
                    if unbuffered.is_valid and not is_sequence(unbuffered):
                        polygons[i] = unbuffered
                    else:
                        polygons[i] = buffered
                    log.warn('Recovered invalid polygon')
                else:
                    log.error('Unrecoverable polygon detected!')
                    log.error('Broken polygon vertices: \n%s', 
                              str(np.array(polygons[i].exterior.coords)))
        polygons = np.array(polygons)
        self._cache_put('polygons_closed', polygons)

    def generate_enclosure_tree(self):
        root, enclosure = polygons_enclosure_tree(self.polygons_closed)
        self._cache_put('root',      root)
        self._cache_put('enclosure',          enclosure.to_undirected())
        self._cache_put('enclosure_directed', enclosure)


    def connected_paths(self, path_id, include_self = False):
        if len(self.root) == 1:
            path_ids = np.arange(len(self.paths))
        else:
            path_ids = list(nx.node_connected_component(self.enclosure, path_id))
        if include_self: 
            return np.array(path_ids)
        return np.setdiff1d(path_ids, [path_id])
        
    def simplify(self):
        self._cache = {}
        simplify(self)

    def split(self):
        '''
        If the current Path2D consists of n 'root' curves,
        split them into a list of n Path2D objects
        '''
        if len(self.root) == 1:
            return [deepcopy(self)]
        result   = [None] * len(self.root)
        for i, root in enumerate(self.root):
            connected    = self.connected_paths(root, include_self=True)
            new_root     = np.nonzero(connected == root)[0]
            new_entities = deque()
            new_paths    = deque()
            new_metadata = {'split_2D' : i}
            new_metadata.update(self.metadata)

            for path in self.paths[connected]:
                new_paths.append(np.arange(len(path)) + len(new_entities))
                new_entities.extend(path)
            new_entities = np.array(new_entities)

            result[i] = Path2D(entities = deepcopy(self.entities[new_entities]),
                               vertices = deepcopy(self.vertices))
            result[i]._cache = {'entity_count'   : len(new_entities),
                                'paths'           : np.array(new_paths),
                                'polygons_closed' : self.polygons_closed[connected],
                                'metadata'        : new_metadata,
                                'root'            : new_root}
        return result

    def show(self):
        import matplotlib.pyplot as plt
        self.plot_discrete(show=True)
     
    def plot_discrete(self, show=False, transform=None, axes=None):
        self._cache_verify()
        import matplotlib.pyplot as plt
        plt.axes().set_aspect('equal', 'datalim')
        def plot_transformed(vertices, color='g'):
            if transform is None: 
                if axes is None:
                    plt.plot(*vertices.T, color=color)
                else:
                    axes.plot(*vertices.T, color=color)
            else:
                transformed = transform_points(vertices, transform)
                plt.plot(*transformed.T, color=color)
        for i, polygon in enumerate(self.polygons_closed):
            color = ['g','k'][i in self.root]
            plot_transformed(np.column_stack(polygon.boundary.xy), color=color)
        if show: plt.show()

    def plot_entities(self, show=False):
        import matplotlib.pyplot as plt
        plt.axes().set_aspect('equal', 'datalim')
        eformat = {'Line0'  : {'color'  :'g', 'linewidth':1}, 
                   'Arc0'   : {'color'  :'r', 'linewidth':1}, 
                   'Arc1'   : {'color'  :'b', 'linewidth':1},
                   'Bezier0': {'color'  :'k', 'linewidth':1},
                   'BSpline0': {'color' :'m', 'linewidth':1},
                   'BSpline1': {'color' :'m', 'linewidth':1}}
        for entity in self.entities:
            discrete = entity.discrete(self.vertices)
            e_key    = entity.__class__.__name__ + str(int(entity.closed))
            plt.plot(discrete[:,0], 
                     discrete[:,1], 
                     **eformat[e_key])
        if show: plt.show()

    def identifier(self):
        if len(self.polygons_full) != 1: 
            raise TypeError('Identifier only valid for single body')
        return polygon_hash(self.polygons_full[0])
