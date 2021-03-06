import numpy as np
import networkx as nx

from collections import deque

from ..points    import unitize
from ..util      import is_ccw
from ..constants import tol_path as tol


def vertex_graph(entities):
    '''
    Given a set of entity objects (which have node and closed attributes)
    '''
    graph  = nx.Graph()
    closed = deque()
    for index, entity in enumerate(entities):
        if entity.closed:
            closed.append(index)
        else:             
            graph.add_edges_from(entity.nodes, entity_index = index)
    return graph, np.array(closed)
    
def edge_direction(a, b):
    '''
    Given two edges, find out whether the first edge needs to be
    reversed to generate path
    '''
    if   a[0] == b[0]: return  1
    elif a[0] == b[1]: return -1
    elif a[1] == b[1]: return  1
    elif a[1] == b[0]: return -1
    else: 
        raise ValueError('Can\'t determine direction, edges aren\'t connected!')

def vertex_to_entity_path(vertex_path, graph, entities, vertices):
    # vertex path contains 'nodes', which are always on the path,
    # regardless of entity type. 
    # this is essentially a very coarsely discretized polygon
    # thus it is valid to compute if the path is counter-clockwise on these
    # vertices relatively cheaply, and reverse the path if it is clockwise
    ccw_dir = (is_ccw(vertices[np.append(vertex_path, vertex_path[0])])*2) - 1    
    entity_path = deque()
    for i in range(len(vertex_path)+1):
        path_pos = np.mod(np.arange(2) + i, len(vertex_path))
        vertex_index = np.array(vertex_path)[[path_pos]]
        entity_index = graph.get_edge_data(*vertex_index)['entity_index']
        if ((len(entity_path) == 0) or 
            ((entity_path[-1] != entity_index) and 
             (entity_path[0]  != entity_index))):
            entity        = entities[entity_index]
            direction     = edge_direction(vertex_index, entity.end_points) 
            direction    *= ccw_dir
            entity.points = entity.points[::direction]
            entity_path.append(entity_index)
    entity_path = np.array(entity_path)[::ccw_dir]
    return entity_path

def connected_open(graph):
    broken = set()
    for node, degree in graph.degree().items():
        if degree == 2:    continue
        if node in broken: continue
        [broken.add(i) for i in nx.node_connected_component(g, node)]
    okay = set(graph.nodes()).difference(broken)
    return broken, okay

def closed_paths(entities, vertices):
    '''
    Paths are lists of entity indices.
    We first generate vertex paths using graph cycle algorithms, 
    and then convert them to entity paths using 
    a frankly worrying number of loops and conditionals...

    This will also change the ordering of entity.points in place, so that
    a path may be traversed without having to reverse the entity
    '''
    graph, closed = vertex_graph(entities)
    paths         = deque(np.reshape(closed, (-1,1)))
    vertex_paths  = np.array(nx.cycles.cycle_basis(graph))
    
    for vertex_path in vertex_paths:
        if len(vertex_path) < 2: continue
        entity_path = vertex_to_entity_path(vertex_path,
                                            graph, 
                                            entities, 
                                            vertices)
        paths.append(np.array(entity_path))
    paths = np.array(paths)
    return paths

def arctan2_points(points):
    angle = np.arctan2(*points.T[::-1])
    test  = angle < 0.0
    angle[test] = (np.pi*2) + angle[test]
    return angle

def discretize_path(entities, vertices, path, scale=1.0):
    '''
    Return a (n, dimension) list of vertices. 
    Samples arcs/curves to be line segments
    '''
    path_len  = len(path)
    if path_len == 0:  
        raise NameError('Cannot discretize empty path!')
    if path_len == 1:  
        return np.array(entities[path[0]].discrete(vertices))
    discrete = deque()
    for i, entity_id in enumerate(path):
        last    = (i == (path_len - 1))
        current = entities[entity_id].discrete(vertices, scale=scale)
        slice   = (int(last) * len(current)) + (int(not last) * -1)
        discrete.extend(current[:slice])
    return np.array(discrete)    

class PathSample:
    def __init__(self, points):
        # make sure input array is numpy
        self._points = np.array(points)
        # find the direction of each segment
        self._vectors = np.diff(self._points, axis=0)
        # find the length of each segment
        self._norms = np.linalg.norm(self._vectors, axis=1)
        # unit vectors for each segment
        nonzero = self._norms > tol.zero
        self._unit_vec = self._vectors.copy()
        self._unit_vec[nonzero] /= self._norms[nonzero].reshape((-1,1))
        # total distance in the path
        self.length = self._norms.sum()
        # cumulative sum of section length
        # note that this is sorted
        self._cum_norm  = np.cumsum(self._norms)        

    def sample(self, distances):
        # return the indices in cum_norm that each sample would
        # need to be inserted at to maintain the sorted property
        positions = np.searchsorted(self._cum_norm, distances)
        positions = np.clip(positions, 0, len(self._unit_vec)-1)
        offsets   = np.append(0, self._cum_norm)[positions]
        # the distance past the reference vertex we need to travel
        projection = distances - offsets
        # find out which dirction we need to project
        direction  = self._unit_vec[positions]
        # find out which vertex we're offset from
        origin     = self._points[positions]
        # just the parametric equation for a line
        resampled = origin + (direction*projection.reshape((-1,1)))
        
        return resampled
        

def resample_path(points, count=None, step=None, step_round=True):
    '''
    Given a path along (n,d) points, resample them such that the
    distance traversed along the path is constant in between each 
    of the resampled points. Note that this can produce clipping at 
    corners, as the original vertices are NOT guaranteed to be in the
    new, resampled path. 

    ONLY ONE of count or step can be specified
    Result can be uniformly distributed (np.linspace) by specifying count
    Result can have a specific distance (np.arange) by specifying step


    Arguments
    ----------
    points:   (n,d) sequence of points in space
    count:    number of points to sample to (aka np.linspace)
    step:     distance each step should take along the path (aka np.arange)

    Returns
    ----------
    resampled: (j,d) set of points on the path
    '''

    points = np.array(points)
    # generate samples along the perimeter from kwarg count or step
    if (count is not None) and (step is not None):
        raise ValueError('Only step OR count can be specified')
    if (count is None) and (step is None):
        raise ValueError('Either step or count must be specified')

    sampler = PathSample(points)
    if step is not None and step_round:
        count = int(np.ceil(sampler.length / step))
    if  count is not None:
        samples = np.linspace(0, sampler.length, count)
    elif step is not None:
        samples = np.arange(0, sampler.length, step)
    
    resampled = sampler.sample(samples)
    
    check = np.linalg.norm(points[[0,-1]] - resampled[[0,-1]],axis=1)
    assert check[0] < tol.merge
    if count is not None:
        assert check[1] < tol.merge

    return resampled
