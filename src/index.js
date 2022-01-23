// The URL on your server where CesiumJS's static files are hosted.
window.CESIUM_BASE_URL = process.env.CESIUM_BASE_URL;

import * as Cesium from 'cesium';
import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
//import viewerCesiumNavigationMixin from 'cesium-navigation';
import placeholderImage from './placeholder.png';
import { getMarker } from './markers';
import Cartesian3 from 'cesium/Source/Core/Cartesian3';
import Cartographic from 'cesium/Source/Core/Cartographic';
import JulianDate from 'cesium/Source/Core/JulianDate';

// Your access token can be found at: https://cesium.com/ion/tokens.
Cesium.Ion.defaultAccessToken = process.env.CESIUM_TOKEN;

Cesium.Camera.DEFAULT_VIEW_RECTANGLE = new Cesium.Rectangle(
  -0.28035843653241455, 0.752411813958121, 0.39315544282710924, 1.0074066673564466);
Cesium.Camera.DEFAULT_VIEW_FACTOR = 1.0;

// The key for the dataset to load
const urlSearchParams = new URLSearchParams(window.location.search);
const key = urlSearchParams.get('key');

// Set up viewer
const viewer = new Cesium.Viewer('cesiumContainer', {
  terrainProvider: Cesium.createWorldTerrain(),
  baseLayerPicker: true,
  shouldAnimate: false, // don't automatically play animation
  infoBox: false        // we'll use a custom infobox
});

// Load config
const configPath = `data/${key}/config.json`;
fetch(configPath)
  .then(result => result.json())
  .then(config => {
    Cesium.Camera.DEFAULT_VIEW_FACTOR = 0.002;
    const homeRect = config.home_rect;
    Cesium.Camera.DEFAULT_VIEW_RECTANGLE = new Cesium.Rectangle(
      homeRect.west, homeRect.south, homeRect.east, homeRect.north);
    viewer.camera.flyHome(5.0);
  });

// Instantiate the custom infobox from the template and
// put it inside the cesium viewer element for it to be rendered properly
const infobox = document.querySelector('#infoBox').content.cloneNode(true);
viewer._element.appendChild(infobox);

// Some variables
let photoEntities; // entityList
let trackEntities; // entityList
let poiEntities;   // entityList
let lastSelectedFlyToEntity; // tracked to determine camera position when flying to a new entity
let lastSelectedInfoboxEntity;
let trackedEntity; //entity to track
let isFlyingToEntity = false; // a flag to indicate if the camera is moving because of a flyToEntity call

// "Class" that keeps track of a list of entities and the selected entity,
// has previous/next functions that also update the viewer.selectedEntity
const entityList = (entities) => {
  const list = entities;
  let index = -1;
  return {
    list,
    current: () => list[index],
    select: (entity) => {
      index = list.indexOf(entity)
    },
    previous: () => {
      if (index === -1) return;
      index = index > 0 ? index - 1 : list.length - 1;
      viewer.selectedEntity = list[index];
    },
    next: () => {
      if (index === -1) return;
      index = (index + 1) % list.length;
      viewer.selectedEntity = list[index];
    }
  };
};

// Updates the infobox with the selected photo
const updateInfobox = entity => {
  lastSelectedInfoboxEntity = entity;
  document.querySelector('#track-metadata').style.display = 'none'; // hide metadata
  document.querySelector('#selectedPhoto').src = entity.properties.src;
  document.querySelector('#selectedPhotoCaption').innerHTML = entity.name;
  document.querySelector("#selectedPhoto").style.display = ''; // show photo
  document.querySelector(".cesium-infoBox").style.display = ''; // show the box
}

const updateInfoboxPOI = entity => {
  lastSelectedInfoboxEntity = entity;
  document.querySelector('#track-metadata').style.display = 'none'; // hide metadata
  document.querySelector("#selectedPhoto").style.display = 'none'; // hide photo
  document.querySelector('#selectedPhotoCaption').innerHTML = entity.properties['name']
  document.querySelector(".cesium-infoBox").style.display = ''; // show the box
}

