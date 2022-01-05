// The URL on your server where CesiumJS's static files are hosted.
window.CESIUM_BASE_URL = process.env.CESIUM_BASE_URL;

import * as Cesium from 'cesium';
import "cesium/Build/Cesium/Widgets/widgets.css";
import "./style.css";
//import viewerCesiumNavigationMixin from 'cesium-navigation';
import placeholderImage from './placeholder.png';
import Cartesian3 from 'cesium/Source/Core/Cartesian3';
import Cartographic from 'cesium/Source/Core/Cartographic';

// Your access token can be found at: https://cesium.com/ion/tokens.
Cesium.Ion.defaultAccessToken = process.env.CESIUM_TOKEN;

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

// Instantiate the custom infobox from the template and
// put it inside the cesium viewer element for it to be rendered properly
const infobox = document.querySelector('#infoBox').content.cloneNode(true);
viewer._element.appendChild(infobox);

// Some variables
let photoEntities; // entityList
let trackEntities; // entityList
let lastSelectedFlyToEntity; // tracked to determine camera position when flying to a new entity
let lastSelectedInfoboxEntity;

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

const updateInfoboxTrackEntity = entity => {
  lastSelectedInfoboxEntity = entity;
  document.querySelector("#selectedPhoto").style.display = 'none'; // hide photo
  document.querySelector('#selectedPhotoCaption').innerHTML = entity.id;
  const table = document.querySelector("#track-metadata")
  table.style.display = '';
  
  const props = {
    start_time: {
      label: "Start time",
      format: d => (new Date(d)).toLocaleString()
    },
    end_time: {
      label: "End time",
      format: d => (new Date(d)).toLocaleString()
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
  
  // String interpolation FTW
  table.innerHTML = `${Object.keys(props).map(id => 
    `<tr><td>${props[id].label}</td><td>${props[id].format(entity.properties[id]._value)}</td></tr>`).join('')}`;
  
    document.querySelector(".cesium-infoBox").style.display = ''; // show the box
}

// Moves the camera to the entity
const flyToEntity = entity => {
  if (entity.position === undefined) return;

  // Correct the height above terrain for an entity, since they are clamped to ground, which makes height = 0
  //TODO: is there no obvious way to handle this??
  const correctHeight = cartesian3 => {
    const carto = Cartographic.fromCartesian(cartesian3);
    const height = viewer.scene.globe.getHeight(carto);
    return Cartesian3.fromRadians(carto.longitude, carto.latitude, height);
  }

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
  viewer.camera.flyTo({
    destination: newPosition,
    orientation : { heading, pitch, roll: 0.0 },
    duration: 1.0
  });

  lastSelectedFlyToEntity = entity;
};

// Reset the lastSelectedFlyToEntity if the camera moved too much
viewer.camera.percentageChanged = 1;
viewer.camera.changed.addEventListener(() => {
  lastSelectedFlyToEntity = undefined;
});

// Moves the photo timeline to the entity
const photoTimelineToEntity = entity => {
  const img = document.getElementById(entity.id);
  img.scrollIntoView({inline: "center"});
}

// Moves the timeline slider/cursor to the time of the entity
const timelineToEntity = entity => {
  const julianDate = Cesium.JulianDate.fromIso8601(entity.properties.time._value);
  viewer.clock.currentTime = julianDate;
}

const previousEntity = () => {
  if (lastSelectedInfoboxEntity.id.startsWith('photo_')) {
    photoEntities.previous();
  }
  if (lastSelectedInfoboxEntity.id.startsWith('line_')) {
    trackEntities.previous();
  }
}
document.querySelector('.btn-prev').onclick = previousEntity;

const nextEntity = () => {
  if (lastSelectedInfoboxEntity.id.startsWith('photo_')) {
    photoEntities.next();
  }
  if (lastSelectedInfoboxEntity.id.startsWith('line_')) {
    trackEntities.next();
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
  else if (Cesium.defined(entity) && entity.id.startsWith('photo_')) {
    photoEntities.select(entity);
    photoTimelineToEntity(entity);
    timelineToEntity(entity);
    flyToEntity(entity);
    updateInfobox(entity);
  }
  else {
    // Effectively prevents other entities from being selected
    viewer.selectedEntity = undefined;
  }
}
viewer.selectedEntityChanged.addEventListener(onSelectEntity);

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

      // Set the disableDepthTestDistance to a high number, but not INFINITY. The effect is that markers are not clipped
      // at their edges, but are hidden behind terrain (mountains). Setting to INFINITY would do no depth testing at all
      // (similar to viewer.scene.globe.depthTestAgainstTerrain = false)
      entity.point.disableDepthTestDistance = new Cesium.ConstantProperty(100000);
    }

    // This combines well with entity.point.disableDepthTestDistance of the photo markers
    viewer.scene.globe.depthTestAgainstTerrain = true;

    // GPS tracks
    const entities = allEntities.filter(entity => entity.id.startsWith('line_'));
    trackEntities = entityList(entities);

    // Tracking point
    const point = allEntities.find(entity => entity.id === 'point_0');
    //viewer.trackedEntity = point;
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


// Click the globe to see the cartographic position
const coordinatePicker = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
coordinatePicker.setInputAction(event => {
  const cartesian = viewer.camera.pickEllipsoid(
    event.position,
    viewer.scene.globe.ellipsoid
  );
  if (cartesian) {
    const carto = Cesium.Cartographic.fromCartesian(cartesian);
    const height = viewer.scene.globe.getHeight(carto);
    console.log([Cesium.Math.toDegrees(carto.longitude).toFixed(4),
      Cesium.Math.toDegrees(carto.latitude).toFixed(4),
      height.toFixed(0)].join(','));
  }
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);
