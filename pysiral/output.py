# -*- coding: utf-8 -*-


from pysiral.path import filename_from_path
from pysiral.errorhandler import ErrorStatus
from pysiral.config import options_from_dictionary, get_parameter_attributes
from pysiral.path import validate_directory


from netCDF4 import Dataset, date2num
from datetime import datetime
from dateutil import parser as dtparser
import numpy as np
import parse
import os


class NCDateNumDef(object):
    """
    Holds definition for datetime conversion to numbers and vice versa
    for netCDF operations
    """

    def __init__(self):
        self.units = "seconds since 1970-01-01"
        self.calendar = "standard"


class NCDataFile(object):

    def __init__(self):
        self.filename = None
        self.time_def = NCDateNumDef()
        self.zlib = True
        self._rootgrp = None
        self._options = None
        self.verbose = False

    def set_options(self, **opt_dict):
        self._options = options_from_dictionary(**opt_dict)

    def _create_root_group(self, attdict):
        """
        Create the root group and add l1b metadata as global attributes
        """
        self._convert_datetime_attributes(attdict)
        self._convert_bool_attributes(attdict)
        self._convert_nonetype_attributes(attdict)
        self._set_global_attributes(attdict)

    def _convert_datetime_attributes(self, attdict):
        """
        Replace l1b info parameters of type datetime.datetime by a double
        representation to match requirements for netCDF attribute data type
        rules
        """
        for key in attdict.keys():
            content = attdict[key]
            if type(content) is datetime:
                attdict[key] = date2num(
                    content, self.time_def.units, self.time_def.calendar)

    def _convert_bool_attributes(self, attdict):
        """
        Replace l1b info parameters of type bool ['b1'] by a integer
        representation to match requirements for netCDF attribute data type
        rules
        """
        for key in attdict.keys():
            content = attdict[key]
            if type(content) is bool:
                attdict[key] = int(content)

    def _convert_nonetype_attributes(self, attdict):
        """
        Replace l1b info parameters of type bool ['b1'] by a integer
        representation to match requirements for netCDF attribute data type
        rules
        """
        for key in attdict.keys():
            content = attdict[key]
            if content is None:
                attdict[key] = ""

    def _set_global_attributes(self, attdict):
        """ Save l1b.info dictionary as global attributes """
        for key in attdict.keys():
            self._rootgrp.setncattr(key, attdict[key])

    def _open_file(self):
        self._rootgrp = Dataset(self.path, "w")

    def _write_to_file(self):
        self._rootgrp.close()


class L1bDataNC(NCDataFile):
    """
    Class to export a L1bdata object into a netcdf file
    """

    def __init__(self):
        super(L1bDataNC, self).__init__()

        self.datagroups = ["waveform", "surface_type", "time_orbit",
                           "classifier", "correction"]
        self.output_folder = None
        self.l1b = None
        self.parameter_attributes = get_parameter_attributes("l1b")

    def export(self):
        self._validate()
        self._open_file()
        # Save the l1b info data group as global attributes
        attdict = self.l1b.info.attdict
        self._create_root_group(attdict)
        self._populate_data_groups()
        self._write_to_file()

    def _validate(self):
        if self.filename is None:
            self._create_filename()
        self.path = os.path.join(self.output_folder, self.filename)

    def _create_filename(self):
        self.filename = file_basename(self.l1b.filename)+".nc"

    def _populate_data_groups(self):
        for datagroup in self.datagroups:
            if self.verbose:
                print datagroup.upper()
            # Create the datagroup
            dgroup = self._rootgrp.createGroup(datagroup)
            content = getattr(self.l1b, datagroup)
            # Create the dimensions
            # (must be available as OrderedDict in Datagroup Container
            dims = content.dimdict.keys()
            for key in dims:
                dgroup.createDimension(key, content.dimdict[key])
            # Now add variables for each parameter in datagroup
            for parameter in content.parameter_list:
                data = getattr(content, parameter)
                # Convert datetime objects to number
                if type(data[0]) is datetime:
                    data = date2num(data, self.time_def.units,
                                    self.time_def.calendar)
                # Convert bool objects to integer
                if data.dtype.str == "|b1":
                    data = np.int8(data)
                dimensions = tuple(dims[0:len(data.shape)])
                if self.verbose:
                    print " "+parameter, dimensions, data.dtype.str, data.shape
                var = dgroup.createVariable(
                    parameter, data.dtype.str, dimensions, zlib=self.zlib)
                var[:] = data
                # Add Parameter Attributes
                attribute_dict = self._get_variable_attr_dict(parameter)
                for key in attribute_dict.keys():
                    setattr(var, key, attribute_dict[key])
        print "Warning: Missing parameter attributes for "+"; ".join(
            self._missing_parameters)

    def _get_variable_attr_dict(self, parameter):
        """ Retrieve the parameter attributes """
        self._missing_parameters = []
        default_attrs = {
            "long_name": parameter,
            "standard_name": parameter,
            "scale_factor": 1.0,
            "add_offset": 0.0}
        if not self.parameter_attributes.has_key(parameter):
            self._missing_parameters.append(parameter)
            return default_attrs
        else:
            return dict(self.parameter_attributes[parameter])


