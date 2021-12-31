
import pandas as pd
import numpy as np
import gpxpy
import json
import os
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

def create_coordinate_list(df_input):
    results = []
    timestep = 0
    for i in df_input.index:
        results.append(timestep)
        results.append(df_input.longitude.iloc[i])
        results.append(df_input.latitude.iloc[i])
        results.append(df_input.elevation.iloc[i])
        duration = df_input.duration.iloc[(i)]
        timestep += duration
    return results

def format_datetime(datetime):
    return str(datetime).replace(" ", "T").replace(".000", "Z")

def create_path(path_id, df_input, coordinate_list, color):
    path_starttime = format_datetime(min(df_input['starttime']))
    path_stoptime = format_datetime(max(df_input['stoptime']))
    path_availability = path_starttime + "/" + path_stoptime
    return {
        "id": path_id,
        "availability": path_availability,
        "position": {
            "epoch": path_starttime,
            "cartographicDegrees": coordinate_list
        },
        "path": {
            "material": {
                "polylineOutline": {
                    "color": {
                        "rgba": color
                    },
                    "outlineColor": {
                        "rgba": color
                    },
                    "outlineWidth": 0
                }
            },
            "width": 6,
            # "leadTime": 10,
            # "trailTime": 10000,
            "resolution": 5,
            "heightReference": "RELATIVE_TO_GROUND"
        }
    }

def create_point(point_id, df_input, coordinate_list, color):
    point_starttime = format_datetime(min(df_input['starttime']))
    point_stoptime = format_datetime(max(df_input['stoptime']))
    point_availability = point_starttime + "/" + point_stoptime
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
            "heightReference": "NONE"
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

def load_track(path):
    gpx_file = open(path, 'r')
    gpx = gpxpy.parse(gpx_file)
    return gpx_to_dataframe(gpx)

def load_tracks(tracks_dir):
    listdir = os.listdir(tracks_dir)
    listdir.sort()
    paths = [os.path.join(tracks_dir, file) for file in listdir if file[-4:] == '.gpx']
    gpx_dfs = [load_track(path) for path in paths]
    return gpx_dfs

def process_track(df, czml, index):
    # Coordinates used for both path and point
    coordinate_list = create_coordinate_list(df)

    # Path
    path_object = create_path(f'path_{index}', df, coordinate_list, get_color(index))
    czml.append(path_object)

    # Point
    point_object = create_point(f'point_{index}', df, coordinate_list, get_color(6))
    czml.append(point_object)

def create_photo_marker(id, row, track, config, dir_name):
    attribution = config.get('global', 'attribution')
    coordinates, isEstimated = get_photo_coordinates(row, track)
    if coordinates is None:
        return None
    title = f'{attribution}, {row[HEADER_DATE_TIME]} (location {"estimated" if isEstimated else "GPS"})';
    return {
        "id": id,
        "name": title,
        "position": {
            "cartographicDegrees": coordinates
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
            "heightReference": "NONE"
        },
        "properties": {
            "src": f'data/photos/{dir_name}/{row[HEADER_FILENAME]}',
            "time": f'{row[HEADER_DATE_TIME].isoformat()}'
        }
    }

def get_photo_coordinates(photo_row, track):
    lat = photo_row[HEADER_LAT]
    lon = photo_row[HEADER_LON]
    alt = photo_row[HEADER_ALT]
    if lat != '-' and lon != '-' and alt != '-':
        return [float(lon), float(lat), float(alt)], 0
    
    # No GPS data found; use photo time and GPS track to determine position
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
    print(f"Processing photos: ${photo_dir}")

    # Read config
    config = configparser.RawConfigParser()
    config_path = os.path.join(photo_dir, 'config.cfg')
    if not os.path.exists(config_path): return
    config.read(config_path)
    delta_hours = int(config.get('global', 'delta.hours', fallback=0))
    delta_minutes = int(config.get('global', 'delta.minutes', fallback=0))

    # Read and preprocess csv (exiftool output)
    csv_path = os.path.join(photo_dir, 'photos.csv')
    df = pd.read_csv(csv_path)
    df = df.rename(str.lower, axis='columns')
    #df['CreateDate'] = df['CreateDate'].apply(lambda s: datetime.strptime(s, DATETIME_FORMAT) + timedelta(hours=delta_hours, minutes=delta_minutes))
    df[HEADER_DATE_TIME] = df[HEADER_DATE_TIME].apply(lambda s: datetime.strptime(s, DATETIME_FORMAT) + timedelta(hours=delta_hours, minutes=delta_minutes))
    df.sort_values(HEADER_DATE_TIME, inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.to_csv(csv_path + '_sorted.csv')

    # Create markers for photos
    for index, row in df.iterrows():
        marker = create_photo_marker(f'photo_{dir_name}_{index}', row, combined_tracks, config, dir_name)
        if marker is not None:
            czml.append(marker)

def get_datadir():
    return os.environ['DATA_DIR']

if __name__ == "__main__":
    dotenv.load_dotenv()
    data_dir = get_datadir()
    czml = []
    
    # Process tracks
    print(f"Loading and combining tracks")
    tracks = load_tracks(os.path.join(data_dir, 'tracks'))
    for index, track in enumerate(tracks):
        process_track(track, czml, index)
    
    # Combined tracks
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
