
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
EXIF_TAG_DATE_TIME = "datetimeoriginal"
EXIF_TAG_LAT = "gpslatitude#"
EXIF_TAG_LON = "gpslongitude#"
EXIF_TAG_ALT = "gpsaltitude#"
PHOTO_FILENAME = "filename"
PHOTO_LOCATION_SOURCE = "locationsource"
PHOTO_LAT = "latitude"
PHOTO_LON = "longitude"
PHOTO_ALT = "altitude"
PHOTO_ATTRIBUTION = "attribution"
PHOTO_ID = "id"
PHOTO_DIRNAME = "dirname"
PHOTO_TIMESTAMP = "timestamp"
PHOTO_INTERVAL = "interval"
LOCATION_SOURCES = ['exif', 'gpx', 'manual', 'interpolated']

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
                timestamps.append(point.time.timestamp() if not point.time is None else None)

    output = pd.DataFrame()
    output['latitude'] = lats
    output['longitude'] = lons
    output['elevation'] = elevations
    output['time'] = times
    output['timestamp'] = timestamps
    
    # Mark first and last rows as boundaries
    output['boundary'] = [0] * len(lats)
    output.loc[0, 'boundary'] = 1
    output.loc[output.index[-1], 'boundary'] = 1

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
    tm_sha = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    tm_dirty = subprocess.call('git diff-index --quiet HEAD', shell=True) != 0
    tm_timestamp = subprocess.run(['git', 'show', '-s', '--format=%cd', '--date=format:%Y-%m-%dT%H:%M:%S'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    generated_at = datetime.now().isoformat()
    return {
        "id": "document",
        "name": name,
        "version": "1.0",
        "author": "cesium-travelmap/gpx2czml.py",
        "travelmap-sha": tm_sha,
        "travelmap-dirty": tm_dirty,
        "travelmap-timestamp": tm_timestamp,
        "generated-at": generated_at,
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
        "start_time": time_bounds.start_time.isoformat() if not time_bounds.start_time is None else None,
        "end_time": time_bounds.end_time.isoformat() if not time_bounds.end_time is None else None,
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

def create_photo_markers(df, czml):
    if df is None: return
    base_path = get_datadir(True) # relative path starting at data/
    for index, row in df.iterrows():

        # Read data from dataframe
        lat = row[PHOTO_LAT]
        lon = row[PHOTO_LON]
        if lat == None or lon == None:
            print(f'Discarding {row[PHOTO_DIRNAME]}/{row[PHOTO_FILENAME]}')
            continue;
        location_source = LOCATION_SOURCES[row[PHOTO_LOCATION_SOURCE]]
        title = f'{row[PHOTO_ATTRIBUTION]}, {row[EXIF_TAG_DATE_TIME]} (location {location_source})'

        # Append the marker
        czml.append({
            "id": row[PHOTO_ID],
            "name": title,
            "position": {
                "cartographicDegrees": [lon, lat, 2] # reset height to prevent floating markers
            },
            "point": {
                "color": {
                    "rgba": [200, 50, 0, 100] if row[PHOTO_LOCATION_SOURCE] == 3 else [0, 50, 200, 100]
                },
                "outlineColor": {
                    "rgba": [200, 200, 200, 255]
                },
                "outlineWidth": 2,
                "pixelSize": 20,
                "heightReference": "CLAMP_TO_GROUND"
            },
            "properties": {
                "src": f'{base_path}/photos/{row[PHOTO_DIRNAME]}/{row[PHOTO_FILENAME]}',
                "time": f'{row[EXIF_TAG_DATE_TIME].isoformat()}'
            }
        })

def get_photo_coordinates(photo_df, index, track, config, global_config):
    photo_row = photo_df.iloc[index]

    # 1) See if there is a manual entry for this photo
    coords = config.get('manual_coords', photo_row[PHOTO_FILENAME], fallback=None)
    if not coords is None:
        return list(map(float, coords.split(','))), 2

    # 2) Read coordinates from EXIF data
    ignore_duplicate_exif_coords = config.getboolean('global', 'ignore_duplicate_exif_coords', fallback=False)
    ignore_exif = config.get('global', 'ignore_exif', fallback='').split(',')
    lat = photo_row[EXIF_TAG_LAT]
    lon = photo_row[EXIF_TAG_LON]
    alt = photo_row[EXIF_TAG_ALT]
    if lat != '-' and lon != '-' and alt != '-':
        # Check if the coordinates are accurate, which will not be the case
        # if multiple photos are present with exactly the same coordinates.
        # In that case, we ignore the EXIF and go on below
        ignore_because_duplicate = ignore_duplicate_exif_coords and \
                photo_df[photo_df[EXIF_TAG_LAT] == lat].shape[0] > 1 and \
                photo_df[photo_df[EXIF_TAG_LON] == lon].shape[0] > 1
        ignore_because_specified = photo_row[PHOTO_FILENAME] in ignore_exif
        if not ignore_because_duplicate and not ignore_because_specified:
            return [float(lon), float(lat), float(alt)], 0
        print(f"Ignoring EXIF coordinates for {photo_row[PHOTO_FILENAME]}")

    # 3) No GPS data found; use photo time and GPS track to determine position
    if track is None: return None, None
    tt = photo_row[EXIF_TAG_DATE_TIME].timestamp()

    # Check if time is inside any of the ignore_gpx_intervals
    intervals = dict(global_config.items('ignore_gpx_intervals'))
    for name, value in intervals.items():
        interval = value.split(',')
        d0 = datetime.fromisoformat(interval[0]).timestamp()
        d1 = datetime.fromisoformat(interval[1]).timestamp()
        if tt > d0 and tt < d1 and photo_row[PHOTO_DIRNAME] in interval[2:]:
            photo_df.loc[index, PHOTO_INTERVAL] = name
            return None, None

    # Continue track interpolation
    i0, i1 = get_closests(track, 'timestamp', tt)
    track_row0 = track.iloc[i0]
    track_row1 = track.iloc[i1]
    if track_row0['boundary'] == 1 and track_row1['boundary'] == 1:
        # It's between tracks
        return None, None
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

def process_photos(dir_name, combined_tracks, global_config):
    photo_dir = os.path.join(get_datadir(), 'photos', dir_name)

    # Read config
    config = configparser.RawConfigParser()
    config_path = os.path.join(photo_dir, 'config.cfg')
    if not os.path.exists(config_path): return
    config.read(config_path)
    delta_hours = float(config.get('global', 'delta.hours', fallback=0))
    delta_minutes = float(config.get('global', 'delta.minutes', fallback=0))

    # Clean if required
    csv_path = os.path.join(photo_dir, 'photos.csv')
    do_clean = sys.argv[2] == 'clean' if len(sys.argv) > 2 else False
    if do_clean:
        os.remove(csv_path)

    # Execute exiftool if photos.csv does not exist
    if not os.path.exists(csv_path):
        print("Executing exiftool for", photo_dir)
        exiftool_path = os.environ['EXIFTOOL_DIR']
        wd = os.getcwd()
        os.chdir(exiftool_path)
        exif_call = f'./exiftool -filename -gpslatitude# -gpslongitude# -gpsaltitude# -gpsdatestamp -gpstimestamp -datetimeoriginal -createdate -dateFormat "%Y-%m-%d %H:%M:%S%z" -fileOrder filename -T -csv --ext csv {photo_dir} > {csv_path}'
        subprocess.call(exif_call, shell=True)
        os.chdir(wd)

    # Read and preprocess csv (exiftool output)
    print(f"Processing photos: ${photo_dir}")
    df = pd.read_csv(csv_path)
    df = df.rename(str.lower, axis='columns')

    # Check if date/time are available
    count = df.shape[0]
    df = df[df[EXIF_TAG_DATE_TIME] != '-'] # Discard when date/time is unavailable
    discard_count = count - df.shape[0]
    if discard_count > 0: print(f"Discarded {discard_count} photos with date/time missing")

    # Apply date/time correction & sort
    df[EXIF_TAG_DATE_TIME] = df[EXIF_TAG_DATE_TIME].apply(lambda s: datetime.strptime(s, DATETIME_FORMAT) + timedelta(hours=delta_hours, minutes=delta_minutes))
    df.sort_values(EXIF_TAG_DATE_TIME, inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Some other properties we want to store
    df[PHOTO_TIMESTAMP] = df[EXIF_TAG_DATE_TIME].apply(lambda dt: dt.timestamp())
    df[PHOTO_ATTRIBUTION] = [config.get('global', 'attribution')] * df.shape[0]
    df[PHOTO_DIRNAME] = [dir_name] * df.shape[0] # needed in get_photo_coords

    # Get coordinates from manual/exif/gpx if available
    # (interpolating between photos can only be done later, after all photos have been processed)
    df[PHOTO_ID] = [None] * df.shape[0]
    df[PHOTO_LAT] = [None] * df.shape[0]
    df[PHOTO_LON] = [None] * df.shape[0]
    df[PHOTO_ALT] = [None] * df.shape[0]
    df[PHOTO_LOCATION_SOURCE] = [-1] * df.shape[0]
    df[PHOTO_INTERVAL] = [None] * df.shape[0]
    for index, row in df.iterrows():
        df.loc[index, PHOTO_ID] = f'photo_{dir_name}_{index}'
        coordinates, location_source = get_photo_coordinates(df, index, combined_tracks, config, global_config)
        if not coordinates is None:
            df.loc[index, PHOTO_LAT] = coordinates[1]
            df.loc[index, PHOTO_LON] = coordinates[0]
            df.loc[index, PHOTO_ALT] = coordinates[2]
            df.loc[index, PHOTO_LOCATION_SOURCE] = location_source

    return df

def copy_position(source_row, target_df, target_index):
    target_df.loc[target_index, PHOTO_TIMESTAMP] = source_row['timestamp']
    target_df.loc[target_index, PHOTO_LAT] = source_row['latitude']
    target_df.loc[target_index, PHOTO_LON] = source_row['longitude']
    target_df.loc[target_index, PHOTO_ALT] = source_row['elevation']

def insert_trackpoints(df, trackpoint0, trackpoint1):
    df.loc[-2] = None # we'll sort later
    df.loc[-1] = None
    copy_position(trackpoint0, df, -2)
    copy_position(trackpoint1, df, -1)
    df.sort_values(PHOTO_TIMESTAMP, inplace=True)
    df.reset_index(drop=True, inplace=True)

def interpolate_photo_coordinates(df, global_config, combined_tracks):
    df.sort_values(PHOTO_TIMESTAMP, inplace=True)
    df.reset_index(drop=True, inplace=True)
    photos_with_coords = df[df[PHOTO_LOCATION_SOURCE] > -1]
    for index, row in df.iterrows():
        if row[PHOTO_LAT] is None:
            # Determine interval and photo selection to interpolate in
            filtered_photos = photos_with_coords
            if not combined_tracks is None:
                if not row[PHOTO_INTERVAL] is None:
                    interval = global_config.get('ignore_gpx_intervals', row[PHOTO_INTERVAL], fallback='').split(',')
                    dir_names = interval[2:]
                    filtered_photos = photos_with_coords[photos_with_coords[PHOTO_DIRNAME].isin(dir_names)]
                    # filtered_photos = filtered_photos.copy(deep=True) # to prevent SettingWithCopyError
                    # filtered_photos.reset_index(drop=True, inplace=True)
                    # # Add track points around interval
                    # d0 = datetime.fromisoformat(interval[0]).timestamp()
                    # d1 = datetime.fromisoformat(interval[1]).timestamp()
                    # i0, _ = get_closests(combined_tracks, 'timestamp', d0)
                    # _, i1 = get_closests(combined_tracks, 'timestamp', d1)
                    # insert_trackpoints(filtered_photos, combined_tracks.iloc[i0], combined_tracks.iloc[i1])
                else:
                    # Add closest track points
                    filtered_photos = filtered_photos.copy(deep=True) # to prevent SettingWithCopyError
                    i0, i1 = get_closests(combined_tracks, 'timestamp', row[PHOTO_TIMESTAMP])
                    insert_trackpoints(filtered_photos, combined_tracks.iloc[i0], combined_tracks.iloc[i1])

            # Find reference points for interpolation
            tt = row[PHOTO_TIMESTAMP]
            i0, i1 = get_closests(filtered_photos, PHOTO_TIMESTAMP, tt)
            row0 = filtered_photos.iloc[i0]
            row1 = filtered_photos.iloc[i1]
            t0 = row0[PHOTO_TIMESTAMP]
            t1 = row1[PHOTO_TIMESTAMP]
            fract = (tt - t0) / (t1 - t0)

            # Discard any photos outside time bounds
            if fract < 0 or fract > 1:
                print(f"Could not interpolate {row[PHOTO_DIRNAME]}/{row[PHOTO_FILENAME]} at {row[EXIF_TAG_DATE_TIME]}")
                continue

            # Interpolate
            df.loc[index, PHOTO_LAT] = row0[PHOTO_LAT] + fract * (row1[PHOTO_LAT] - row0[PHOTO_LAT])
            df.loc[index, PHOTO_LON] = row0[PHOTO_LON] + fract * (row1[PHOTO_LON] - row0[PHOTO_LON])
            df.loc[index, PHOTO_ALT] = row0[PHOTO_ALT] + fract * (row1[PHOTO_ALT] - row0[PHOTO_ALT])
            df.loc[index, PHOTO_LOCATION_SOURCE] = 3

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

    # Load global config
    global_config = configparser.RawConfigParser()
    config_path = os.path.join(data_dir, 'config.cfg')
    if os.path.exists(config_path):
        global_config.read(config_path)

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
        photo_dfs.append(process_photos(dir_name, combined_tracks, global_config))
    all_photos = pd.concat(photo_dfs) if len(photo_dfs) > 0 else None
    # Now that all photos have been processed, interpolate any photos that still miss a location
    interpolate_photo_coordinates(all_photos, global_config, combined_tracks)
    create_photo_markers(all_photos, czml)

    # Tracking entity
    # ! Do this after processing the photos, since we'll smoothen the tracks in-place
    if len(tracks) > 0:
        tracking_entity = create_tracking_entity(f'track_entity', tracks)
        czml.append(tracking_entity)

    # Define document packet (now that we know the global start/stop times)
    starttime = min(all_photos[EXIF_TAG_DATE_TIME]) if combined_tracks is None else min(combined_tracks['time'])
    stoptime = max(all_photos[EXIF_TAG_DATE_TIME]) if combined_tracks is None else max(combined_tracks['time'])
    document_packet = create_document_packet("cesium-travelmap", starttime, stoptime)
    czml.insert(0, document_packet) # put at start

    # Write output
    path = os.path.join(data_dir, 'combined.czml')
    print(f"Writing output to {path}")
    with open(path, 'w') as outfile:
        json.dump(czml, outfile)

    # Write config
    if not combined_tracks is None: # TODO: handle photo-only datasets
        out_config = create_config(combined_tracks)
        path = os.path.join(data_dir, 'config.json')
        print(f"Writing config to {path}")
        with open(path, 'w') as outfile:
            json.dump(out_config, outfile)
