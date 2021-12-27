#!/bin/bash

source ../.env
cd /opt/Image-ExifTool-12.21

# exiftool documentation: https://exiftool.org/exiftool_pod.html
./exiftool -filename -gpslatitude# -gpslongitude# -gpsaltitude# -gpsdatestamp -gpstimestamp -datetimeoriginal -createdate -dateFormat "%Y-%m-%d %H:%M:%S%z" -T -csv --ext csv $DATA_DIR/photos/peter > $DATA_DIR/photos/peter/photos.csv
./exiftool -filename -gpslatitude# -gpslongitude# -gpsaltitude# -gpsdatestamp -gpstimestamp -datetimeoriginal -createdate -dateFormat "%Y-%m-%d %H:%M:%S%z" -T -csv --ext csv $DATA_DIR/photos/peter-telefoon > $DATA_DIR/photos/peter-telefoon/photos.csv
./exiftool -filename -gpslatitude# -gpslongitude# -gpsaltitude# -gpsdatestamp -gpstimestamp -datetimeoriginal -createdate -dateFormat "%Y-%m-%d %H:%M:%S%z" -T -csv --ext csv $DATA_DIR/photos/bas > $DATA_DIR/photos/bas/photos.csv
