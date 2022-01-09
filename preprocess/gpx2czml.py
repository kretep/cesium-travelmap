
import math
import pandas as pd
import numpy as np
import gpxpy
from tcx2gpx import TCX2GPX
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
    times = []
    timestamps = []

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                lats.append(point.latitude)
                lons.append(point.longitude)
                elevations.append(point.elevation)
                times.append(point.time)
                timestamps.append(point.time.timestamp())

    output = pd.DataFrame()
    output['latitude'] = lats
    output['longitude'] = lons
    output['elevation'] = elevations
    output['time'] = times
    output['timestamp'] = timestamps
    output.sort_values('time', inplace=True)
    output.reset_index(drop=True, inplace=True)
    return output

# Returns a coordinate list used for positioning a CZML entity
def create_coordinate_list(df_input, includeTimestep=True):
    results = []
    start_timestamp = min(df_input['timestamp'])
    for i in df_input.index:
        if includeTimestep:
            timestamp = df_input.timestamp.iloc[i]
            results.append(timestamp - start_timestamp)
        results.append(df_input.longitude.iloc[i])
        results.append(df_input.latitude.iloc[i])
        results.append(df_input.elevation.iloc[i])
    return results

# Each track will represented by a polyline
def create_polyline(path_id, df_input, metadata, color):
    coordinate_list = create_coordinate_list(df_input, includeTimestep=False)
    return {
        "id": path_id,
        "name": str(min(df_input['time'])),
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

# The cursor is the entity that will be shown on the polyline,
# so it will be at the exact location of the track.
# Each track will have its own cursor. (see create_tracking_entity)
def create_tracking_cursor(entity_id, df_input):
    point_starttime = min(df_input['time']).isoformat()
    point_stoptime = max(df_input['time']).isoformat()
    point_availability = point_starttime + "/" + point_stoptime
    coordinate_list = create_coordinate_list(df_input, includeTimestep=True)
    return {
        "id": entity_id,
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
                "rgba": [255, 0, 0, 200]
            },
            "outlineWidth": 5,
            "pixelSize": 14,
            "heightReference": "CLAMP_TO_GROUND"
        },
    }

# The tracking entity is the entity that will be tracked in the animation,
# it's based on a heavily smoothed version of the tracks, so the camera movement is smooth.
# There will be one entity for the whole dataset, based on the combined tracks.
# (also see create_tracking_cursor)
def create_tracking_entity(entity_id, track_dfs):
    # Create a smooth path for the camera to track
    SMOOTHING_WINDOW_SIZE = 100
    smoothed_tracks = []
    for track in track_dfs:
        # Apply padding to keep the start and end of the tracks at their current locations
        padding_before = pd.DataFrame([track.iloc[0].copy()] * (int(SMOOTHING_WINDOW_SIZE / 2) + 1))
        padding_after = pd.DataFrame([track.iloc[-1].copy()] * (int(SMOOTHING_WINDOW_SIZE / 2) + 1))
        padded_track = get_combined_tracks([padding_before, track, padding_after])

        # Actual smoothing
        padded_track['longitude'] = padded_track['longitude'].rolling(SMOOTHING_WINDOW_SIZE, 1, True).mean()
        padded_track['latitude'] = padded_track['latitude'].rolling(SMOOTHING_WINDOW_SIZE, 1, True).mean()
        padded_track['elevation'] = padded_track['elevation'].rolling(SMOOTHING_WINDOW_SIZE, 1, True).mean()
        padded_track['timestamp'] = padded_track['timestamp'].rolling(SMOOTHING_WINDOW_SIZE, 1, True).mean()
        padded_track['time'] = padded_track['timestamp'].apply(lambda timestamp: datetime.fromtimestamp(timestamp))
        smoothed_tracks.append(padded_track)

    # Combine all the tracks into one
    combined_tracks = get_combined_tracks(smoothed_tracks)

    # Create and return the entity
    point_starttime = min(combined_tracks['time']).isoformat()
    point_stoptime = max(combined_tracks['time']).isoformat()
    point_availability = point_starttime + "/" + point_stoptime
    coordinate_list = create_coordinate_list(combined_tracks, includeTimestep=True)
    return {
        "id": entity_id,
        "availability": point_availability,
        "position": {
            "epoch": point_starttime,
            "cartographicDegrees": coordinate_list
        },
        "point": {
            "color": {
                "rgba": [255, 255, 255, 0]
            },
            "pixelSize": 0,
            "heightReference": "NONE"
        },
         "viewFrom": {
            "cartesian": [0, -2500, 2000] # this might be reset in the visualizer
        },
    }

