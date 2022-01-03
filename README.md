# Cesium Travelmap

Display photo locations and GPS tracks on an interactive map and timeline.

If GPS information is not available in a photo, the time and GPS track will be used to position the photo on the map.

In short:
1. Exiftool is used to extract photo GPS data and date & time to a CSV file.
2. A Python script combines one or more CSV files and GPX tracks and generates a CZML file that contains the paths and markers to display.
3. CZML is read by the Cesium-based web application and displays the tracks and photo locations on the map.

## Prerequisites

For preprocessing the data:
* Exiftool
* Python 3

For building / developing the application:
 * Node + npm

The built application can be statically served, e.g. with nginx

## Configuration

Create a .env file with the following information:

```
# Cesium base url
CESIUM_BASE_URL=/

# Your cesium token, get one at https://cesium.com/learn/cesiumjs-learn/cesiumjs-quickstart/
CESIUM_TOKEN=

# Directory containing the tracks and photos, used for preprocessing
DATA_DIR=/path/to/data

# Directory where exiftool is installed
EXIFTOOL_DIR=/opt/Image-ExifTool-12.21
```

## Preprocess data

DATA_DIR is the base data directory, KEY_DIR is used to support multiple datasets on the same server. The name of KEY_DIR can be anything and can be generated randomly to make it harder to find.

Put the gpx files in DATA_DIR/KEY_DIR/tracks.

Put series of photos in separate folders. One folder for each author or source is recommended. Each of these folders should be under DATA_DIR/KEY_DIR/photos/.

In each folder, put a config.cfg file and modify the content as following. Attribution is the author or source of the photo and delta.hours/minutes are used to correct the photo time. Optionally, any photo coordinates can be manually specified in the manual_coords section. Coordinates are longitude(!), latitude(!), altitude. Photos for which no coordinates can be determined (because they lack the GPS information or they are outside the GPX track time-wise) will be discarded.

```
[global]
attribution=Peter
delta.hours=1
delta.minutes=0

[manual_coords]
DSC03150.JPG=7.62354,44.06445,777.4
DSC03151.JPG=7.62354,44.06446,777.4
```

Execute the preprocessing script:
```
python3 preprocess/gpx2czml.py key
```
This will perform a number of tasks:
* Run exiftool for each directory with photos. This will generate a csv file with all the required information extracted from the photos.
* Combine all GPX tracks and photo information into one CZML file (DATA_DIR/KEY_DIR/combined.czml) that can be visualized.

## Run the visualizer

Make sure .env contains the correct CESIUM_TOKEN and DATA_DIR values.

```
npm start
```

Access the visualizer at http://localhost:8081?key=KEY_DIR, where KEY_DIR is the value for the corresponding dataset.
