import markerTent from './images/marker_tent.svg';
import markerMountain from './images/marker_mountain.svg';

const getMarker = symbol => {
  switch(symbol) {
    case 'tent':
      return markerTent;
    case 'mountain':
      return markerMountain;
    default:
      console.log("Marker not found:", symbol);
  }
}

export { getMarker };
