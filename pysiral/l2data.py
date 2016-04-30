# -*- coding: utf-8 -*-
"""
Created on Fri Jul 24 16:30:24 2015

@author: Stefan
"""
from pysiral.iotools import ReadNC

import numpy as np
from geopy.distance import great_circle
from collections import OrderedDict


class Level2Data(object):

    _L2_DATA_ITEMS = ["mss", "ssa", "elev", "afrb", "frb", "range", "sic",
                      "sitype", "snow_depth", "snow_dens", "ice_dens",
                      "sit"]

    _HEMISPHERE_CODES = {"north": "nh", "south": "sh"}

    _PARAMETER_CATALOG = {
        "timestamp": "timestamp",
        "longitude": "longitude",
        "latitude": "latitude",
        "surface_type": "surface_type_flag",
        "elevation": "elev",
        "mean_sea_surface": "mss",
        "sea_surface_anomaly": "ssa",
        "radar_freeboard": "afrb",
        "freeboard": "frb",
        "sea_ice_type": "sitype",
        "snow_depth": "snow_depth",
        "snow_density": "snow_dens",
        "ice_density": "ice_dens",
        "sea_ice_thickness": "sit"}

    def __init__(self, l1b):
        # Copy necessary fields form l1b
        self._n_records = l1b.n_records
        self.info = l1b.info
        self.track = l1b.time_orbit
        # Create Level2 Data Groups
        self._create_l2_data_items()

    def set_surface_type(self, surface_type):
        self.surface_type = surface_type

    def update_retracked_range(self, retracker):
        # Update only for indices (surface type) supplied by retracker class
        # XXX: should get an overhaul
        ii = retracker.indices
        self.range[ii] = retracker.range[ii]
        self.elev[ii] = self.track.altitude[ii] - retracker.range[ii]

    def get_parameter_by_name(self, parameter_name):
        source = self._PARAMETER_CATALOG[parameter_name]
        parameter = getattr(self, source)
        return parameter

    def _create_l2_data_items(self):
        for item in self._L2_DATA_ITEMS:
            setattr(self, item, L2ElevationArray(shape=(self._n_records)))

    @property
    def n_records(self):
        return self._n_records

    @property
    def hemisphere(self):
        return self.info.subset_region_name

    @property
    def hemisphere_code(self):
        return self._HEMISPHERE_CODES[self.hemisphere]

    @property
    def footprint_spacing(self):
        spacing = great_circle(
            (self.track.latitude[1], self.track.longitude[1]),
            (self.track.latitude[0], self.track.longitude[0])).meters
        return spacing

    @property
    def dimdict(self):
        """ Returns dictionary with dimensions"""
        dimdict = OrderedDict([("n_records", self.n_records)])
        return dimdict

    @property
    def timestamp(self):
        return self.track.timestamp

    @property
    def longitude(self):
        return self.track.longitude

    @property
    def latitude(self):
        return self.track.latitude

    @property
    def surface_type_flag(self):
        return self.surface_type.flag


class L2ElevationArray(np.ndarray):
    """
    Recipe from:
    http://docs.scipy.org/doc/numpy/user/basics.subclassing.html
    XXX: not yet full slicing capability! -> __getitem__ trouble
         always use cls[list] and cls.uncertainty[list]
         cls[list].uncertainty will fail
    """

    def __new__(subtype, shape, dtype=float, buffer=None, offset=0,
                strides=None, order=None, info=None):
        obj = np.ndarray.__new__(
            subtype, shape, dtype, buffer, offset, strides, order)*np.nan
        obj.uncertainty = np.zeros(shape=shape, dtype=float)
        obj.bias = np.zeros(shape=shape, dtype=float)
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self.uncertainty = getattr(obj, 'uncertainty', None)
        self.bias = getattr(obj, 'bias', None)

    def __getslice__(self, i, j):
        r = np.ndarray.__getslice__(self, i, j)
        r.uncertainty = r.uncertainty[i:j]
        r.bias = r.bias[i:j]
        return r

    def set_value(self, value):
#        uncertainty = self.uncertainty
#        bias = self.bias
        self[:] = value[:]
#        setattr(self, "uncertainty", uncertainty)
#        setattr(self, "bias", bias)

    def set_uncertainty(self, uncertainty):
        self.uncertainty = uncertainty


class L2iNCFile(object):

    def __init__(self, filename):
        self.filename = filename
        self._n_records = 0
        self._parse()

    def _parse(self):
        content = ReadNC(self.filename)
        for parameter_name in content.parameters:
            setattr(self, parameter_name, getattr(content, parameter_name))
        self._n_records = len(self.longitude)

    def project(self, griddef):
        from pyproj import Proj
        p = Proj(**griddef.projection)
        self.projx, self.projy = p(self.longitude, self.latitude)
        # Convert projection coordinates to grid indices
        extent = griddef.extent
        self.xi = np.floor((self.projx + extent.xsize/2.0)/extent.dx)
        self.yj = np.floor((self.projy + extent.ysize/2.0)/extent.dy)

    @property
    def n_records(self):
        return self._n_records
