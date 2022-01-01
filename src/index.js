// The URL on your server where CesiumJS's static files are hosted.
window.CESIUM_BASE_URL = process.env.CESIUM_BASE_URL;

import * as Cesium from 'cesium';
import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
//import viewerCesiumNavigationMixin from 'cesium-navigation';
import { loadTrack } from './tracks';
import placeholderImage from './placeholder.png';

// Your access token can be found at: https://cesium.com/ion/tokens.
Cesium.Ion.defaultAccessToken = process.env.CESIUM_TOKEN;

const urlSearchParams = new URLSearchParams(window.location.search);
const key = urlSearchParams.get('key');

// Some variables
let photoEntities = [];
let currentPhotoEntity = undefined;

// Set up viewer
const viewer = new Cesium.Viewer('cesiumContainer', {
  terrainProvider: Cesium.createWorldTerrain(),
  baseLayerPicker: false,
  shouldAnimate: false, // don't automatically play animation
  infoBox: false        // we'll use a custom infobox
});

// Put the custom infobox inside the cesium viewer element for it to be rendered properly
const template = document.querySelector('#infoBox').content.cloneNode(true);
viewer._element.appendChild(template);

// Updates the infobox with the selected photo
const updateInfobox = entity => {
  document.querySelector('#selectedPhoto').src = entity.properties.src;
  document.querySelector('#selectedPhotoCaption').innerHTML = entity.name;
  document.querySelector(".cesium-infoBox").style.display = '';
}

// Initialize cesium-navigation plugin
const options = {};
//options.defaultResetView = Rectangle.fromDegrees(71, 3, 90, 14);
options.enableCompass = true;
options.enableZoomControls = true;
options.enableDistanceLegend = true;
options.units = 'kilometers' // default is kilometers;
// turf helpers units https://github.com/Turfjs/turf/blob/v5.1.6/packages/turf-helpers/index.d.ts#L20
//options.distanceLabelFormatter = (convertedDistance, units : Units): string => { ... } // custom label formatter

//viewer.extend(viewerCesiumNavigationMixin, options);



/* Initialize the viewer clock:
  Assume the radar samples are 30 seconds apart, and calculate the entire flight duration based on that assumption.
  Get the start and stop date times of the flight, where the start is the known flight departure time (converted from PST 
    to UTC) and the stop is the start plus the calculated duration. (Note that Cesium uses Julian dates. See 
    https://simple.wikipedia.org/wiki/Julian_day.)
  Initialize the viewer's clock by setting its start and stop to the flight start and stop times we just calculated. 
  Also, set the viewer's current time to the start time and take the user to that time. 
*/
// const timeStepInSeconds = 30;
// const totalSeconds = timeStepInSeconds * (flightData.length - 1);
// const start = Cesium.JulianDate.fromIso8601("2020-03-09T23:10:00Z");
// const stop = Cesium.JulianDate.addSeconds(start, totalSeconds, new Cesium.JulianDate());
// viewer.clock.startTime = start.clone();
// viewer.clock.stopTime = stop.clone();
// viewer.clock.currentTime = start.clone();
// viewer.timeline.zoomTo(start, stop);
// // Speed up the playback speed 50x.
// viewer.clock.multiplier = 50;
// // Start playing the scene.
// viewer.clock.shouldAnimate = false;

// The SampledPositionedProperty stores the position and timestamp for each sample along the radar sample series.
//const positionProperty = new Cesium.SampledPositionProperty();

// for (let i = 0; i < flightData.length; i++) {
//   const dataPoint = flightData[i];

//   // Declare the time for this individual sample and store it in a new JulianDate instance.
//   const time = Cesium.JulianDate.addSeconds(start, i * timeStepInSeconds, new Cesium.JulianDate());
//   const position = Cesium.Cartesian3.fromDegrees(dataPoint.longitude, dataPoint.latitude, dataPoint.height);
//   // Store the position along with its timestamp.
//   // Here we add the positions all upfront, but these can be added at run-time as samples are received from a server.
//   positionProperty.addSample(time, position);

//   viewer.entities.add({
//     description: `Location: (${dataPoint.longitude}, ${dataPoint.latitude}, ${dataPoint.height})`,
//     position: position,
//     point: { pixelSize: 10, color: Cesium.Color.RED }
//   });
// }

// // STEP 4 CODE (green circle entity)
// // Create an entity to both visualize the entire radar sample series with a line and add a point that moves along the samples.
// const airplaneEntity = viewer.entities.add({
//   availability: new Cesium.TimeIntervalCollection([ new Cesium.TimeInterval({ start: start, stop: stop }) ]),
//   position: positionProperty,
//   point: { pixelSize: 30, color: Cesium.Color.GREEN },
//   path: new Cesium.PathGraphics({ width: 3 })
// });
// // Make the camera track this moving entity.
// viewer.trackedEntity = airplaneEntity;

