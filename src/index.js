// The URL on your server where CesiumJS's static files are hosted.
window.CESIUM_BASE_URL = process.env.CESIUM_BASE_URL;

import * as Cesium from 'cesium';
import "./widgets.css"; // Copied from cesium/Build/Cesium/Widgets/widgets.css, but it is not exported properly, giving problems with webpack
import "./style.css";
//import viewerCesiumNavigationMixin from 'cesium-navigation';
import { loadTrack } from './tracks';
import placeholderImage from './placeholder.png';

// Your access token can be found at: https://cesium.com/ion/tokens.
Cesium.Ion.defaultAccessToken = process.env.CESIUM_TOKEN;

// The key for the dataset to load
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

// Load config
const configPath = `data/${key}/config.json`;
fetch(configPath)
  .then(result => result.json())
  .then(config => {

    // Fly to home view
    const homeCoords = config.home;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(...homeCoords),
      duration: 1.0
    });
  });
