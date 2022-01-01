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

## Preprocess data

DATA_DIR is the base data directory, KEY_DIR is used to support multiple datasets on the same server. The name of KEY_DIR could be generated randomly to make it harder to find.

Put the gpx files in DATA_DIR/KEY_DIR/tracks.

Put series of photos in separate folders. One folder for each author or source is recommended. Each of these folders should be under DATA_DIR/KEY_DIR/photos/.

For each folder of photos, run exiftool; modify or look at preprocess/run_exif.sh for the arguments. This will generate a csv file with all the required information extracted from the photos.

In each folder, put a config.cfg file and modify the content as following. Attribution is the author or source of the photo and delta.hours/minutes are used to correct the photo time.

```
[global]
attribution=Peter
delta.hours=1
delta.minutes=0
```

Execute the preprocessing script:
```
python3 gpx2czml.py key
```
This will merge all track and photo information into one CZML file (DATA_DIR/KEY_DIR/combined.czml) that can be visualized.

## Run the visualizer

Make sure .env contains the correct CESIUM_TOKEN and DATA_DIR values.

```
npm start
```
