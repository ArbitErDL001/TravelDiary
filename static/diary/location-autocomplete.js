(() => {
  const pendingRequests = new WeakMap();
  const countryCodes = {
    US: "USA", CA: "CAN", MX: "MEX", BR: "BRA", AR: "ARG", CL: "CHL", PE: "PER", CR: "CRI",
    GB: "GBR", FR: "FRA", IT: "ITA", ES: "ESP", PT: "PRT", DE: "DEU", AT: "AUT", CH: "CHE",
    NL: "NLD", BE: "BEL", CZ: "CZE", HR: "HRV", GR: "GRC", IS: "ISL", IE: "IRL", NO: "NOR",
    SE: "SWE", TR: "TUR", MA: "MAR", EG: "EGY", ZA: "ZAF", KE: "KEN", TZ: "TZA", AE: "ARE",
    JO: "JOR", IN: "IND", NP: "NPL", LK: "LKA", TH: "THA", VN: "VNM", KH: "KHM", MY: "MYS",
    ID: "IDN", PH: "PHL", KR: "KOR", CN: "CHN", SG: "SGP", JP: "JPN", AU: "AUS", NZ: "NZL",
  };
  const featuresByButton = new WeakMap();

  function getSuggestions(input) {
    const container = input.closest("[data-location-container]") || input.closest("p") || input.parentElement;
    let suggestions = container.querySelector("[data-location-suggestions]");
    if (!suggestions) {
      suggestions = document.createElement("div");
      suggestions.className = "location-suggestions";
      suggestions.dataset.locationSuggestions = "";
      suggestions.setAttribute("role", "listbox");
      input.insertAdjacentElement("afterend", suggestions);
    }
    if (!suggestions.id) {
      suggestions.id = `${input.id || "location-input"}-suggestions`;
      input.setAttribute("aria-controls", suggestions.id);
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("autocomplete", "off");
    }
    return suggestions;
  }

  function setTarget(input, dataKey, value) {
    const selector = input.dataset[dataKey];
    if (!selector) return;
    const target = document.querySelector(selector);
    if (target) target.value = value;
  }

  function selectedCountryCode(feature) {
    const alpha2 = (feature.country_code || "").toUpperCase();
    return countryCodes[alpha2] || alpha2;
  }

  function locationLabel(feature) {
    return [feature.city, feature.state, feature.country].filter(Boolean).join(", ");
  }

  function normalize(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function matchesQuery(input, feature, query) {
    const needle = normalize(query);
    const terms = needle.split(/\s+/).filter(Boolean);
    const country = normalize(feature.country);
    const locality = normalize([feature.city, feature.state].filter(Boolean).join(" "));
    if (input.dataset.locationAutocomplete === "country") {
      return country.includes(needle) || terms.every((term) => locality.includes(term));
    }
    const resultText = normalize([feature.name, feature.city, feature.state, feature.country].filter(Boolean).join(" "));
    return terms.every((term) => resultText.includes(term));
  }

  function renderSuggestions(input, features, query) {
    const suggestions = getSuggestions(input);
    suggestions.replaceChildren();
    const validFeatures = features.filter((feature) => {
      const coordinates = feature.coordinates || [];
      return feature.name && feature.country_code &&
        Number.isFinite(Number(coordinates[0])) && Number.isFinite(Number(coordinates[1])) &&
        matchesQuery(input, feature, query);
    });
    validFeatures.forEach((feature) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "location-suggestion";
      button.dataset.locationSuggestion = "";
      button.setAttribute("role", "option");
      const copy = document.createElement("span");
      const title = document.createElement("strong");
      const detail = document.createElement("small");
      const code = document.createElement("span");
      const mode = input.dataset.locationAutocomplete;
      title.textContent = mode === "country" ? (feature.country || feature.name) :
        mode === "region" ? (feature.state || feature.city || feature.name) : feature.name;
      detail.textContent = locationLabel(feature);
      code.className = "location-suggestion-code";
      code.textContent = selectedCountryCode(feature);
      copy.append(title, detail);
      button.append(copy, code);
      featuresByButton.set(button, feature);
      suggestions.append(button);
    });
    suggestions.hidden = validFeatures.length === 0;
    input.setAttribute("aria-expanded", String(validFeatures.length > 0));
    if (!validFeatures.length) {
      const status = document.createElement("small");
      status.className = "location-suggestion-status";
      status.textContent = "No matching locations. Try a nearby city or a longer search.";
      suggestions.append(status);
      suggestions.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
  }

  function applySuggestion(input, feature) {
    const mode = input.dataset.locationAutocomplete;
    const address = locationLabel(feature);
    const coordinates = feature.coordinates;
    if (mode === "country") {
      input.value = feature.country || feature.name;
      setTarget(input, "locationCodeTarget", selectedCountryCode(feature));
    } else if (mode === "region") {
      input.value = feature.state || feature.city || feature.name;
      const countrySelect = document.querySelector(input.dataset.locationCountryTarget);
      if (countrySelect && feature.country) {
        const option = [...countrySelect.options].find(
          (item) => item.textContent.trim().toLowerCase() === feature.country.toLowerCase(),
        );
        if (option) {
          countrySelect.value = option.value;
          countrySelect.dispatchEvent(new Event("change", {bubbles: true}));
        }
      }
    } else {
      input.value = mode === "address" ? address : feature.name;
      if (mode !== "address") setTarget(input, "locationAddressTarget", address);
      setTarget(input, "locationLatitudeTarget", coordinates[1]);
      setTarget(input, "locationLongitudeTarget", coordinates[0]);
    }
    input.dataset.locationSelected = "true";
    input.dispatchEvent(new Event("change", {bubbles: true}));
    const suggestions = getSuggestions(input);
    suggestions.replaceChildren();
    suggestions.hidden = true;
    input.setAttribute("aria-expanded", "false");
  }

  document.addEventListener("input", (event) => {
    const input = event.target.closest("[data-location-autocomplete]");
    if (!input) return;
    const oldRequest = pendingRequests.get(input);
    if (oldRequest) {
      clearTimeout(oldRequest.timer);
      oldRequest.controller.abort();
    }
    const suggestions = getSuggestions(input);
    suggestions.replaceChildren();
    const mode = input.dataset.locationAutocomplete;
    if (mode === "country") setTarget(input, "locationCodeTarget", "");
    if ((mode === "place" || mode === "address") && input.dataset.locationSelected === "true") {
      setTarget(input, "locationAddressTarget", "");
      setTarget(input, "locationLatitudeTarget", "");
      setTarget(input, "locationLongitudeTarget", "");
      delete input.dataset.locationSelected;
    }
    const query = input.value.trim();
    if (query.length < 2) {
      suggestions.hidden = true;
      input.setAttribute("aria-expanded", "false");
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({q: query});
        if (mode === "country") params.set("kind", "country");
        const response = await fetch(`/api/photon/?${params}`, {signal: controller.signal});
        if (!response.ok) throw new Error("Location suggestions are temporarily unavailable.");
        const data = await response.json();
        if (input.value.trim() === query) renderSuggestions(input, data.features || [], query);
      } catch (error) {
        if (error.name === "AbortError") return;
        suggestions.replaceChildren();
        const status = document.createElement("small");
        status.className = "location-suggestion-status";
        status.textContent = error.message || "Location suggestions are temporarily unavailable.";
        suggestions.append(status);
        suggestions.hidden = false;
        input.setAttribute("aria-expanded", "true");
      }
    }, 280);
    pendingRequests.set(input, {controller, timer});
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-location-suggestion]");
    if (button) {
      const input = button.closest("[data-location-suggestions]")?.parentElement
        ?.querySelector("[data-location-autocomplete]") ||
        document.querySelector(`[aria-controls="${button.closest("[data-location-suggestions]")?.id}"]`);
      const feature = featuresByButton.get(button);
      if (input && feature) applySuggestion(input, feature);
      return;
    }
    if (event.target.closest("[data-location-autocomplete]")) return;
    document.querySelectorAll("[data-location-suggestions]:not([hidden])").forEach((suggestions) => {
      suggestions.hidden = true;
      const controlledInput = document.querySelector(`[aria-controls="${suggestions.id}"]`);
      controlledInput?.setAttribute("aria-expanded", "false");
    });
  });
})();
