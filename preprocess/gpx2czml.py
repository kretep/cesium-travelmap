
import pandas as pd
import numpy as np
import gpxpy
import json
import os
import sys
import subprocess
import dotenv
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
import configparser

# Adapted from Will Geary, "Visualizing a Bike Ride in 3D", https://willgeary.github.io/GPXto3D/

## See a primer on reading GPX data in python here: http://andykee.com/visualizing-strava-tracks-with-python.html

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S%z"
HEADER_DATE_TIME = "datetimeoriginal"
HEADER_LAT = "gpslatitude#"
HEADER_LON = "gpslongitude#"
HEADER_ALT = "gpsaltitude#"
HEADER_FILENAME = "filename"

def gpx_to_dataframe(gpx):
    lats = []
    lons = []
    elevations = []
    starttimes = []
    timestamps = []

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                lats.append(point.latitude)
                lons.append(point.longitude)
                elevations.append(point.elevation)
                starttimes.append(point.time)
                timestamps.append(point.time.timestamp())

    output = pd.DataFrame()
    output['latitude'] = lats
    output['longitude'] = lons
    output['elevation'] = elevations
    output['starttime'] = starttimes
    output['stoptime'] = output['starttime'].shift(-1).fillna(method='ffill')
    output['duration'] = (output['stoptime'] - output['starttime']) / np.timedelta64(1, 's') ## duration to seconds
    output['timestamp'] = timestamps
    return output

def create_coordinate_list(df_input, includeTimestep=True):
    results = []
    timestep = 0
    for i in df_input.index:
        if includeTimestep: results.append(timestep)
        results.append(df_input.longitude.iloc[i])
        results.append(df_input.latitude.iloc[i])
        results.append(df_input.elevation.iloc[i])
        duration = df_input.duration.iloc[(i)]
        timestep += duration
    return results

def format_datetime(datetime):
    return str(datetime).replace(" ", "T").replace(".000", "Z")

def create_polyline(path_id, df_input, metadata, color):
    coordinate_list = create_coordinate_list(df_input, includeTimestep=False)
    return {
        "id": path_id,
        "polyline": {
            "positions": {
                "cartographicDegrees": coordinate_list
            },
            "material": {
                "polylineOutline": {
                    "color": {
                        "rgba": color
                    },
                    "outlineWidth": 2,
                    "outlineColor": {
                        "rgba": [0, 0, 0, 160]
                    },
                }
            },
            "width": 6,
            "clampToGround": True,
        },
        "properties": metadata
    }

def create_point(point_id, df_input, color):
    point_starttime = format_datetime(min(df_input['starttime']))
    point_stoptime = format_datetime(max(df_input['stoptime']))
    point_availability = point_starttime + "/" + point_stoptime
    coordinate_list = create_coordinate_list(df_input, includeTimestep=True)
    return {
        "id": point_id,
        "availability": point_availability,
        "position": {
            "epoch": point_starttime,
            "cartographicDegrees": coordinate_list
        },
        "point": {
            "color": {
                "rgba": [255, 255, 255, 255]
            },
            "outlineColor": {
                "rgba": color
            },
            "outlineWidth": 6,
            "pixelSize": 8,
            "heightReference": "CLAMP_TO_GROUND"
        }   
    }

def create_document_packet(name, starttime, stoptime):
    starttime = format_datetime(starttime)
    stoptime = format_datetime(stoptime)
    availability = starttime + "/" + stoptime
    return {
        "id": "document",
        "name": name,
        "version": "1.0",
        "author": "cesium-travelmap/gpx2czml.py",
        "clock": {
            "interval": availability,
            "currentTime": starttime,
            "multiplier": 1000
        }
    }

def get_color(index):
    opacity = 150
    return [
        [120, 190, 255, opacity],
        [190, 120, 255, opacity],
        [120, 255, 190, opacity],
        [190, 255, 120, opacity],
        [255, 120, 190, opacity],
        [255, 190, 120, opacity],
        [190, 255, 255, opacity],
    ][index]

