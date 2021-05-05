#!/bin/bash

source ../.env
cd /opt/Image-ExifTool-12.21
./exiftool -filename -gpslatitude -gpslongitude -gpsaltitude -gpsdatestamp -gpstimestamp -datetimeoriginal -createdate -n -T -csv $DATA_DIR/photos > $DATA_DIR/photos.csv