// Moves the camera to the entity
const flyToEntity = entity => {
  const position = Cesium.Cartographic.fromCartesian(entity.position._value);
  const height = viewer.camera.positionCartographic.height;
  position.height = height;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromRadians(
      position.longitude,
      position.latitude,
      height),
    duration: 1.0
  });
};

// Moves the photo timeline to the entity
const photoTimelineToEntity = entity => {
  const img = document.getElementById(entity.id);
  img.scrollIntoView({inline: "center"});
}

// Moves the timeline slider to the entity
const timelineToEntity = entity => {
  const julianDate = Cesium.JulianDate.fromIso8601(entity.properties.time._value);
  viewer.clock.currentTime = julianDate;
}

const previousPhoto = () => {
  const index = photoEntities.indexOf(currentPhotoEntity);
  if (index === -1) return;
  const newIndex = index > 0 ? index - 1 : photoEntities.length - 1;
  currentPhotoEntity = photoEntities[newIndex];
  viewer.selectedEntity = currentPhotoEntity;
}
document.querySelector('.btn-prev').onclick = previousPhoto;

const nextPhoto = () => {
  const index = photoEntities.indexOf(currentPhotoEntity);
  if (index === -1) return;
  const newIndex = (index + 1) % photoEntities.length;
  currentPhotoEntity = photoEntities[newIndex];
  viewer.selectedEntity = currentPhotoEntity;
}
document.querySelector('.btn-next').onclick = nextPhoto;

// Arrow key handler
document.querySelector('body').addEventListener('keydown', event => {
  if (event.key === "ArrowLeft") previousPhoto();
  if (event.key === "ArrowRight") nextPhoto();
});

const closeInfoBox = () => {
  currentPhotoEntity = undefined;
  document.querySelector(".cesium-infoBox").style.display = 'none';
}
document.querySelector('.cesium-infoBox-close').onclick = closeInfoBox;


// Handler for selecting a timeline photo (img)
const selectTimelinePhoto = entity => {
  viewer.selectedEntity = entity; // this will trigger selectPhotoEntity
};

// Handler for map selection of an entity.
// Don't call directly, but set viewer.selectedEntity to trigger it.
const selectPhotoEntity = entity => {
  if (Cesium.defined(entity) && entity.id.startsWith('photo_')) {
    currentPhotoEntity = entity;
    photoTimelineToEntity(entity);
    timelineToEntity(entity);
    flyToEntity(entity);
    updateInfobox(entity);
  }
  else {
    // Effectively prevents non-photo entities from being selected
    viewer.selectedEntity = undefined;
  }
}
viewer.selectedEntityChanged.addEventListener(selectPhotoEntity);

// Scrolling for photo timeline
const element = document.querySelector('#photoTimeline');
element.addEventListener('wheel', (event) => {
  event.preventDefault();
  element.scrollBy({
    left: event.deltaY < 0 ? -30 : 30,
  });
});

// Load the data, filter, sort and display the photos
const czml_path = `data/${key}/combined.czml`;
loadTrack(czml_path, viewer)
  .then(() => {
    // Get a sorted list of all photo entities
    const allEntities = viewer.dataSources._dataSources[0].entities.values;
    photoEntities = allEntities.filter(entity => entity.id.startsWith('photo'));
    photoEntities.sort((a, b) => { 
      return a.properties.time._value.localeCompare(b.properties.time._value);
    });

    // The div we'll put the photos in
    const target = document.querySelector('#photoTimeline');
    
    // Lazy loading for images
    const observer = new IntersectionObserver((entries, observer) => {
      for (let entry of entries) {
        if (entry.isIntersecting) {
          const img = entry.target;
          if (img.src === placeholderImage) {
            img.setAttribute('src', img.getAttribute('lazysrc'));
          }
        }
      }
    }, {
      root: target, rootMargin: '0px', threshold: 0.01
    });

    // For each photo add a placeholder to the timeline
    for (let entity of photoEntities) {
      const img = document.createElement('img');
      img.src = placeholderImage;
      img.onclick = event => selectTimelinePhoto(event.target.entity);
      img.setAttribute('id', entity.id);
      img.setAttribute('height', '100%');
      img.setAttribute('alt', entity.id);
      img.setAttribute('lazysrc', entity.properties.src._value);
      img.entity = entity;
      target.appendChild(img);
      // Observe for img visibility
      observer.observe(img);
    }

  });

// Fly to home view
viewer.camera.flyTo({
  destination: Cesium.Cartesian3.fromDegrees(13.862629, 60.050526, 50000.0),
  duration: 1.0
});
