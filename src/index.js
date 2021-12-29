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

// STEP 4 CODE (replaces steps 2 and 3)
// Keep your `Cesium.Ion.defaultAccessToken = 'your_token_here'` line from before here. 
const viewer = new Cesium.Viewer('cesiumContainer', {
  terrainProvider: Cesium.createWorldTerrain(),
  baseLayerPicker: false,
  shouldAnimate: false // don't automatically play animation
});


// Set infobox css
const frame = viewer.infoBox.frame;
frame.addEventListener('load', function () {
    var cssLink = frame.contentDocument.createElement('link');
    cssLink.href = Cesium.buildModuleUrl('infobox.css');
    cssLink.rel = 'stylesheet';
    cssLink.type = 'text/css';
    frame.contentDocument.head.appendChild(cssLink);
}, false);


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
const positionProperty = new Cesium.SampledPositionProperty();

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

const selectPhotoHandler = event => {
  const entity = event.target.entity;

  // Update timeline
  const julianDate = Cesium.JulianDate.fromIso8601(entity.properties.time._value);
  viewer.clock.currentTime = julianDate;

  // Select entity
  viewer.selectedEntity = entity;

  // Fly to entity (but keep camera height)
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

loadTrack("data/combined.czml", viewer)
  .then(() => {
    // Get a sorted list of all photo entities
    const allEntities = viewer.dataSources._dataSources[0].entities.values;
    const entities = allEntities.filter(entity => entity.id.startsWith('photo'));
    entities.sort((a, b) => { 
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
    for (let entity of entities) {
      const img = document.createElement('img');
      img.src = placeholderImage;
      img.onclick = selectPhotoHandler;
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

viewer.camera.flyTo({
  destination: Cesium.Cartesian3.fromDegrees(13.862629, 60.050526, 50000.0)
});

console.log(viewer.dataSources);

// Scrolling for photo timeline
const element = document.querySelector('#photoTimeline');
element.addEventListener('wheel', (event) => {
  event.preventDefault();
  element.scrollBy({
    left: event.deltaY < 0 ? -30 : 30,
  });
});