def create_document_packet(name, starttime, stoptime):
    starttime = starttime.isoformat()
    stoptime = stoptime.isoformat()
    availability = starttime + "/" + stoptime
    return {
        "id": "document",
        "name": name,
        "version": "1.0",
        "author": "cesium-travelmap/gpx2czml.py",
        "clock": {
            "interval": availability,
            "currentTime": starttime,
            "multiplier": 300
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
    ][index % 7]

# Returns a tuple of dataframe and metadata dictionary
def load_track(path, config):
    print("Loading and processing track", path)
    gpx_file = open(path, 'r')
    gpx = gpxpy.parse(gpx_file)
    gpx_point_count = gpx.get_points_no()

    # Smoothen and resample track
    if gpx_point_count > 1000:
        for i in range(10):
            gpx.smooth(vertical=True, horizontal=True, remove_extremes=True)
        gpx.simplify(max_distance=1)
        print(f"Reduced point count from {gpx_point_count} to {gpx.get_points_no()}")
    else:
        print(f"Point count: {gpx_point_count}")

    # Extract meta data
    minmax = gpx.get_elevation_extremes()
    time_bounds = gpx.get_time_bounds()
    updown_elevation = gpx.get_uphill_downhill()
    metadata = {
        "source": config.get('global', 'attribution', fallback=''),
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
    # Load config
    config = configparser.RawConfigParser()
    config_path = os.path.join(tracks_dir, 'config.cfg')
    config.read(config_path)

    # Convert any unconverted tcx files
    listdir = os.listdir(tracks_dir)
    listdir.sort()
    tcx_files = [os.path.join(tracks_dir, file) for file in listdir if file[-4:] == '.tcx']
    tcx_to_process = [file for file in tcx_files if not os.path.exists(file[:-4] + '.gpx')]
    for tcx_path in tcx_to_process:
        print(f"Converting to gpx: {tcx_path}")
        gps_object = TCX2GPX(tcx_path)
        gps_object.convert()

    # List and load gpx files
    listdir = os.listdir(tracks_dir)
    listdir.sort()
    paths = [os.path.join(tracks_dir, file) for file in listdir if file[-4:] == '.gpx']
    track_tuple = [load_track(path, config) for path in paths]
    return track_tuple

def process_track(data, czml, index):
    df = data[0]
    metadata = data[1]

    # Polyline
    path_object = create_polyline(f'line_{index}', df, metadata, get_color(index))
    czml.append(path_object)

    # Point
    cursor_object = create_tracking_cursor(f'point_{index}', df)
    czml.append(cursor_object)

LOCATION_SOURCES = ['exif', 'gpx', 'manual']

def create_photo_marker(id, row, track, config, dir_name):
    attribution = config.get('global', 'attribution')
    coordinates, location_source = get_photo_coordinates(row, track, config)
    if coordinates is None:
        print(f'Discarding {dir_name}/{row[HEADER_FILENAME]}')
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
    if track is None: return None, None
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
    delta_hours = float(config.get('global', 'delta.hours', fallback=0))
    delta_minutes = float(config.get('global', 'delta.minutes', fallback=0))

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
    
    return df

def get_datadir(relative=False):
    base_dir = 'data' if relative else os.environ['DATA_DIR']
    key_dir = sys.argv[1] if len(sys.argv) > 1 else ''
    return f'{base_dir}/{key_dir}'

def get_combined_tracks(tracks):
    if len(tracks) == 0: return None
    combined_tracks = pd.concat(tracks)
    combined_tracks.sort_values('time', inplace=True)
    combined_tracks.reset_index(drop=True, inplace=True)
    return combined_tracks

def create_config(combined_tracks):
    return {
        "home_rect": {
            "west": min(combined_tracks['longitude'] / 180 * math.pi),
            "south": min(combined_tracks['latitude'] / 180 * math.pi),
            "east": max(combined_tracks['longitude'] / 180 * math.pi),
            "north": max(combined_tracks['latitude'] / 180 * math.pi)
            }
    }

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
    tracks = list(map(lambda el: el[0], track_tuples))
    combined_tracks = get_combined_tracks(tracks)
    #combined_tracks.to_csv(os.path.join(get_datadir(), 'tracks_combined.csv'))

    # Process photos
    photo_dfs = []
    photo_dir = os.path.join(data_dir, 'photos')
    photo_dirs = [name for name in os.listdir(photo_dir) if os.path.isdir(os.path.join(photo_dir, name))]
    photo_dirs.sort()
    for dir_name in photo_dirs:
        photo_dfs.append(process_photos(dir_name, czml, combined_tracks))
    all_photos = pd.concat(photo_dfs)

    # Tracking entity
    # ! Do this after processing the photos, since we'll smoothen the tracks in-place
    if len(tracks) > 0:
        tracking_entity = create_tracking_entity(f'track_entity', tracks)
        czml.append(tracking_entity)

    # Define document packet (now that we know the global start/stop times)
    starttime = min(all_photos[HEADER_DATE_TIME]) if combined_tracks is None else min(combined_tracks['time'])
    stoptime = max(all_photos[HEADER_DATE_TIME]) if combined_tracks is None else max(combined_tracks['time'])
    document_packet = create_document_packet("cesium-travelmap", starttime, stoptime)
    czml.insert(0, document_packet) # put at start

    # Write output
    path = os.path.join(data_dir, 'combined.czml')
    print(f"Writing output to {path}")
    with open(path, 'w') as outfile:
        json.dump(czml, outfile)

    # Write config
    out_config = create_config(combined_tracks)
    path = os.path.join(data_dir, 'config.json')
    print(f"Writing config to {path}")
    with open(path, 'w') as outfile:
        json.dump(out_config, outfile)