const updateInfoboxTrackEntity = entity => {
  lastSelectedInfoboxEntity = entity;
  document.querySelector("#selectedPhoto").style.display = 'none'; // hide photo
  document.querySelector('#selectedPhotoCaption').innerHTML = (new Date(entity.name)).toLocaleDateString("nl-NL");
  const table = document.querySelector("#track-metadata")
  table.style.display = '';
  
  const props = {
    source: {
      label: "Source",
      format: d => d
    },
    start_time: {
      label: "Start time",
      format: d => (new Date(d)).toLocaleString("nl-NL")
    },
    end_time: {
      label: "End time",
      format: d => (new Date(d)).toLocaleString("nl-NL")
    },
    duration: {
      label: "Duration",
      format: d => `${Math.floor(d / 3600)}h ${Math.floor((d % 3600) / 60)}m ${Math.floor(d % 60)}s`
    },
    length_2d: {
      label: "Distance",
      format: d => `${(d / 1000).toFixed(1)} km`
    },
    ascent: {
      label: "Ascent",
      format: d => `${d.toFixed(0)} meters`
    },
    descent: {
      label: "Descent",
      format: d => `${d.toFixed(0)} meters`
    },
    min_elevation: {
      label: "Min elevation",
      format: d => `${d.toFixed(0)} meters`
    },
    max_elevation: {
      label: "Max elevation",
      format: d => `${d.toFixed(0)} meters`
    },
  }
  
  table.innerHTML = Object.keys(props).map(key => 
    `<tr><td>${props[key].label}</td><td>${props[key].format(entity.properties[key]._value)}</td></tr>`).join('');
  
  document.querySelector(".cesium-infoBox").style.display = ''; // show the box
}

  // Correct the height above terrain for an entity, since they are clamped to ground, which makes height = 0
  //TODO: is there no obvious way to handle this??
  const correctHeight = cartesian3 => {
    const carto = Cartographic.fromCartesian(cartesian3);
    const height = viewer.scene.globe.getHeight(carto);
    return Cartesian3.fromRadians(carto.longitude, carto.latitude, height);
  }

// Moves the camera to the entity
const flyToEntity = entity => {
  if (entity.position === undefined) return;
  
  // Complete any current flight, in order to get a correct reference point for the next flight.
  // This prevents the focus from moving out of view when quickly going through photos,
  // which would interrupt any in-progress flight at an unintended position.
  viewer.camera.completeFlight();
  
  // If lastSelectedFlyToEntity was reset (because of camera movement), we use the terrain
  // at the center of the viewport to determine the viewing distance, otherwise we
  // use the last selected entity
  let oldLookAtPosition;
  if (lastSelectedFlyToEntity === undefined) {
    const w = document.getElementById('cesiumContainer').scrollWidth;
    const h = document.getElementById('cesiumContainer').scrollHeight;
    const ray = viewer.camera.getPickRay(new Cesium.Cartesian2(w/2, 0.5*h));
    oldLookAtPosition = viewer.scene.globe.pick(ray, viewer.scene);
  }
  else {
    oldLookAtPosition = correctHeight(lastSelectedFlyToEntity.position._value);
  }

  // Move toward the new entity, but keep same orientation
  const entityPos = correctHeight(entity.position._value);
  const positionOffset = Cesium.Cartesian3.subtract(viewer.camera.positionWC, oldLookAtPosition, new Cartesian3(0, 0, 0));
  const newPosition = Cesium.Cartesian3.add(entityPos, positionOffset, new Cartesian3(0, 0, 0));
  const heading = viewer.camera.heading;
  const pitch = viewer.camera.pitch;
  isFlyingToEntity = true;
  viewer.camera.flyTo({
    destination: newPosition,
    orientation : { heading, pitch, roll: 0.0 },
    duration: 1.0
  });

  lastSelectedFlyToEntity = entity;
};

// Reset the lastSelectedFlyToEntity if the camera moved too much
viewer.camera.percentageChanged = 0.05;
viewer.camera.changed.addEventListener(() => {
  if (!isFlyingToEntity) {
    lastSelectedFlyToEntity = undefined;
  }
});

viewer.camera.moveEnd.addEventListener(() => {
  isFlyingToEntity = false;

  // Turn on depth testing only when pitch is shallow.
  // In other words: we don't need (or want) it when looking straight down.
  // Straight down is -PI/2 or -90 degrees.
  // Actually not sure if this works as expected....
  const pitchDegrees = viewer.camera.pitch / Cesium.Math.PI * 180;
  viewer.scene.globe.depthTestAgainstTerrain = pitchDegrees > -45;
});