# Returns a tuple of dataframe and metadata dictionary
def load_track(path):
    print("Loading and processing track", path)
    gpx_file = open(path, 'r')
    gpx = gpxpy.parse(gpx_file)

    # Smoothen and resample track
    for i in range(10):
        gpx.smooth(vertical=True, horizontal=True, remove_extremes=True)
    gpx.simplify(max_distance=1)

    # Extract meta data
    minmax = gpx.get_elevation_extremes()
    time_bounds = gpx.get_time_bounds()
    updown_elevation = gpx.get_uphill_downhill()
    metadata = {
        "start_time": time_bounds.start_time.isoformat(),
        "end_time": time_bounds.end_time.isoformat(),
        "duration": gpx.get_duration(),
        "length_2d": gpx.length_2d(),
        "ascent": updown_elevation.uphill,
        "descent": updown_elevation.downhill,
        "min_elevation": minmax.minimum,
        "max_elevation": minmax.maximum
    }

    return gpx_to_dataframe(gpx), metadata

def load_tracks(tracks_dir):
    listdir = os.listdir(tracks_dir)
    listdir.sort()
    paths = [os.path.join(tracks_dir, file) for file in listdir if file[-4:] == '.gpx']
    track_tuple = [load_track(path) for path in paths]
    return track_tuple

def process_track(data, czml, index):
    df = data[0]
    metadata = data[1]

    # Polyline
    path_object = create_polyline(f'line_{index}', df, metadata, get_color(index))
    czml.append(path_object)

    # Point
    point_object = create_point(f'point_{index}', df, get_color(6))
    czml.append(point_object)

LOCATION_SOURCES = ['exif', 'gpx', 'manual']

def create_photo_marker(id, row, track, config, dir_name):
    attribution = config.get('global', 'attribution')
    coordinates, location_source = get_photo_coordinates(row, track, config)
    if coordinates is None:
        print("Discarding ", f'{dir_name}/{row[HEADER_FILENAME]}')
        return None
    title = f'{attribution}, {row[HEADER_DATE_TIME]} (location {LOCATION_SOURCES[location_source]})';
    base_path = get_datadir(True) # relative path starting at data/
    return {
        "id": id,
        "name": title,
        "position": {
            "cartographicDegrees": [coordinates[0], coordinates[1], 2] # reset height to prevent floating markers
        },
        "point": {
            "color": {
                "rgba": [0, 50, 200, 100]
            },
            "outlineColor": {
                "rgba": [200, 200, 200, 255]
            },
            "outlineWidth": 2,
            "pixelSize": 20,
            "heightReference": "CLAMP_TO_GROUND"
        },
        "properties": {
            "src": f'{base_path}/photos/{dir_name}/{row[HEADER_FILENAME]}',
            "time": f'{row[HEADER_DATE_TIME].isoformat()}'
        }
    }

def get_photo_coordinates(photo_row, track, config):
    # 1) Read coordinates from EXIF data
    lat = photo_row[HEADER_LAT]
    lon = photo_row[HEADER_LON]
    alt = photo_row[HEADER_ALT]
    if lat != '-' and lon != '-' and alt != '-':
        return [float(lon), float(lat), float(alt)], 0

    # 2) See if there is a manual entry for this photo
    coords = config.get('manual_coords', photo_row[HEADER_FILENAME], fallback=None)
    if not coords is None:
        return list(map(float, coords.split(','))), 2

    # 3) No GPS data found; use photo time and GPS track to determine position
    tt = photo_row[HEADER_DATE_TIME].timestamp()
    i0, i1 = get_closests(track, 'timestamp', tt)
    track_row0 = track.iloc[i0]
    track_row1 = track.iloc[i1]
    t0 = track_row0['timestamp']
    t1 = track_row1['timestamp']
    fract = (tt - t0) / (t1 - t0)

    # Discard any photos outside track time bounds
    if fract < 0 or fract > 1:
        return None, None

    # Interpolate
    lat = track_row0['latitude'] + fract * (track_row1['latitude'] - track_row0['latitude'])
    lon = track_row0['longitude'] + fract * (track_row1['longitude'] - track_row0['longitude'])
    alt = track_row0['elevation'] + fract * (track_row1['elevation'] - track_row0['elevation'])
    return [float(lon), float(lat), float(alt)], 1

