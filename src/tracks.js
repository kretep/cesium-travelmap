import * as Cesium from 'cesium';

export const loadTrack = (path, viewer) => {
  fetch(path)
    .then(response => response.json())
    .then(czml => {
      viewer.dataSources
        .add(Cesium.CzmlDataSource.load(czml))
        .then(function (ds) {
          //viewer.trackedEntity = ds.entities.getById("path");
        });
    });
  };
