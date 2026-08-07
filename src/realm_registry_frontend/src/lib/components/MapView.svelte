<script>
  /**
   * MapLibre 3D globe — vector tiles (sharp zoom) + no political borders + zoom-adaptive H3.
   * Uses MapLibre's globe projection so the planet stays a sphere, not a flat map.
   */
  import { createEventDispatcher, onDestroy, onMount } from 'svelte';
  import { browser } from '$app/environment';
  import { get } from 'svelte/store';
  import { _ } from 'svelte-i18n';
  import {
    buildHexPolygons,
    buildPointMarkers,
    capitalHexCenter,
    realmDisplayBounds,
    resolveCapitalZone,
  } from '$lib/globe/hex-data.js';

  import {
    buildHexHoverPopupHtml,
    buildMarkerHoverPopupHtml,
  } from '$lib/globe/realm-hover-popup.js';
  import {
    FLY_TO_MS,
    hexDisplayZoomKey,
    h3ResolutionForZoom,
    MAP_BG,
    MERCATOR_PROJECTION_MIN_ZOOM,
    softenGlobeBasemap,
    stripPoliticalLayers,
    ZONE_DATA_RESOLUTION,
  } from '$lib/globe/globe-config.js';
  import GlobeWireframeLoader from '$lib/components/GlobeWireframeLoader.svelte';

  export let realms = [];
  export let realmZoneData = {};
  export let searchQuery = '';
  export let loading = false;

  const dispatch = createEventDispatcher();
  const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
  const HEX_SOURCE = 'realm-hexes';
  const HEX_FILL = 'realm-hex-fill';
  const HEX_LINE = 'realm-hex-line';
  /** Far-side pins use DOM Markers — MapLibre depth-occludes circle layers. */
  const MARKER_COVERED_OPACITY = 0.48;

  let container;
  /** @type {import('maplibre-gl').Map | null} */
  let map = null;
  /** @type {typeof import('maplibre-gl') | null} */
  let maplibregl = null;
  /** @type {import('h3-js') | null} */
  let h3 = null;
  /** @type {Map<string, import('maplibre-gl').Marker>} */
  let markerById = new Map();
  /** @type {Map<string, object>} */
  let hexByIndex = new Map();
  /** @type {import('maplibre-gl').Popup | null} */
  let hoverPopup = null;
  let hoveredHexIndex = '';
  let hoveredMarkerId = '';
  let ready = false;
  let currentH3Res = -1;
  let lastHexZoomKey = '';
  /** @type {ReturnType<typeof setTimeout> | null} */
  let zoomUpdateTimer = null;
  let mapError = '';
  let reducedMotion = false;
  let overlayShown = true;
  let overlayFade = false;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let overlayFadeTimer = null;
  let autoRotate = true;
  let resumeTimer = null;
  let rotateRaf = null;
  /** @type {ResizeObserver | null} */
  let resizeObserver = null;
  const AUTO_ROTATE_DEG_PER_FRAME = 0.012;
  const AUTO_ROTATE_RESUME_MS = 5000;
  /** Below this zoom the view is globe-like; above it MapLibre flattens toward mercator. */
  const GLOBE_VIEW_MAX_ZOOM = 5.5;
  /** Keep selected realm hexes clear of fixed header / KPI chrome. */
  const REALM_FIT_PADDING = { top: 88, bottom: 64, left: 48, right: 48 };
  const MAP_SHELL_INSET_MS = 280;

  // Realms prop is already filtered by search; never dim the globe while typing.
  $: matchingRealmIds = null;
  $: dimNonMatching = false;

  function emptyFeatureCollection() {
    return { type: 'FeatureCollection', features: [] };
  }

  function polygonsToGeoJSON(polygons) {
    return {
      type: 'FeatureCollection',
      features: polygons.map((p) => ({
        type: 'Feature',
        id: p.hexIndex,
        properties: {
          fill: p.fillColor,
          stroke: p.strokeColor,
          opacity: p.opacity,
          weight: p.weight,
          realmId: p.realmIds?.[0] || '',
          hexIndex: p.hexIndex,
        },
        geometry: p.geometry,
      })),
    };
  }

  function translate(key, opts = {}) {
    return get(_)(key, opts);
  }

  function clearHoverPopup() {
    hoveredHexIndex = '';
    hoveredMarkerId = '';
    hoverPopup?.remove();
  }

  function showHoverPopup(lngLat, html) {
    if (!map || !hoverPopup || !html) return;
    const lng = Array.isArray(lngLat) ? lngLat[0] : lngLat?.lng;
    const lat = Array.isArray(lngLat) ? lngLat[1] : lngLat?.lat;
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    hoverPopup.setLngLat([lng, lat]).setHTML(html).addTo(map);
  }

  function attachMarkerHover(el, point) {
    const onEnter = () => {
      if (!map) return;
      hoveredMarkerId = point.realmId;
      hoveredHexIndex = '';
      showHoverPopup(
        [point.lng, point.lat],
        buildMarkerHoverPopupHtml(point, translate)
      );
    };
    const onLeave = () => {
      if (hoveredMarkerId === point.realmId) clearHoverPopup();
    };
    el.addEventListener('mouseenter', onEnter);
    el.addEventListener('mouseleave', onLeave);
    el.addEventListener('focus', onEnter);
    el.addEventListener('blur', onLeave);
  }

  function clearHtmlMarkers() {
    for (const marker of markerById.values()) marker.remove();
    markerById.clear();
  }

  /** @param {string} hex */
  function pinGlowVars(hex) {
    const raw = String(hex || '#22c55e').replace('#', '');
    if (raw.length !== 6) {
      return { r: 34, g: 197, b: 94 };
    }
    return {
      r: parseInt(raw.slice(0, 2), 16),
      g: parseInt(raw.slice(2, 4), 16),
      b: parseInt(raw.slice(4, 6), 16),
    };
  }

  /** @param {HTMLElement} el @param {object} p */
  function styleMarkerElement(el, p) {
    const size = Math.round(12 * (p.size || 1));
    const { r, g, b } = pinGlowVars(p.color);
    el.style.backgroundColor = p.color;
    el.style.width = `${size}px`;
    el.style.height = `${size}px`;
    el.style.setProperty('--pin-r', String(r));
    el.style.setProperty('--pin-g', String(g));
    el.style.setProperty('--pin-b', String(b));
    el.dataset.stage = p.stage || '';
    el.setAttribute('aria-label', p.realmName || p.realmId);
  }

  function syncHtmlMarkers(points) {
    if (!map || !maplibregl) return;
    const seen = new Set();

    for (const p of points) {
      if (!Number.isFinite(p.lat) || !Number.isFinite(p.lng)) continue;
      seen.add(p.realmId);
      let marker = markerById.get(p.realmId);
      const offset = Array.isArray(p.pixelOffset) ? p.pixelOffset : [0, 0];

      if (!marker) {
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'realm-globe-marker';
        styleMarkerElement(el, p);
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          dispatch('select', { realmId: p.realmId });
        });
        attachMarkerHover(el, p);
        marker = new maplibregl.Marker({
          element: el,
          anchor: 'center',
          offset,
          opacity: 1,
          opacityWhenCovered: MARKER_COVERED_OPACITY,
          subpixelPositioning: true,
        })
          .setLngLat([p.lng, p.lat])
          .addTo(map);
        markerById.set(p.realmId, marker);
      } else {
        marker.setLngLat([p.lng, p.lat]);
        marker.setOffset(offset);
        styleMarkerElement(marker.getElement(), p);
      }
    }

    for (const [id, marker] of [...markerById.entries()]) {
      if (seen.has(id)) continue;
      marker.remove();
      markerById.delete(id);
    }
  }

  function ensureLayers() {
    if (!map) return;

    if (!map.getSource(HEX_SOURCE)) {
      // tolerance:0 keeps ~3 km hex edges from being simplified away when
      // overzoomed; high maxzoom keeps geojson-vt tiles available past z12.
      map.addSource(HEX_SOURCE, {
        type: 'geojson',
        data: emptyFeatureCollection(),
        tolerance: 0,
        maxzoom: 22,
      });
    }

    if (!map.getLayer(HEX_FILL)) {
      map.addLayer({
        id: HEX_FILL,
        type: 'fill',
        source: HEX_SOURCE,
        paint: {
          'fill-color': ['get', 'fill'],
          'fill-opacity': ['get', 'opacity'],
        },
      });
    }

    if (!map.getLayer(HEX_LINE)) {
      map.addLayer({
        id: HEX_LINE,
        type: 'line',
        source: HEX_SOURCE,
        paint: {
          'line-color': ['get', 'stroke'],
          'line-width': ['get', 'weight'],
          'line-opacity': 0.85,
        },
      });
    }

    // Keep hex overlays above basemap tiles after projection/style churn.
    try {
      if (map.getLayer(HEX_FILL)) map.moveLayer(HEX_FILL);
      if (map.getLayer(HEX_LINE)) map.moveLayer(HEX_LINE);
    } catch {
      // ignore
    }
  }

  function desiredProjection(zoom = map?.getZoom?.() ?? 0) {
    return zoom >= MERCATOR_PROJECTION_MIN_ZOOM ? 'mercator' : 'globe';
  }

  function syncProjectionForZoom() {
    if (!map) return false;
    const next = desiredProjection();
    try {
      const current = map.getProjection?.()?.type || 'globe';
      if (current === next) return false;
      map.setProjection({ type: next });
      return true;
    } catch {
      try {
        map.setProjection({ type: next });
        return true;
      } catch {
        return false;
      }
    }
  }

  function updateLayers({ force = false } = {}) {
    if (!ready || !map || !h3) return;

    const zoom = map.getZoom();
    const zoomKey = hexDisplayZoomKey(zoom);
    const projectionChanged = syncProjectionForZoom();

    if (!force && !projectionChanged && zoomKey === lastHexZoomKey) {
      return;
    }

    lastHexZoomKey = zoomKey;
    // Projection / style reloads can drop custom sources — always re-bind.
    ensureLayers();
    currentH3Res = h3ResolutionForZoom(zoom);

    const polygons = buildHexPolygons(realms, realmZoneData, h3, {
      matchingRealmIds,
      dimNonMatching,
      zoom,
    });

    const points = buildPointMarkers(realms, realmZoneData, {
      matchingRealmIds,
      dimNonMatching,
      h3,
      h3Resolution: ZONE_DATA_RESOLUTION,
    });

    hexByIndex = new Map(polygons.map((polygon) => [polygon.hexIndex, polygon]));

    const hexSource = map.getSource(HEX_SOURCE);
    if (hexSource) hexSource.setData(polygonsToGeoJSON(polygons));
    syncHtmlMarkers(points);

    // If setProjection deferred a style rebuild, push data again after it settles.
    if (projectionChanged) {
      map.once('idle', () => {
        ensureLayers();
        const src = map.getSource(HEX_SOURCE);
        if (src) src.setData(polygonsToGeoJSON(polygons));
      });
    }
  }

  function onZoomEnd() {
    if (!map) return;
    if (zoomUpdateTimer) clearTimeout(zoomUpdateTimer);
    zoomUpdateTimer = setTimeout(() => {
      zoomUpdateTimer = null;
      updateLayers();
    }, 48);
  }

  function onMapClick(e) {
    if (!map || !map.getLayer(HEX_FILL)) return;
    const hits = map.queryRenderedFeatures(e.point, { layers: [HEX_FILL] });
    const hit = hits.find((f) => f.properties?.realmId);
    if (hit?.properties?.realmId) {
      dispatch('select', { realmId: hit.properties.realmId });
    }
  }

  function pauseAutoRotate() {
    autoRotate = false;
    if (resumeTimer) clearTimeout(resumeTimer);
    resumeTimer = setTimeout(() => {
      if (!reducedMotion && map && map.getZoom() <= GLOBE_VIEW_MAX_ZOOM) {
        autoRotate = true;
      }
    }, AUTO_ROTATE_RESUME_MS);
  }

  function tickRotate() {
    rotateRaf = requestAnimationFrame(tickRotate);
    if (!map || !autoRotate || reducedMotion) return;
    if (map.getZoom() > GLOBE_VIEW_MAX_ZOOM) return;
    const center = map.getCenter();
    map.setCenter([center.lng + AUTO_ROTATE_DEG_PER_FRAME, center.lat]);
  }

  function applyGlobeLook() {
    if (!map) return;
    // Respect zoom: do NOT force globe when zoomed in — that undoes the
    // mercator switch and makes GeoJSON hex fills vanish past ~z12.
    map.setProjection({ type: desiredProjection() });
    // Soft atmosphere that fades as you zoom into regional detail
    try {
      map.setSky?.({
        'atmosphere-blend': [
          'interpolate',
          ['linear'],
          ['zoom'],
          0,
          0.12,
          4,
          0.04,
          6,
          0,
        ],
      });
    } catch {
      // Older builds without sky support
    }
    // Flat, even lighting — no day/night terminator
    try {
      map.setLight?.({
        anchor: 'viewport',
        position: [1.15, 210, 30],
        intensity: 0,
        color: '#ffffff',
      });
    } catch {
      // ignore
    }
  }

  export function flyTo(lat, lng, zoom = 11) {
    if (!map) return;
    pauseAutoRotate();
    map.flyTo({
      center: [lng, lat],
      zoom,
      duration: FLY_TO_MS,
      essential: true,
    });
  }

  /**
   * @param {object} realm
   * @param {{ waitForInset?: boolean }} [opts]
   */
  export function flyToRealm(realm, { waitForInset = false } = {}) {
    const zones = realmZoneData[realm.id]?.zones;
    if (!zones?.length || !map) return;
    pauseAutoRotate();

    const fit = () => {
      if (!map) return;
      map.resize();

      const bounds = h3 ? realmDisplayBounds(zones, h3) : null;

      if (bounds) {
        map.fitBounds(bounds, {
          padding: REALM_FIT_PADDING,
          duration: FLY_TO_MS,
          maxZoom: 13,
          essential: true,
        });
        return;
      }

      const capital = resolveCapitalZone(zones);
      if (!capital) return;
      const center = capitalHexCenter(capital, h3, currentH3Res || ZONE_DATA_RESOLUTION);
      flyTo(center.lat, center.lng, 11);
    };

    if (waitForInset) {
      requestAnimationFrame(fit);
      setTimeout(fit, MAP_SHELL_INSET_MS);
      return;
    }

    fit();
  }

  // Comma-op truthiness is unsafe here: empty searchQuery is falsy and skipped repaints.
  $: if (ready) {
    void realms;
    void realmZoneData;
    void searchQuery;
    lastHexZoomKey = '';
    updateLayers({ force: true });
  }

  $: needsLoaderOverlay = !ready || loading;

  $: if (needsLoaderOverlay) {
    overlayShown = true;
    overlayFade = false;
    if (overlayFadeTimer) {
      clearTimeout(overlayFadeTimer);
      overlayFadeTimer = null;
    }
  } else if (overlayShown && !overlayFade) {
    overlayFade = true;
    overlayFadeTimer = setTimeout(() => {
      overlayShown = false;
      overlayFade = false;
      overlayFadeTimer = null;
    }, 420);
  }

  onMount(async () => {
    if (!browser || !container) return;

    reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    try {
      maplibregl = await import('maplibre-gl');
      await import('maplibre-gl/dist/maplibre-gl.css');
      h3 = await import('h3-js');

      const styleRes = await fetch(STYLE_URL);
      if (!styleRes.ok) throw new Error(`Basemap style HTTP ${styleRes.status}`);
      let style = stripPoliticalLayers(await styleRes.json());
      style = softenGlobeBasemap(style, { surfaceOpacity: 0.18, waterDarken: 0.45 });
      style.projection = { type: 'globe' };
      style.sky = {
        'atmosphere-blend': [
          'interpolate',
          ['linear'],
          ['zoom'],
          0,
          0.12,
          4,
          0.04,
          6,
          0,
        ],
      };
      // Even lighting (no terminator); intensity 0 disables directional shade
      style.light = {
        anchor: 'viewport',
        position: [1.15, 210, 30],
        intensity: 0,
        color: '#ffffff',
      };

      const desktop = window.matchMedia('(min-width: 768px)').matches;
      // Higher zoom ⇒ larger planet on screen under globe projection.
      const initialZoom = desktop ? 2.65 : 2.05;

      map = new maplibregl.Map({
        container,
        style,
        center: [10, 18],
        zoom: initialZoom,
        minZoom: desktop ? 1.6 : 1.1,
        maxZoom: 16,
        attributionControl: { compact: true },
        pitchWithRotate: false,
        dragRotate: false,
        canvasContextAttributes: { antialias: true },
      });

      map.addControl(
        new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }),
        'bottom-right'
      );

      map.getCanvas().style.cursor = 'grab';

      map.on('style.load', () => {
        applyGlobeLook();
        if (ready) {
          ensureLayers();
          updateLayers();
        }
      });

      map.on('load', () => {
        applyGlobeLook();
        ensureLayers();
        ready = true;
        updateLayers();
        if (!reducedMotion) {
          autoRotate = true;
          tickRotate();
        }
      });

      map.on('zoom', () => {
        if (syncProjectionForZoom()) {
          // Projection change can drop sources; rebuild immediately.
          ensureLayers();
        }
      });
      map.on('zoomend', onZoomEnd);
      map.on('mousedown', pauseAutoRotate);
      map.on('touchstart', pauseAutoRotate);
      map.on('wheel', pauseAutoRotate);
      map.on('click', onMapClick);

      hoverPopup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        maxWidth: '300px',
        className: 'realm-hover-popup',
        offset: 18,
      });

      map.on('mousemove', HEX_FILL, (e) => {
        if (!map || !hoverPopup) return;
        const hit = e.features?.find((f) => f.properties?.hexIndex);
        if (!hit?.properties?.hexIndex) return;

        const hexIndex = String(hit.properties.hexIndex);
        map.getCanvas().style.cursor = 'pointer';

        if (hexIndex !== hoveredHexIndex) {
          hoveredHexIndex = hexIndex;
          hoveredMarkerId = '';
          const polygon = hexByIndex.get(hexIndex);
          if (polygon) {
            showHoverPopup(e.lngLat, buildHexHoverPopupHtml(polygon, translate));
          }
        } else {
          hoverPopup.setLngLat(e.lngLat);
        }
      });

      map.on('mouseenter', HEX_FILL, () => {
        if (map) map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', HEX_FILL, () => {
        if (map) map.getCanvas().style.cursor = 'grab';
        clearHoverPopup();
      });

      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(() => {
          map?.resize();
        });
        resizeObserver.observe(container);
      }
    } catch (err) {
      console.error('Map init failed', err);
      mapError = err?.message || 'Failed to load map';
    }

    return () => {
      if (overlayFadeTimer) clearTimeout(overlayFadeTimer);
      resizeObserver?.disconnect();
      resizeObserver = null;
      if (resumeTimer) clearTimeout(resumeTimer);
      if (rotateRaf) cancelAnimationFrame(rotateRaf);
      clearHoverPopup();
      hoverPopup = null;
      clearHtmlMarkers();
      map?.remove();
      map = null;
    };
  });

  onDestroy(() => {
    if (overlayFadeTimer) clearTimeout(overlayFadeTimer);
    if (zoomUpdateTimer) clearTimeout(zoomUpdateTimer);
    resizeObserver?.disconnect();
    resizeObserver = null;
    if (resumeTimer) clearTimeout(resumeTimer);
    if (rotateRaf) cancelAnimationFrame(rotateRaf);
    clearHoverPopup();
    hoverPopup = null;
    clearHtmlMarkers();
    map?.remove();
    map = null;
  });
