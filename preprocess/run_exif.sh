#!/bin/bash

source ../.env
cd /opt/Image-ExifTool-12.21

# exiftool documentation: https://exiftool.org/exiftool_pod.html
./exiftool -filename -gpslatitude# -gpslongitude# -gpsaltitude# -gpsdatestamp -gpstimestamp -datetimeoriginal -createdate -dateFormat "%Y-%m-%d %H:%M:%S%z" -T -csv $DATA_DIR/photos > $DATA_DIR/photos.csv
