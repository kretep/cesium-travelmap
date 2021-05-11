
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

def gpx_to_dataframe(gpx):
    lats = []
    lons = []
    elevations = []
    timestamps = []

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                lats.append(point.latitude)
                lons.append(point.longitude)
                elevations.append(point.elevation)
                timestamps.append(point.time)

    output = pd.DataFrame()
    output['latitude'] = lats
    output['longitude'] = lons
    output['elevation'] = elevations
    output['starttime'] = timestamps
    output['stoptime'] = output['starttime'].shift(-1).fillna(method='ffill')
    output['duration'] = (output['stoptime'] - output['starttime']) / np.timedelta64(1, 's') ## duration to seconds
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
    opacity = 100
    return [
        [0, 173, 253, opacity],
        [173, 0, 253, opacity],
        [0, 253, 173, opacity],
        [173, 253, 0, opacity],
        [253, 173, 0, opacity],
        [253, 0, 173, opacity],
        [173, 253, 253, opacity],
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
    description = f'<div>{attribution}, {row["DateTimeOriginal"]}<br /><img src="data/photos/{dir_name}/{row["FileName"]}" width="100%" height="100%" style="float:left; margin: 0 1em 1em 0;" /></div><p>testing</p>'
    return {
        "id": id,
        "name": f'{id} {"estimated location" if isEstimated else ""}',
        "description": description,
        "position": {
            "cartographicDegrees": coordinates
        },
        "point": {
            "color": {
                "rgba": [50, 200, 50, 50]
            },
            "outlineColor": {
                "rgba": [200, 200, 0, 255]
            },
            "outlineWidth": 2,
            "pixelSize": 20,
            "heightReference": "NONE"
        }
    }

def get_photo_coordinates(photo_row, track):
    lat = photo_row['GPSLatitude#']
    lon = photo_row['GPSLongitude#']
    alt = photo_row['GPSAltitude#']
    if lat != '-' and lon != '-' and alt != '-':
        return [float(lon), float(lat), float(alt)], 0
    val = photo_row['DateTimeOriginal']
    index = get_closests(track, 'starttime', val)
    track_row = track.iloc[index]
    lat = track_row['latitude']
    lon = track_row['longitude']
    alt = track_row['elevation']
    return [float(lon), float(lat), float(alt)], 1

def get_closests(df, col, val):
    index = bisect_left(df[col].tolist(), val)
    if index >= df.shape[0]:
        index = df.shape[0] - 1
    return index
    # lower_idx = bisect_left(df[col].values, val)
    # higher_idx = bisect_right(df[col].values, val)
    # if higher_idx == lower_idx:      #val is not in the list
    #     return lower_idx - 1, lower_idx
    # else:                            #val is in the list
    #     return lower_idx

def process_photos(dir_name, czml, combined_tracks):
    photo_dir = os.path.join(get_datadir(), 'photos', dir_name)

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
    #df['CreateDate'] = df['CreateDate'].apply(lambda s: datetime.strptime(s, DATETIME_FORMAT) + timedelta(hours=delta_hours, minutes=delta_minutes))
    df['DateTimeOriginal'] = df['DateTimeOriginal'].apply(lambda s: datetime.strptime(s, DATETIME_FORMAT) + timedelta(hours=delta_hours, minutes=delta_minutes))
    df.sort_values('DateTimeOriginal', inplace=True)
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

    photo_dir = os.path.join(data_dir, 'photos')
    photo_dirs = [name for name in os.listdir(photo_dir) if os.path.isdir(os.path.join(photo_dir, name))]
    photo_dirs.sort()
    for dir_name in photo_dirs:
        process_photos(dir_name, czml, combined_tracks)

    # Write output
    with open(os.path.join(data_dir, 'combined.czml'), 'w') as outfile:
        json.dump(czml, outfile)