// Moves the photo timeline to the entity
const photoTimelineToEntity = (entity, smooth=false) => {
  const img = document.getElementById(entity.id);
  img.scrollIntoView({
    inline: "center",
    behavior: smooth ? "smooth": "auto"
  });
}

// Moves the timeline slider/cursor to the time of the entity
const timelineToEntity = entity => {
  const julianDate = Cesium.JulianDate.fromIso8601(entity.properties.time._value);
  viewer.clock.currentTime = julianDate;
}

const previousEntity = () => {
  if (lastSelectedInfoboxEntity === undefined) return;
  if (lastSelectedInfoboxEntity.id.startsWith('photo_')) {
    photoEntities.previous();
  }
  if (lastSelectedInfoboxEntity.id.startsWith('line_')) {
    trackEntities.previous();
  }
  if (lastSelectedInfoboxEntity.id.startsWith('poi_')) {
    poiEntities.previous();
  }
}
document.querySelector('.btn-prev').onclick = previousEntity;

const nextEntity = () => {
  if (lastSelectedInfoboxEntity === undefined) return;
  if (lastSelectedInfoboxEntity.id.startsWith('photo_')) {
    photoEntities.next();
  }
  if (lastSelectedInfoboxEntity.id.startsWith('line_')) {
    trackEntities.next();
  }
  if (lastSelectedInfoboxEntity.id.startsWith('poi_')) {
    poiEntities.next();
  }
}
document.querySelector('.btn-next').onclick = nextEntity;

// Arrow key handler
document.querySelector('body').addEventListener('keydown', event => {
  if (event.key === "ArrowLeft") previousEntity();
  if (event.key === "ArrowRight") nextEntity();
});

const closeInfoBox = () => {
  document.querySelector(".cesium-infoBox").style.display = 'none';
  viewer.selectedEntity = undefined;
}
document.querySelector('.cesium-infoBox-close').onclick = closeInfoBox;


// Handler for selecting a timeline photo (img)
const selectTimelinePhoto = entity => {
  viewer.selectedEntity = entity; // this will trigger onSelectEntity
};

// Handler for map selection of an entity.
// Don't call directly, but set viewer.selectedEntity to trigger it.
const onSelectEntity = entity => {
  if (Cesium.defined(entity) && entity.id.startsWith('line_')) {
    trackEntities.select(entity);
    updateInfoboxTrackEntity(entity);
  }
  else if (Cesium.defined(entity) && entity.id.startsWith('poi_')) {
    poiEntities.select(entity);
    updateInfoboxPOI(entity);
  }
  else if (Cesium.defined(entity) && entity.id.startsWith('photo_')) {
    photoEntities.select(entity);
    photoTimelineToEntity(entity);
    timelineToEntity(entity);
    updateInfobox(entity);
    if (!viewer.clock.shouldAnimate) {
      flyToEntity(entity);
    }
  }
  else {
    // Effectively also prevents other entities from being selected
    closeInfoBox();
  }
}
viewer.selectedEntityChanged.addEventListener(onSelectEntity);

// Wheel scrolling for photo timeline
const photoTimeline = document.querySelector('#photoTimeline');
photoTimeline.addEventListener('wheel', (event) => {
  event.preventDefault();
  photoTimeline.scrollBy({
    left: event.deltaY < 0 ? -60 : 60,
  });
});

