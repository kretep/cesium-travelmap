
import pandas as pd
import numpy as np
import gpxpy
import json
import os

# Adapted from Will Geary, "Visualizing a Bike Ride in 3D", https://willgeary.github.io/GPXto3D/

## See a primer on reading GPX data in python here: http://andykee.com/visualizing-strava-tracks-with-python.html

def parse_gpx(gpx_input_file):
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
    path_stoptime = format_datetime(max(df_input['starttime']))
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
    point_stoptime = format_datetime(max(df_input['starttime']))
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

def create_first_packet(name, df_input):
    starttime = format_datetime(min(df_input['starttime']))
    stoptime = format_datetime(max(df_input['stoptime']))
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

def create_czml(df_input):
    
    # Store output in array
    czml_output = []

    # Define global variables
    global_packet = create_first_packet("testing", df_input)
    czml_output.append(global_packet)

    # Coordinates used for both path and point
    coordinate_list = create_coordinate_list(df_input)

    # Path
    path_object = create_path("path", df_input, coordinate_list, [0, 173, 253, 200])
    czml_output.append(path_object)

    # Point
    point_object = create_point("point", df_input, coordinate_list, [0, 253, 173, 255])
    czml_output.append(point_object)
    
    return czml_output


if __name__ == "__main__":
    
    tracks_dir = "../../data/tracks/"
    for file in os.listdir(tracks_dir):
        print(file, file[-4:])
        if file[-4:] == '.gpx':
            gpx_file = open(os.path.join(tracks_dir, file), 'r')
            gpx = gpxpy.parse(gpx_file)
            
            df = parse_gpx(gpx)
            #print(df.head())
            czml_output = create_czml(df)

            # Write output
            with open(os.path.join(tracks_dir, file.split('.')[0] + '.czml'), 'w') as outfile:
                json.dump(czml_output, outfile)
