
import pandas as pd
import numpy as np
import gpxpy
import json
import os

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
    return [
        [0, 173, 253, 200],
        [173, 0, 253, 200],
        [0, 253, 173, 200],
        [173, 253, 0, 200],
        [253, 173, 0, 200],
        [253, 0, 173, 200],
        [173, 253, 253, 200],
    ][index]

def process_dir(tracks_dir):
    # Get files
    listdir = os.listdir(tracks_dir)
    listdir.sort()
    paths = [os.path.join(tracks_dir, file) for file in listdir if file[-4:] == '.gpx']

    czml_packets = []
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
        czml_packets.append(path_object)

        # Point
        point_object = create_point(f'point_{index}', df, coordinate_list, get_color(6))
        czml_packets.append(point_object)

        # Update global start/end time
        current_min = min(df['starttime'])
        current_max = max(df['stoptime'])
        starttime = current_min if index == 0 else min(starttime, current_min)
        stoptime = current_max if index == 0 else max(stoptime, current_max)

    # Define document packet (now that global start and end time are known)
    document_packet = create_document_packet("testing", starttime, stoptime)
    czml_packets.insert(0, document_packet)

    # Write output
    with open(os.path.join(tracks_dir, 'combined.czml'), 'w') as outfile:
        json.dump(czml_packets, outfile)

if __name__ == "__main__":
    process_dir("../../data/tracks/")