class L2iDataNC(NCDataFile):
    """
    Class to export a l2data object into a netcdf file
    """

    def __init__(self):
        super(L2iDataNC, self).__init__()
        self.parameter = []
        self.export_path = None
        self.l2 = None

    def set_export_path(self, path):
        self.export_path = path

    def write_to_file(self, l2):
        self._validate(l2)
        self._open_file()
        self._create_root_group(l2.info.attdict)
        self._populate_data_groups(l2)
        self._write_to_file()

    def _validate(self, l2):
        # Validate the export directory
        path = self.export_path
        for subfolder_tag in self._options.subfolders:
            subfolder = getattr(l2.info, subfolder_tag)
            path = os.path.join(path, subfolder)
        validate_directory(path)
        # get full output filename
        filename = l2i_filenaming(l2)
        self.path = os.path.join(path, filename)

    def _populate_data_groups(self, l2):
        dimdict = l2.dimdict
        dims = dimdict.keys()
        for key in dims:
                self._rootgrp.createDimension(key, dimdict[key])
        for parameter_name in self._options.parameter:
            data = l2.get_parameter_by_name(parameter_name)
            # Convert datetime objects to number
            if type(data[0]) is datetime:
                data = date2num(data, self.time_def.units,
                                self.time_def.calendar)
            # Convert bool objects to integer
            if data.dtype.str == "|b1":
                data = np.int8(data)
            dimensions = tuple(dims[0:len(data.shape)])
            var = self._rootgrp.createVariable(
                    parameter_name, data.dtype.str, dimensions, zlib=self.zlib)
            var[:] = data


class L3SDataNC(NCDataFile):
    """
    Class to export a l2data object into a netcdf file
    """

    def __init__(self):
        super(L3SDataNC, self).__init__()
        self.parameter = []
        self.export_path = None
        self.metadata = None
        self.l2 = None

    def set_export_folder(self, path):
        self.export_path = path

    def set_metadata(self, metadata):
        self.metadata = metadata

    def export(self, l3):
        self._validate()
        self._open_file()
        self._create_root_group(self.metadata.attdict)
        self._populate_data_groups(l3)
        self._write_to_file()

    def _validate(self):
        # Validate the export directory
        path = self.export_path
        validate_directory(path)
        # get full output filename
        filename = l3s_filenaming(self.metadata)
        self.path = os.path.join(path, filename)

    def _populate_data_groups(self, l3):
        dimdict = l3.dimdict
        dims = dimdict.keys()
        for key in dims:
                self._rootgrp.createDimension(key, dimdict[key])
        for parameter_name in l3.parameter_list:
            data = l3.get_parameter_by_name(parameter_name)
            dimensions = tuple(dims[0:len(data.shape)])
            var = self._rootgrp.createVariable(
                    parameter_name, data.dtype.str, dimensions, zlib=self.zlib)
            var[:] = data


