"""
Copied from https://gitlab.com/nshephard/tcx2gpx, as the package doesn't seem to expose the TCX2GPX class.
Also fixed date format to support fractional seconds.
---
Class for converting tcx to gpx
"""
import logging
from datetime import datetime
from pathlib import Path
import dateutil.parser

from gpxpy import gpx
from tcxparser import TCXParser

# pylint: disable=logging-format-interpolation
# pylint: disable=logging-fstring-interpolation

LOGGER = logging.getLogger('tcx2gpx')


class TCX2GPX():
    """
    Convert tcx files to gpx.
    """
    def __init__(self, tcx_path: str, outdir: str = None):
        """
        Initialise the class.

        Parameter
        ---------
        tcx_path: str
            Valid path to a TCX file.
        outdir: str
            Output directory, if not specified uses the default.
        """
        self.tcx_path = Path(tcx_path)
        self.outdir = outdir
        self.tcx = None
        self.track_points = None
        self.gpx = gpx.GPX()

    def convert(self):
        """
        Convert tcx to gpx.
        """
        self.read_tcx()
        self.extract_track_points()
        self.create_gpx()
        self.write_gpx()

    def read_tcx(self):
        """
        Read a TCX file.
        """
        try:
            self.tcx = TCXParser(str(self.tcx_path.resolve()))
            LOGGER.info(f'Reading                     : {self.tcx_path}')
        except TypeError as not_pathlib:
            raise TypeError('File path did not resolve.') from not_pathlib

    def extract_track_points(self):
        """
        Extract and combine features from tcx
        """
        self.track_points = zip(self.tcx.position_values(),
                                self.tcx.altitude_points(),
                                self.tcx.time_values())
        LOGGER.info(f'Extracting track points from : {self.tcx_path}')

    def create_gpx(self):
        """
        Create GPX object.
        """
        self.gpx.name = dateutil.parser.parse(
            self.tcx.started_at).strftime('%Y-%m-%d %H:%M:%S')
        self.gpx.description = ''
        gpx_track = gpx.GPXTrack(name=dateutil.parser.parse(
            self.tcx.started_at).strftime('%Y-%m-%d %H:%M:%S'),
                                 description='')
        gpx_track.type = self.tcx.activity_type
        # gpx_track.extensions = '<topografix:color>c0c0c0</topografix:color>'
        self.gpx.tracks.append(gpx_track)
        gpx_segment = gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        for track_point in self.track_points:
            gpx_trackpoint = gpx.GPXTrackPoint(latitude=track_point[0][0],
                                               longitude=track_point[0][1],
                                               elevation=track_point[1],
                                               time=datetime.strptime(
                                                   track_point[2],
                                                   '%Y-%m-%dT%H:%M:%S.%f%z'))
            gpx_segment.points.append(gpx_trackpoint)
        LOGGER.info(f'Creating GPX for             : {self.tcx_path}')

    def write_gpx(self):
        """
        Write GPX object to file.
        """
        out = Path(str(self.tcx_path.resolve()).replace('.tcx', '.gpx'))
        with out.open('w', encoding='utf8') as output:
            output.write(self.gpx.to_xml())
        LOGGER.info(f'GPX written to               : {out}')