</script>

<div
  class="map-view"
  data-tour="globe"
  style="background: {MAP_BG}"
  aria-label={$_('globe.aria_label')}
  bind:this={container}
>
  {#if overlayShown}
    <div class="map-loading" class:fade-out={overlayFade} aria-busy={!overlayFade}>
      <GlobeWireframeLoader size={64} />
    </div>
  {/if}
  {#if mapError}
    <div class="map-error">{mapError}</div>
  {/if}
</div>

<style>
  .map-view {
    position: absolute;
    inset: 0;
    overflow: hidden;
  }

  .map-view :global(.maplibregl-map) {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }

  .map-view :global(.maplibregl-ctrl-group) {
    border: 1px solid var(--border, #e5e5e5);
    box-shadow: none;
    border-radius: 8px;
    overflow: hidden;
  }

  .map-view :global(.maplibregl-ctrl-group button) {
    width: 32px;
    height: 32px;
  }

  .map-view :global(.maplibregl-ctrl-attrib) {
    font-size: 10px;
    background: rgba(250, 250, 250, 0.85);
  }

  .map-view :global(.maplibregl-ctrl-scale) {
    margin: 0 12px 28px 0;
    border-color: #a3a3a3;
    border-width: 1px 1px 2px;
    background: rgba(250, 250, 250, 0.72);
    color: #737373;
    font-size: 10px;
    font-family: var(--font-family, inherit);
    height: 14px;
    line-height: 12px;
    padding: 0 4px;
    border-radius: 2px;
  }

  @media (max-width: 767px) {
    .map-view :global(.maplibregl-ctrl-attrib),
    .map-view :global(.maplibregl-ctrl-scale) {
      display: none !important;
    }
  }

  /* Realm pins — stage-colored + glow; DOM so far-side ones show through */
  .map-view :global(.realm-globe-marker) {
    --pin-r: 34;
    --pin-g: 197;
    --pin-b: 94;
    display: block;
    padding: 0;
    border: 2px solid rgba(255, 255, 255, 0.95);
    border-radius: 50%;
    background-color: rgb(var(--pin-r), var(--pin-g), var(--pin-b));
    box-shadow:
      0 0 6px 2px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.95),
      0 0 14px 5px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.55),
      0 0 28px 10px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.28);
    cursor: pointer;
    transform: translateZ(0);
    animation: pin-glow 2.4s ease-in-out infinite;
  }

  .map-view :global(.realm-globe-marker.maplibregl-marker-covered) {
    animation: none;
    box-shadow:
      0 0 4px 1px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.55),
      0 0 10px 3px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.28);
    cursor: pointer;
  }

  .map-view :global(.realm-globe-marker:hover),
  .map-view :global(.realm-globe-marker:focus-visible) {
    animation: none;
    box-shadow:
      0 0 8px 3px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 1),
      0 0 18px 7px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.7),
      0 0 36px 14px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.35);
    outline: none;
  }

  @keyframes pin-glow {
    0%,
    100% {
      box-shadow:
        0 0 6px 2px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.95),
        0 0 14px 5px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.55),
        0 0 28px 10px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.28);
    }
    50% {
      box-shadow:
        0 0 8px 3px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 1),
        0 0 20px 8px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.7),
        0 0 36px 14px rgba(var(--pin-r), var(--pin-g), var(--pin-b), 0.4);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .map-view :global(.realm-globe-marker) {
      animation: none;
    }
  }

  .map-view :global(.realm-hover-popup .maplibregl-popup-content) {
    padding: 0;
    background: transparent;
    box-shadow: none;
    pointer-events: none;
  }

  .map-view :global(.realm-hover-popup .maplibregl-popup-tip) {
    display: none;
  }

  .map-view :global(.realm-hover-card) {
    min-width: 220px;
    max-width: 280px;
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid rgba(0, 229, 255, 0.28);
    background: rgba(10, 14, 22, 0.94);
    backdrop-filter: blur(14px);
    box-shadow:
      0 10px 28px rgba(0, 0, 0, 0.42),
      0 0 0 1px rgba(255, 255, 255, 0.04) inset,
      0 0 24px rgba(0, 229, 255, 0.12);
    color: #e8edf5;
    font-family: var(--font-family, inherit);
    line-height: 1.45;
  }

  .map-view :global(.realm-hover-header) {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
  }

  .map-view :global(.realm-hover-title) {
    margin: 0;
    font-size: 0.9375rem;
    font-weight: 600;
    color: #f8fafc;
    letter-spacing: -0.01em;
  }

  .map-view :global(.realm-hover-stage) {
    flex-shrink: 0;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.625rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .map-view :global(.realm-hover-locations) {
    margin-bottom: 6px;
    font-size: 0.75rem;
    color: #94a3b8;
  }

  .map-view :global(.realm-hover-stat) {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    font-size: 0.75rem;
    color: #cbd5e1;
  }

  .map-view :global(.realm-hover-stat.muted) {
    color: #94a3b8;
  }

  .map-view :global(.realm-hover-stat-icon) {
    color: #00e5ff;
    font-size: 0.5rem;
  }

  .map-view :global(.realm-hover-influence) {
    margin-bottom: 6px;
    font-size: 0.6875rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #67e8f9;
  }

  .map-view :global(.realm-hover-manifesto) {
    margin: 8px 0 0;
    padding-top: 8px;
    border-top: 1px solid rgba(148, 163, 184, 0.18);
    font-size: 0.75rem;
    color: #94a3b8;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .map-view :global(.realm-hover-footer) {
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid rgba(0, 229, 255, 0.14);
    font-size: 0.6875rem;
    font-weight: 500;
    letter-spacing: 0.02em;
    color: #67e8f9;
  }

  .map-loading,
  .map-error {
    position: absolute;
    inset: 0;
    z-index: 2;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    pointer-events: none;
    color: var(--text-tertiary, #737373);
    font-size: 0.8125rem;
  }

  .map-loading {
    background: rgba(250, 250, 250, 0.72);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    opacity: 1;
    transition: opacity 0.42s ease-out;
  }

  .map-loading.fade-out {
    opacity: 0;
    pointer-events: none;
  }

  @media (prefers-reduced-motion: reduce) {
    .map-loading {
      transition: none;
    }

    .map-loading.fade-out {
      display: none;
    }
  }

  .map-error {
    color: #b91c1c;
    background: rgba(250, 250, 250, 0.9);
    pointer-events: auto;
    padding: 1rem;
    text-align: center;
  }
</style>
