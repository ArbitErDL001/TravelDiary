(() => {
  const mapElement = document.querySelector("[data-place-map]");
  const confirmButton = document.querySelector("[data-place-map-confirm]");
  const clearButton = document.querySelector("[data-place-map-clear]");
  const status = document.querySelector("[data-place-map-status]");
  const confirmation = document.querySelector("[data-place-confirmation]");
  const placeInput = document.querySelector("#memory-place");
  const searchInput = document.querySelector("#memory-place-search");
  const nameInput = document.querySelector("#id_new_place-name");
  const addressInput = document.querySelector("#id_new_place-address");
  const latitudeInput = document.querySelector("#id_new_place-latitude");
  const longitudeInput = document.querySelector("#id_new_place-longitude");
  if (!mapElement || !confirmButton || !clearButton || !status || !confirmation || !placeInput || !searchInput ||
      !nameInput || !addressInput || !latitudeInput || !longitudeInput) return;

  let map;
  let marker;
  let reverseLookup;
  let resizeObserver;

  const coordinatesFromInputs = () => {
    const latitude = Number(latitudeInput.value);
    const longitude = Number(longitudeInput.value);
    if (!latitudeInput.value || !longitudeInput.value || !Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
    return [latitude, longitude];
  };

  const showMarker = (latitude, longitude, focus = false) => {
    const position = [latitude, longitude];
    if (!marker) {
      marker = window.L.marker(position, {draggable: true}).addTo(map);
      marker.on("dragend", () => selectLocation(marker.getLatLng()));
    } else {
      marker.setLatLng(position);
    }
    if (focus) map.setView(position, Math.max(map.getZoom(), 14));
  };

  const selectLocation = async (position, fromSearch = false) => {
    const latitude = Number(position.lat.toFixed(6));
    const longitude = Number(position.lng.toFixed(6));
    if (!fromSearch) {
      searchInput.value = "";
      delete searchInput.dataset.locationSelected;
    }
    latitudeInput.value = latitude.toFixed(6);
    longitudeInput.value = longitude.toFixed(6);
    placeInput.value = "";
    nameInput.value = "Pinned location";
    addressInput.value = "";
    confirmButton.disabled = true;
    confirmation.textContent = `Selected point: ${latitude.toFixed(6)}, ${longitude.toFixed(6)}. Looking up its location…`;
    confirmation.hidden = false;
    showMarker(latitude, longitude, fromSearch);

    if (reverseLookup) reverseLookup.abort();
    reverseLookup = new AbortController();
    status.textContent = "Pin saved. Looking up the place name and address…";

    try {
      const query = new URLSearchParams({latitude: latitude.toFixed(6), longitude: longitude.toFixed(6)});
      const response = await fetch(`/api/reverse-geocode/?${query}`, {
        headers: {"Accept": "application/json"},
        signal: reverseLookup.signal,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Address lookup is unavailable.");
      nameInput.value = (result.name || result.address || "Pinned location").slice(0, 180);
      addressInput.value = (result.address || "").slice(0, 255);
      confirmation.textContent = `${nameInput.value}${addressInput.value ? ` — ${addressInput.value}` : ""}`;
      status.textContent = result.address
        ? "Place name and address filled in. Confirm this location to attach it to your memory."
        : "Pin saved. Confirm this location to use its coordinates.";
    } catch (error) {
      if (error.name === "AbortError") return;
      confirmation.textContent = `Pinned location: ${nameInput.value} (${latitude.toFixed(6)}, ${longitude.toFixed(6)})`;
      status.textContent = `Pin saved, but address lookup failed. Confirm to use its coordinates. ${error.message}`;
    } finally {
      if (latitudeInput.value === latitude.toFixed(6) && longitudeInput.value === longitude.toFixed(6)) {
        confirmButton.disabled = false;
      }
    }
  };

  const initializeMap = () => {
    if (!window.L) {
      status.textContent = "The map could not load. Reload the page to try again.";
      return;
    }
    const worldBounds = window.L.latLngBounds([[-85.051129, -180], [85.051129, 180]]);
    map = window.L.map(mapElement, {
      zoomControl: false,
      minZoom: 2,
      scrollWheelZoom: true,
      worldCopyJump: false,
      maxBounds: worldBounds,
      maxBoundsViscosity: 1,
    }).setView([20, 0], 2);
    const updateDragging = () => {
      if (map.getZoom() > map.getMinZoom()) map.dragging.enable();
      else map.dragging.disable();
    };
    map.on("zoomend", updateDragging);
    updateDragging();
    window.L.control.zoom({position: "topright"}).addTo(map);
    const L = window.L;
    const mapTilerApiKey = mapElement.dataset.maptilerApiKey;
    if (mapTilerApiKey) {
      const tiles = `https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=${encodeURIComponent(mapTilerApiKey)}`;
      L.tileLayer(tiles, {
        noWrap: true,
        bounds: worldBounds,
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.maptiler.com/copyright/" target="_blank">MapTiler</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>'
      }).addTo(map);
    } else {
      status.textContent = "MapTiler tiles are not configured. Set MAPTILER_API_KEY to load the map.";
    }
    map.on("click", (event) => selectLocation(event.latlng));
    const coordinates = coordinatesFromInputs();
    if (coordinates) {
      showMarker(coordinates[0], coordinates[1], true);
      if (placeInput.value === "__new__" && nameInput.value.trim()) {
        confirmButton.disabled = false;
        confirmation.textContent = `Location confirmed: ${nameInput.value}${addressInput.value ? ` — ${addressInput.value}` : ""}`;
        confirmation.hidden = false;
        status.textContent = "Location confirmed. Click the map to choose a different pin.";
      } else {
        selectLocation({lat: coordinates[0], lng: coordinates[1]}, true);
      }
    }
    const refreshMapSize = () => window.requestAnimationFrame(() => map.invalidateSize({pan: false}));
    if ("ResizeObserver" in window) {
      resizeObserver = new ResizeObserver(refreshMapSize);
      resizeObserver.observe(mapElement);
    }
    window.addEventListener("resize", refreshMapSize, {passive: true});
    refreshMapSize();
  };

  confirmButton.addEventListener("click", () => {
    if (!coordinatesFromInputs()) return;
    placeInput.value = "__new__";
    confirmation.textContent = `Location confirmed: ${nameInput.value}${addressInput.value ? ` — ${addressInput.value}` : ""}`;
    confirmation.hidden = false;
    status.textContent = "Location confirmed. It will be attached to your memory.";
  });

  searchInput.addEventListener("input", () => {
    if (reverseLookup) reverseLookup.abort();
    if (marker) {
      map.removeLayer(marker);
      marker = null;
    }
    placeInput.value = "";
    nameInput.value = "";
    addressInput.value = "";
    latitudeInput.value = "";
    longitudeInput.value = "";
    confirmButton.disabled = true;
    confirmation.hidden = true;
    status.textContent = "Choose a search result to jump to it, or pin a location on the map.";
  });

  searchInput.addEventListener("change", () => {
    const coordinates = coordinatesFromInputs();
    if (!coordinates) return;
    selectLocation({lat: coordinates[0], lng: coordinates[1]}, true);
  });

  clearButton.addEventListener("click", () => {
    if (reverseLookup) reverseLookup.abort();
    if (marker) {
      map.removeLayer(marker);
      marker = null;
    }
    placeInput.value = "";
    searchInput.value = "";
    delete searchInput.dataset.locationSelected;
    nameInput.value = "";
    addressInput.value = "";
    latitudeInput.value = "";
    longitudeInput.value = "";
    confirmButton.disabled = true;
    confirmation.hidden = true;
    status.textContent = "Click the map to choose a location.";
  });

  initializeMap();
})();
