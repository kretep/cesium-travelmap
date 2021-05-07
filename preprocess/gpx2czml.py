
import pandas as pd
import numpy as np
import gpxpy
import json
import os
import dotenv

# Adapted from Will Geary, "Visualizing a Bike Ride in 3D", https://willgeary.github.io/GPXto3D/

## See a primer on reading GPX data in python here: http://andykee.com/visualizing-strava-tracks-with-python.html

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
                        "rgba": [255, 255, 255, 200]
                    },
                    "outlineColor": {
                        "rgba": color
                    },
                    "outlineWidth": 5
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

def process_tracks(tracks_dir, czml):
    # Get files
    listdir = os.listdir(tracks_dir)
    listdir.sort()
    paths = [os.path.join(tracks_dir, file) for file in listdir if file[-4:] == '.gpx']

    starttime = None  # global start and end time
    stoptime = None
    
    for index, path in enumerate(paths):
        # Parse file
        gpx_file = open(path, 'r')
        gpx = gpxpy.parse(gpx_file)
        
        # Convert to dataframe
        df = gpx_to_dataframe(gpx)
        #print(df.head())

        # Coordinates used for both path and point
        coordinate_list = create_coordinate_list(df)

        # Path
        path_object = create_path(f'path_{index}', df, coordinate_list, get_color(index))
        czml.append(path_object)

        # Point
        point_object = create_point(f'point_{index}', df, coordinate_list, get_color(6))
        czml.append(point_object)

        # Update global start/end time
        current_min = min(df['starttime'])
        current_max = max(df['stoptime'])
        starttime = current_min if index == 0 else min(starttime, current_min)
        stoptime = current_max if index == 0 else max(stoptime, current_max)

    # Define document packet (now that global start and end time are known)
    document_packet = create_document_packet("testing", starttime, stoptime)
    czml.insert(0, document_packet)

def create_photo_marker(id, row):
    lat = row['GPSLatitude']
    lon = row['GPSLongitude']
    alt = row['GPSAltitude']
    if lat == '-' or lon == '-' or alt == '-':
        return None
    coordinates = [float(lon), float(lat), float(alt)]
    description = f'<div><img src="data/photos/{row["FileName"]}" width="100%" height="100%" style="float:left; margin: 0 1em 1em 0;" /></div><p>testing</p>'
    return {
        "id": id,
        "name": id,
        "description": description,
        #"availability": point_availability,
        "position": {
            #"epoch": point_starttime,
            "cartographicDegrees": coordinates
        },
        "point": {
            "color": {
                "rgba": [255, 255, 255, 100]
            },
            "outlineColor": {
                "rgba": [250, 100, 0, 200]
            },
            "outlineWidth": 10,
            "pixelSize": 20,
            "heightReference": "NONE"
        }
    }

def process_photos(csv_path, czml):
    df = pd.read_csv(csv_path)
    df.sort_values('DateTimeOriginal', inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.to_csv(csv_path + '_sorted.csv')
    for index, row in df.iterrows():
        marker = create_photo_marker(f'photo_{index}', row)
        if marker is not None:
            czml.append(marker)

if __name__ == "__main__":
    dotenv.load_dotenv()
    data_dir = os.environ['DATA_DIR']
    czml = []
    
    # Process
    process_tracks(os.path.join(data_dir, 'tracks'), czml)
    process_photos(os.path.join(data_dir, 'photos.csv'), czml)

    # Write output
    with open(os.path.join(data_dir, 'combined.czml'), 'w') as outfile:
        json.dump(czml, outfile)
