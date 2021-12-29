import * as Cesium from 'cesium';

export const loadTrack = (path, viewer) => {
  return fetch(path)
    .then(response => response.json())
    .then(czml => {
      viewer.dataSources
        .add(Cesium.CzmlDataSource.load(czml))
        .then(ds => {
          //viewer.trackedEntity = ds.entities.getById("point_0");
          console.log(ds);
        });
    });
  };
