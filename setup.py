#!/usr/bin/env python

from distutils.core import setup

exec(open('trimesh/version.py').read())

setup(name='trimesh',
      version=__version__,
      description='Load, process, and view triangular meshes.',
      author='Mike Dawson-Haggerty',
      author_email='mik3dh@gmail.com',
      url='github.com/mikedh/trimesh',
      packages         = ['trimesh',
                          'trimesh.io',
                          'trimesh.ray',
                          'trimesh.path',
                          'trimesh.scene'],
      install_requires = ['numpy', 
                          'scipy', 
                          'networkx', 
                          'pyglet'],
      extras_require    = {'path' : ['svg.path', 
                                     'Shapely', 
                                     'rtree']}
     )