// Load the data, filter, sort and display the photos
const czml_path = `data/${key}/combined.czml`;
fetch(czml_path)
  .then(response => response.json())
  .then(czml => viewer.dataSources.add(Cesium.CzmlDataSource.load(czml)))
  .then(() => {
    // Get a sorted list of all photo entities
    const allEntities = viewer.dataSources._dataSources[0].entities.values;
    const filteredEntities = allEntities.filter(entity => entity.id.startsWith('photo'));
    filteredEntities.sort((a, b) => { 
      return a.properties.time._value.localeCompare(b.properties.time._value);
    });
    photoEntities = entityList(filteredEntities);

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
    for (let entity of photoEntities.list) {
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

      // For easy clock comparisons
      entity.properties.julianDate = JulianDate.fromIso8601(entity.properties.time._value);

      // Set the disableDepthTestDistance to a high number, but not INFINITY. The effect is that markers are not clipped
      // at their edges, but are hidden behind terrain (mountains). Setting to INFINITY would do no depth testing at all
      // (similar to viewer.scene.globe.depthTestAgainstTerrain = false)
      entity.point.disableDepthTestDistance = new Cesium.ConstantProperty(100000);
    }

    // By default, don't depth test (looking straight down),
    // because marker edges might be clipped. Also see camera.moveEnd handler.
    viewer.scene.globe.depthTestAgainstTerrain = false;
    viewer.scene.screenSpaceCameraController.enableCollisionDetection = true

    // GPS tracks
    const entities = allEntities.filter(entity => entity.id.startsWith('line_'));
    trackEntities = entityList(entities);

    // Tracking point
    trackedEntity = allEntities.find(entity => entity.id === 'track_entity');
  });

const pois_path = `data/${key}/pois.geojson`;
fetch(pois_path)
  .then(response => response.json())
  .then(geojson => {
    Cesium.GeoJsonDataSource.clampToGround = true;
    viewer.dataSources.add(Cesium.GeoJsonDataSource.load(geojson))
    .then(dataSource => {
      var entities = dataSource.entities.values;
      for (var i = 0; i < entities.length; i++) {
          var entity = entities[i];
          entity.billboard.image = getMarker(entity.properties['marker-symbol']._value);
      }
      poiEntities = entityList(entities);
    });
  });

// Log the cartographic position on clicking the globe. Mainly for manual positioning of photos and debugging
const coordinatePicker = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
coordinatePicker.setInputAction(event => {
  const cartesian = viewer.camera.pickEllipsoid(
    event.position,
    viewer.scene.globe.ellipsoid
  );
  if (cartesian) {
    const carto = Cesium.Cartographic.fromCartesian(cartesian);
    const height = viewer.scene.globe.getHeight(carto);
    let s = lastSelectedInfoboxEntity !== undefined ? lastSelectedInfoboxEntity.properties.src + "=" : '';
    s += [Cesium.Math.toDegrees(carto.longitude).toFixed(6),
          Cesium.Math.toDegrees(carto.latitude).toFixed(6),
          height.toFixed(0)].join(',');
    console.log(s);
    console.log(viewer.camera.computeViewRectangle(viewer.scene.globe.ellipsoid, new Cartesian3()));
  }
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

Cesium.knockout.getObservable(viewer.clockViewModel, 'shouldAnimate').subscribe(isAnimating => {
  if (isAnimating) {
    closeInfoBox();
    viewer.scene.globe.depthTestAgainstTerrain = true;
    trackedEntity._viewFrom._value = new Cartesian3(0, -2500, 2000);
    viewer.trackedEntity = trackedEntity;
  } else {
    viewer.trackedEntity = undefined; // "Release" camera from focussing on entity
  }
});

// From https://stackoverflow.com/a/27078401/1097971
function throttle (callback, limit) {
  var waiting = false;                      // Initially, we're not waiting
  return function () {                      // We return a throttled function
      if (!waiting) {                       // If we're not waiting
          callback.apply(this, arguments);  // Execute users function
          waiting = true;                   // Prevent future invocations
          setTimeout(function () {          // After a period of time
              waiting = false;              // And allow future invocations
          }, limit);
      }
  }
}

const photoTimelineToTimeline = () => {
  for (let [i, photo] of photoEntities.list.entries()) {
    // Select the last photo that is before the current time
    // (i.e. the one before the first after the current time)
    if (photo.properties.julianDate >= viewer.clock.currentTime) {
      photoTimelineToEntity(photoEntities.list[Math.max(0, i-1)], true);
      return;
    }
  }
}
viewer.timeline.addEventListener('settime', throttle(photoTimelineToTimeline, 200), false);
const updateToClock = () => {
  if (viewer.clock.shouldAnimate) {
    photoTimelineToTimeline();
  }
}
viewer.clock.onTick.addEventListener(throttle(updateToClock, 200));
viewer.clock.onTick.addEventListener(() => {
  if (viewer.clock.shouldAnimate) {
    // Setting to anything higher is really making me dizzy
    viewer.camera.rotateRight(0.001);
  }
});