class PysiralOutputFileNaming(object):

    def __init__(self):
        self.error = ErrorStatus()
        self.data_level = None
        self.version = None
        self.hemisphere = None
        self.mission_id = None
        self.orbit = None
        self.start = None
        self.stop = None
        self.resolution_tag = None
        self.grid_tag = None

        self._registered_parsers = {
            "l1bdata": "l1bdata_{version}_{hemisphere}_{mission_id}_{orbit:06d}_{start}_{stop}.nc"}

    def parse_filename(self, fn):
        filename = filename_from_path(fn)
        for data_level in self._registered_parsers.keys():
            parser = parse.compile(self._registered_parsers[data_level])
            match = parser.parse(filename)
            if match:
                self.data_level = data_level
                for parameter in match.named.keys():
                    value = match[parameter]
                    if parameter in ["start", "stop"]:
                        value = dtparser.parse(value)
                    setattr(self, parameter, value)
                return

def l1bnc_filenaming(l1b, config, version):
    """
    Returns the standard export folder and filename of a level-1b netCDF
    data file

    Export Folder
    -------------

    Based on the ``l1bdata`` file for the specific mission in
    ``local_machine_def.yaml`` in the pysiral main directory
    with sub-folders for hemisphere, year, month

    Filename
    --------

    Default l1bdata filename in pysiral::

        l1bdat_v$VERS_$REG_$MISSION_$ORBIT_$YYYYMMDDHHMISS_$YYYYMMDDHHMISS.nc

    :$VERS: l1bdata version [00 (beta)]
    :$REG: region [north | south]
    :$MISSION: mission short name [cryosat2 | envisat | ers1 | ...]
    :$ORBIT: orbit/cylce number [ 00026000 ]
    :$YYYYMMDDHHMISS: start and end time

    """
    # export folder: $mission_l1bdata_folder/YYYY/MM (start time)

    # Get a proper filename friendly representation of the pysiral version
    pysiral_version = config.PYSIRAL_VERSION
    pysiral_version = pysiral_version.replace(".", "")
    pysiral_version = pysiral_version.replace("-", "")

    year = l1b.info.start_time.year
    month = l1b.info.start_time.month
    hemisphere = l1b.info.hemisphere
    export_folder = get_l1bdata_export_folder(config, l1b.mission, version,
                                              hemisphere, year, month)

    # construct filename from
    export_filename = "l1bdata_v{version}_{region}_{mission}_" + \
                      "{orbit:06g}_{startdt:%Y%m%dT%H%M%S}_" + \
                      "{stopdt:%Y%m%dT%H%M%S}.nc"
    export_filename = export_filename.format(
        version=pysiral_version, region=hemisphere, mission=l1b.info.mission,
        orbit=l1b.info.orbit, startdt=l1b.info.start_time,
        stopdt=l1b.info.stop_time)
    return export_folder, export_filename


def get_l1bdata_export_folder(config, mission, version,
                              hemisphere, year, month):
    local_repository = config.local_machine.l1b_repository
    export_folder = local_repository[mission][version].l1bdata
    yyyy = "%04g" % year
    mm = "%02g" % month
    export_folder = os.path.join(export_folder, hemisphere, yyyy, mm)
    return export_folder

def l2i_filenaming(l2):
    export_filename = "l2i_v{version:02g}_{region}_{mission}_" + \
                      "{orbit:06g}_{startdt:%Y%m%dT%H%M%S}_" + \
                      "{stopdt:%Y%m%dT%H%M%S}.nc"
    export_filename = export_filename.format(
        version=0, region=l2.hemisphere, mission=l2.info.mission,
        orbit=l2.info.orbit, startdt=l2.info.start_time,
        stopdt=l2.info.stop_time)
    return export_filename


def l3s_filenaming(l3):
    export_filename = "l3s_v{version:02g}_{mission}_" + \
                      "{grid_tag}_{resolution_tag}_" + \
                      "{start_period}_{stop_period}.nc"
    export_filename = export_filename.format(
        version=0, mission=l3.mission, grid_tag=l3.grid_tag,
        resolution_tag=l3.resolution_tag, start_period=l3.start_period,
        stop_period=l3.stop_period)
    return export_filename


def get_output_class(name):
    return globals()[name]()
