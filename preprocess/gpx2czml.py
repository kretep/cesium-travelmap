
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


def create_czml_path(df_input):
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

def point_with_trailing_path(df_input):
    
    # Store output in array
    czml_output = []

    # Define global variables
    global_id = "document"
    global_name = "document name test"
    global_version = "1.0"
    global_author = "gpx2czml.py"
    global_starttime = str(min(df_input['starttime'])).replace(" ", "T").replace(".000", "Z")
    global_stoptime = str(max(df_input['stoptime'])).replace(" ", "T").replace(".000", "Z")
    global_availability = global_starttime + "/" + global_stoptime    
    
    # Create packet with global variables
    global_element = {
        "id" : global_id,
        "name" : global_name,
        "version" : global_version,
        "author": global_author,
        "clock": {
            "interval": global_availability,
            "currentTime": global_starttime,
            "multiplier": 1000
        }
    }
    
    # Append global packet to output
    czml_output.append(global_element)
    
    # Define path variables
    path_id = "path"
    path_starttime = str(min(df_input['starttime'])).replace(" ", "T").replace(".000", "Z")
    path_stoptime = str(max(df_input['starttime'])).replace(" ", "T").replace(".000", "Z")
    path_availability = path_starttime + "/" + path_stoptime
    
    # Create path object
    path_object = {
            "id": path_id,
            "availability": path_availability,
            "position": {
                "epoch": path_starttime,
                "cartographicDegrees": create_czml_path(df)
            },
            "path" : {
                "material" : {
                    "polylineOutline" : {
                        "color" : {
                            "rgba" : [255, 255, 255, 200]
                        },
                        "outlineColor" : {
                            "rgba" : [0, 173, 253, 200]
                        },
                        "outlineWidth" : 5
                    }
                },
                "width" : 6,
                # "leadTime" : 10,
                # "trailTime" : 10000,
                "resolution" : 5,
                "heightReference": "RELATIVE_TO_GROUND"
            }
        }

    # Append path element to output
    czml_output.append(path_object)
        
    # Define point variable
    point_id = "Point"
    point_starttime = str(min(df_input['starttime'])).replace(" ", "T").replace(".000", "Z")
    point_stoptime = str(max(df_input['starttime'])).replace(" ", "T").replace(".000", "Z")
    point_availability = point_starttime + "/" + point_stoptime
    
    point_object = {
            "id": point_id,
            "availability": point_availability,
            "position": {
                "epoch": point_starttime,
                "cartographicDegrees": create_czml_path(df)
            },
            "point": {
                "color": {
                    "rgba": [255, 255, 255, 255]
                },
                "outlineColor": {
                    "rgba": [0, 253, 173, 255]
                },
                "outlineWidth": 6,
                "pixelSize": 8,
                "heightReference": "NONE"
            }   
        }

    czml_output.append(point_object)
    
    return czml_output


if __name__ == "__main__":
    
    tracks_dir = "../data/tracks/"
    for file in os.listdir(tracks_dir):
        print(file, file[-4:])
        if file[-4:] == '.gpx':
            gpx_file = open(os.path.join(tracks_dir, file), 'r')
            gpx = gpxpy.parse(gpx_file)
            
            df = parse_gpx(gpx)
            print(df.head())

            czml_output = point_with_trailing_path(df)

            with open(os.path.join(tracks_dir, file.split('.')[0] + '.czml'), 'w') as outfile:
                json.dump(czml_output, outfile)