def get_closests(df, col, val):
    # Index before "insertion" point
    i0 = bisect_left(df[col].tolist(), val) - 1
    # Make sure both i0 and i1 will be within bounds
    i0 = min(max(i0, 0), df.shape[0] - 2)
    i1 = i0 + 1
    return i0, i1

def process_photos(dir_name, czml, combined_tracks):
    photo_dir = os.path.join(get_datadir(), 'photos', dir_name)

    # Read config
    config = configparser.RawConfigParser()
    config_path = os.path.join(photo_dir, 'config.cfg')
    if not os.path.exists(config_path): return
    config.read(config_path)
    delta_hours = int(config.get('global', 'delta.hours', fallback=0))
    delta_minutes = int(config.get('global', 'delta.minutes', fallback=0))

    # Execute exiftool if photos.csv does not exist yet
    csv_path = os.path.join(photo_dir, 'photos.csv')
    if not os.path.exists(csv_path):
        print("Executing exiftool for", photo_dir)
        exiftool_path = os.environ['EXIFTOOL_DIR']
        os.chdir(exiftool_path)
        exif_call = f'./exiftool -filename -gpslatitude# -gpslongitude# -gpsaltitude# -gpsdatestamp -gpstimestamp -datetimeoriginal -createdate -dateFormat "%Y-%m-%d %H:%M:%S%z" -T -csv --ext csv {photo_dir} > {csv_path}'
        subprocess.call(exif_call, shell=True)

    # Read and preprocess csv (exiftool output)
    print(f"Processing photos: ${photo_dir}")
    df = pd.read_csv(csv_path)
    df = df.rename(str.lower, axis='columns')

    # Check if date/time are available
    count = df.shape[0]
    df = df[df[HEADER_DATE_TIME] != '-'] # Discard when date/time is unavailable
    discard_count = count - df.shape[0]
    if discard_count > 0: print(f"Discarded {discard_count} photos with date/time missing")

    # Apply date/time correction & sort
    df[HEADER_DATE_TIME] = df[HEADER_DATE_TIME].apply(lambda s: datetime.strptime(s, DATETIME_FORMAT) + timedelta(hours=delta_hours, minutes=delta_minutes))
    df.sort_values(HEADER_DATE_TIME, inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Create markers for photos
    for index, row in df.iterrows():
        marker = create_photo_marker(f'photo_{dir_name}_{index}', row, combined_tracks, config, dir_name)
        if marker is not None:
            czml.append(marker)

def get_datadir(relative=False):
    base_dir = 'data' if relative else os.environ['DATA_DIR']
    key_dir = sys.argv[1] if len(sys.argv) > 1 else ''
    return f'{base_dir}/{key_dir}'

if __name__ == "__main__":
    dotenv.load_dotenv()
    data_dir = get_datadir()
    czml = []
    
    # Process tracks
    print(f"Loading and combining tracks")
    track_tuples = load_tracks(os.path.join(data_dir, 'tracks'))
    for index, track_tuple in enumerate(track_tuples):
        process_track(track_tuple, czml, index)
    
    # Combined tracks
    tracks = map(lambda el: el[0], track_tuples)
    combined_tracks = pd.concat(tracks)
    combined_tracks.sort_values('starttime', inplace=True)
    combined_tracks.reset_index(drop=True, inplace=True)
    combined_tracks.to_csv(os.path.join(get_datadir(), 'tracks_combined.csv'))

    # Define document packet
    starttime = min(combined_tracks['starttime'])
    stoptime = max(combined_tracks['stoptime'])
    document_packet = create_document_packet("testing", starttime, stoptime)
    czml.insert(0, document_packet)

    # Process photos
    photo_dir = os.path.join(data_dir, 'photos')
    photo_dirs = [name for name in os.listdir(photo_dir) if os.path.isdir(os.path.join(photo_dir, name))]
    photo_dirs.sort()
    for dir_name in photo_dirs:
        process_photos(dir_name, czml, combined_tracks)

    # Write output
    path = os.path.join(data_dir, 'combined.czml')
    print(f"Writing output to ${path}")
    with open(path, 'w') as outfile:
        json.dump(czml, outfile)
