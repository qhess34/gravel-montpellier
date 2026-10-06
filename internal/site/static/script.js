(function () {
  "use strict";

  function ensureModal() {
    var modal = document.getElementById("gm-modal");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "gm-modal";
    modal.className = "gm-modal";
    modal.innerHTML =
      '<div class="gm-modal-backdrop"></div>' +
      '<div class="gm-modal-body"></div>' +
      '<button type="button" class="gm-modal-close" aria-label="Fermer">&times;</button>';
    document.body.appendChild(modal);

    modal.querySelector(".gm-modal-backdrop").addEventListener("click", closeModal);
    modal.querySelector(".gm-modal-close").addEventListener("click", closeModal);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeModal();
    });

    return modal;
  }

  function openModal(contentEl) {
    var modal = ensureModal();
    var body = modal.querySelector(".gm-modal-body");
    body.innerHTML = "";
    body.appendChild(contentEl);
    modal.classList.add("gm-modal--open");
    document.body.classList.add("gm-modal-lock");
  }

  function closeModal() {
    var modal = document.getElementById("gm-modal");
    if (!modal) return;
    modal.classList.remove("gm-modal--open");
    document.body.classList.remove("gm-modal-lock");
    modal.querySelector(".gm-modal-body").innerHTML = "";
  }

  // Affiche une photo en grand, avec légende optionnelle.
  window.gmOpenPhoto = function (src, caption) {
    var wrap = document.createElement("div");
    wrap.className = "gm-lightbox";

    var img = document.createElement("img");
    img.src = src;
    img.alt = caption || "";
    wrap.appendChild(img);

    if (caption) {
      var cap = document.createElement("p");
      cap.className = "gm-lightbox-caption";
      cap.textContent = caption;
      wrap.appendChild(cap);
    }

    openModal(wrap);
  };

  // Ouvre la visionneuse Panoramax (composant web officiel @panoramax/web-viewer)
  // pointant sur une photo précise.
  // Parcourt layer et tous ses sous-calques (récursif) pour appliquer
  // callback à chaque Polyline trouvée — nécessaire car L.GPX imbrique
  // parfois la trace réelle dans des sous-groupes (par segment), qu'un
  // simple eachLayer non récursif sur la couche du dessus ne voit pas.
  window.gmEachPolyline = function (layer, callback) {
    if (layer instanceof L.Polyline) {
      callback(layer);
    }
    if (typeof layer.eachLayer === "function") {
      layer.eachLayer(function (child) {
        window.gmEachPolyline(child, callback);
      });
    }
  };

  // Visionneuse Panoramax : même principe que le userscript
  // tampermonkey-komoot-panoramax — une grande fenêtre en superposition
  // (bandeau « Panoramax » + ✕) qui affiche dans une iframe l'interface web
  // officielle de Panoramax, centrée sur la photo (?focus=pic&pic=<id>).
  // Fermeture : ✕, Échap ou clic à côté de la fenêtre.
  var gmPanoramaxPopup = null;
  var gmPanoramaxReturnFocus = null;

  // URL de l'interface web d'une instance à partir de son API
  // (https://api.panoramax.xyz/api -> https://api.panoramax.xyz/).
  function gmPanoramaxViewerURL(endpoint, picture) {
    var base = (endpoint || "https://api.panoramax.xyz/api").replace(/\/+$/, "").replace(/\/api$/, "");
    return base + "/?focus=pic&pic=" + encodeURIComponent(picture);
  }

  function gmClosePanoramax() {
    if (!gmPanoramaxPopup) return;
    gmPanoramaxPopup.remove();
    gmPanoramaxPopup = null;
    document.body.classList.remove("gm-modal-lock");
    if (gmPanoramaxReturnFocus && gmPanoramaxReturnFocus.focus) gmPanoramaxReturnFocus.focus();
    gmPanoramaxReturnFocus = null;
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") gmClosePanoramax();
  });

  // sequence est conservé dans la signature (points.md le fournit) mais
  // l'interface web retrouve la séquence à partir de la photo seule.
  window.gmOpenPanoramax = function (endpoint, sequence, picture, label) {
    gmClosePanoramax();
    var url = gmPanoramaxViewerURL(endpoint, picture);
    gmPanoramaxReturnFocus = document.activeElement;

    var popup = document.createElement("div");
    popup.id = "panoramax-popup";
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-modal", "true");
    popup.setAttribute("aria-label", "Vue 360° Panoramax" + (label ? " — " + label : ""));

    var overlay = document.createElement("div");
    overlay.className = "pmx-overlay";

    var header = document.createElement("div");
    header.className = "pmx-header";
    var title = document.createElement("span");
    title.className = "pmx-title";
    title.textContent = "Panoramax" + (label ? " · " + label : "");
    var actions = document.createElement("span");
    actions.className = "pmx-actions";
    var open = document.createElement("a");
    open.href = url;
    open.target = "_blank";
    open.rel = "noopener noreferrer";
    open.textContent = "↗";
    open.title = "Ouvrir dans Panoramax (nouvel onglet)";
    open.setAttribute("aria-label", "Ouvrir dans Panoramax (nouvel onglet)");
    var close = document.createElement("button");
    close.type = "button";
    close.textContent = "✕";
    close.setAttribute("aria-label", "Fermer la vue Panoramax");
    close.addEventListener("click", gmClosePanoramax);
    actions.appendChild(open);
    actions.appendChild(close);
    header.appendChild(title);
    header.appendChild(actions);

    var iframe = document.createElement("iframe");
    iframe.src = url;
    iframe.title = "Visionneuse Panoramax";
    iframe.setAttribute("allowfullscreen", "");
    iframe.setAttribute("allow", "fullscreen; geolocation");

    overlay.appendChild(header);
    overlay.appendChild(iframe);
    popup.appendChild(overlay);
    popup.addEventListener("click", function (e) {
      if (e.target === popup) gmClosePanoramax();
    });

    document.body.appendChild(popup);
    document.body.classList.add("gm-modal-lock");
    gmPanoramaxPopup = popup;
    close.focus();
  };

  // Clic sur la trace : si une vue Panoramax existe à proximité du point
  // cliqué, affiche une popup avec un bouton pour l'ouvrir directement.
  var GM_PANORAMAX_DEFAULT_ENDPOINT = "https://api.panoramax.xyz/api";

  function gmDistMeters(lat1, lon1, lat2, lon2) {
    var R = 6371000;
    var toRad = function (d) { return (d * Math.PI) / 180; };
    var dLat = toRad(lat2 - lat1);
    var dLon = toRad(lon2 - lon1);
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function gmPanoramaxLoadingContent() {
    var wrap = document.createElement("div");
    wrap.className = "gm-track-panoramax-popup gm-track-panoramax-popup--loading";
    wrap.textContent = "Recherche d'une vue 360°…";
    return wrap;
  }

  function gmFormatDate(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
  }

  // Popup « vue 360° » : miniature de la photo (si connue), date de prise de
  // vue, distance au point cliqué, et bouton pour ouvrir la visionneuse.
  // info : { label, endpoint, sequence, picture, thumb, date, dist }.
  function gmPanoramaxButtonContent(info) {
    var wrap = document.createElement("div");
    wrap.className = "gm-track-panoramax-popup";
    var open = function () {
      window.gmOpenPanoramax(info.endpoint, info.sequence, info.picture, info.label);
    };

    if (info.thumb) {
      var thumb = document.createElement("button");
      thumb.type = "button";
      thumb.className = "gm-pano-thumb";
      thumb.setAttribute("aria-label", "Ouvrir la vue 360°");
      var img = document.createElement("img");
      img.src = info.thumb;
      img.alt = "";
      img.loading = "lazy";
      img.onerror = function () { thumb.remove(); };
      thumb.appendChild(img);
      var badge = document.createElement("span");
      badge.className = "gm-pano-badge";
      badge.textContent = "360°";
      thumb.appendChild(badge);
      thumb.addEventListener("click", open);
      wrap.appendChild(thumb);
    }

    if (info.label) {
      var title = document.createElement("strong");
      title.className = "gm-pano-title";
      title.textContent = info.label;
      wrap.appendChild(title);
    }
    var meta = [];
    if (info.date) meta.push("Photo du " + gmFormatDate(info.date));
    if (typeof info.dist === "number") meta.push("à " + Math.round(info.dist) + " m");
    if (meta.length) {
      var m = document.createElement("span");
      m.className = "gm-pano-meta";
      m.textContent = meta.join(" · ");
      wrap.appendChild(m);
    }

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "gm-track-panoramax-btn";
    btn.textContent = "🧭 Voir en 360°";
    btn.addEventListener("click", open);
    wrap.appendChild(btn);
    return wrap;
  }

  function gmPanoramaxEmptyContent() {
    var wrap = document.createElement("div");
    wrap.className = "gm-track-panoramax-popup gm-track-panoramax-popup--empty";
    wrap.textContent = "Pas encore de photo 360° à cet endroit.";
    return wrap;
  }

  function gmPanoramaxFeature(f, lat, lon) {
    var coords = f.geometry && f.geometry.coordinates;
    if (!coords) return null;
    var assets = f.assets || {};
    return {
      picture: f.id,
      sequence: f.collection,
      lat: coords[1],
      lon: coords[0],
      thumb: (assets.thumb && assets.thumb.href) || "",
      date: (f.properties && f.properties.datetime) || "",
      dist: lat === undefined ? undefined : gmDistMeters(lat, lon, coords[1], coords[0]),
    };
  }

  // Cherche la photo Panoramax la plus proche de (lat, lon), comme le
  // userscript tampermonkey-komoot-panoramax : photos qui « voient » le
  // point (place_position, toutes orientations) dans un rayon de radiusM.
  // Si l'instance ne gère pas cette recherche, repli sur un filtre bbox.
  // Renvoie une promesse : {picture, sequence, lat, lon, thumb, date, dist}
  // ou null (rien à proximité, ou erreur réseau).
  window.gmFindNearestPanoramax = function (lat, lon, radiusM, endpoint) {
    var base = endpoint.replace(/\/$/, "") + "/search?";
    var byPosition = base + "place_position=" + lon + "," + lat +
      "&place_fov_tolerance=180&place_distance=0-" + Math.round(radiusM) + "&sortby=-ts&limit=50";
    var dLat = radiusM / 111320;
    var dLon = radiusM / (111320 * Math.cos((lat * Math.PI) / 180));
    var byBbox = base + "bbox=" + encodeURIComponent([lon - dLon, lat - dLat, lon + dLon, lat + dLat].join(",")) + "&limit=20";

    function nearest(data) {
      var best = null;
      ((data && data.features) || []).forEach(function (f) {
        var c = gmPanoramaxFeature(f, lat, lon);
        if (c && c.dist <= radiusM * 1.5 && (!best || c.dist < best.dist)) best = c;
      });
      return best;
    }

    return fetch(byPosition)
      .then(function (r) {
        if (r.ok) return r.json().then(nearest);
        return fetch(byBbox).then(function (r2) { return r2.ok ? r2.json().then(nearest) : null; });
      })
      .catch(function () { return null; });
  };

  // Miniature et date d'une photo connue par son identifiant (points.md).
  window.gmPanoramaxPreview = function (endpoint, picture) {
    return fetch(endpoint.replace(/\/$/, "") + "/search?ids=" + encodeURIComponent(picture) + "&limit=1")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var f = data && data.features && data.features[0];
        return f ? gmPanoramaxFeature(f) : null;
      })
      .catch(function () { return null; });
  };

  // Clic sur la carte (ou sur le profil) : popup immédiate « recherche… »,
  // puis aperçu de la vue 360° la plus proche avec un bouton pour l'ouvrir,
  // ou un message s'il n'y en a pas. Les points panoramax catalogués dans
  // points.md (à moins de 60 m) sont prioritaires ; à défaut, l'API
  // Panoramax est interrogée en direct (photos à moins de 50 m).
  var gmTrackClickSeq = 0;

  window.gmHandleTrackClick = function (ev, map, panoramaxPoints) {
    var seq = ++gmTrackClickSeq;
    var clickLat = ev.latlng.lat;
    var clickLon = ev.latlng.lng;
    var stale = function (popup) { return seq !== gmTrackClickSeq || !map.hasLayer(popup); };

    var best = null;
    var bestDist = 60; // mètres : ces points sont placés à la main, donc on peut être strict
    (panoramaxPoints || []).forEach(function (p) {
      var d = gmDistMeters(clickLat, clickLon, p.lat, p.lon);
      if (d < bestDist) {
        bestDist = d;
        best = p;
      }
    });
    if (best) {
      var info = { label: best.label, endpoint: best.endpoint, sequence: best.sequence, picture: best.picture, dist: bestDist };
      var known = L.popup({ className: "gm-pano-popup" }).setLatLng([best.lat, best.lon])
        .setContent(gmPanoramaxButtonContent(info)).openOn(map);
      window.gmPanoramaxPreview(best.endpoint, best.picture).then(function (p) {
        if (!p || stale(known)) return;
        info.thumb = p.thumb;
        info.date = p.date;
        known.setContent(gmPanoramaxButtonContent(info));
      });
      return;
    }

    var popup = L.popup({ className: "gm-pano-popup" }).setLatLng(ev.latlng).setContent(gmPanoramaxLoadingContent()).openOn(map);

    window.gmFindNearestPanoramax(clickLat, clickLon, 50, GM_PANORAMAX_DEFAULT_ENDPOINT).then(function (found) {
      // Un clic plus récent a eu lieu, ou la popup a été refermée entre-temps.
      if (stale(popup)) return;
      if (found) {
        found.endpoint = GM_PANORAMAX_DEFAULT_ENDPOINT;
        popup.setContent(gmPanoramaxButtonContent(found));
      } else {
        popup.setContent(gmPanoramaxEmptyContent());
      }
    });
  };

  // Bouton « Visite 360° » sur la carte d'une sortie : rappelle que la trace
  // se parcourt en vues immersives et ouvre la vue la plus proche du départ.
  window.gmInit360Control = function (map, start, panoramaxPoints) {
    if (!map || !window.L) return;
    var Ctl = L.Control.extend({
      options: { position: "topright" },
      onAdd: function () {
        var btn = L.DomUtil.create("button", "gm-360-control");
        btn.type = "button";
        btn.innerHTML = '<span class="gm-360-control-badge" aria-hidden="true">360°</span><span class="gm-360-control-text">Visite immersive<small>Cliquez sur la trace</small></span>';
        btn.setAttribute("aria-label", "Voir le départ en 360° (Panoramax). Cliquez ensuite n'importe où sur la trace.");
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.on(btn, "click", function () {
          if (!start) return;
          var latlng = L.latLng(start[0], start[1]);
          map.setView(latlng, Math.max(map.getZoom(), 14));
          window.gmHandleTrackClick({ latlng: latlng }, map, panoramaxPoints);
        });
        return btn;
      },
    });
    new Ctl().addTo(map);
  };

  // Construit le contenu d'une popup Leaflet pour un point d'intérêt.
  // lat/lon sont optionnels : s'ils sont fournis, un lien discret pour
  // signaler une erreur à cet endroit sur OpenStreetMap est ajouté. km
  // (point kilométrique, ou null) et kindLabel (type de point) sont
  // optionnels aussi.
  window.gmPoiPopup = function (label, note, lat, lon, km, kindLabel) {
    var div = document.createElement("div");
    div.className = "gm-poi-popup";
    var meta = [];
    if (typeof km === "number" && isFinite(km)) meta.push("PK " + km.toFixed(1).replace(".", ",") + " km");
    if (kindLabel) meta.push(kindLabel);
    if (meta.length) {
      var m = document.createElement("span");
      m.className = "gm-poi-popup-meta";
      m.textContent = meta.join(" · ");
      div.appendChild(m);
    }
    var strong = document.createElement("strong");
    strong.textContent = label;
    div.appendChild(strong);
    if (note) {
      var p = document.createElement("p");
      p.textContent = note;
      div.appendChild(p);
    }
    if (lat !== undefined && lon !== undefined) {
      var a = document.createElement("a");
      a.className = "gm-popup-report";
      a.href = "https://www.openstreetmap.org/note/new#map=18/" + lat + "/" + lon + "&layers=N";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "Signaler une erreur sur OpenStreetMap";
      div.appendChild(a);
    }
    return div;
  };

  // Icône de marqueur Leaflet selon le type/style de point (poi, photo, panoramax).
  window.gmIcon = function (kind) {
    return L.divIcon({
      className: "gm-marker gm-marker--" + (kind || "generic"),
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -16],
    });
  };

  // Synchronise le survol du profil altimétrique (SVG) avec un marqueur sur
  // la carte Leaflet, et inversement (survol de la trace -> repère sur le
  // profil). `svg` est le <svg class="elevation-profile"> généré côté
  // serveur (échelle exposée en attributs data-*), `data` un tableau
  // [{km, ele, lat, lon}, ...] le long de la trace.
  // slopes (optionnel) : tronçons [{s, e, p, l}] issus de slope.geojson —
  // kilométrage de début/fin, pente en %, libellé — pour afficher la pente
  // au survol, sur le profil comme sur la carte.
  window.gmInitProfileHover = function (svg, map, data, slopes) {
    if (!svg || !map || !data || !data.length) return;
    slopes = slopes || [];
    var tooltip = svg.parentNode && svg.parentNode.querySelector(".elevation-tooltip");

    var padL = parseFloat(svg.dataset.padL);
    var padTop = parseFloat(svg.dataset.padTop);
    var width = parseFloat(svg.dataset.width);
    var height = parseFloat(svg.dataset.height);
    var chartW = width - padL - parseFloat(svg.dataset.padR);
    var chartH = height - padTop - parseFloat(svg.dataset.padBot);
    var minEle = parseFloat(svg.dataset.minEle);
    var maxEle = parseFloat(svg.dataset.maxEle);
    var totalKm = data[data.length - 1].km;

    function xForKm(km) { return padL + (km / totalKm) * chartW; }
    function yForEle(ele) { return padTop + chartH - ((ele - minEle) / (maxEle - minEle)) * chartH; }

    var guide = svg.querySelector(".elevation-hover-line");
    var dot = svg.querySelector(".elevation-hover-dot");
    var mapMarker = null;

    function ensureMapMarker() {
      if (!mapMarker) {
        mapMarker = L.circleMarker([0, 0], { radius: 7, className: "gm-hover-marker", interactive: false });
        mapMarker.bindTooltip("", { permanent: true, direction: "top", offset: [0, -8], className: "gm-hover-tooltip" });
      }
      return mapMarker;
    }

    function slopeAt(km) {
      for (var i = 0; i < slopes.length; i++) {
        if (km >= slopes[i].s && km <= slopes[i].e) return slopes[i];
      }
      return null;
    }

    function fmt(v, digits) { return v.toFixed(digits).replace(".", ","); }

    // Texte de survol : « PK 12,3 km · ↗ +5,2 % » (pente du tronçon calculée
    // par tools/slope_colors.py ; seulement le PK et l'altitude sans elle).
    function hoverHTML(point) {
      var html = "<strong>PK " + fmt(point.km, 1) + " km</strong>";
      var seg = slopeAt(point.km);
      if (seg && typeof seg.p === "number") {
        var arrow = seg.p >= 2 ? "↗" : seg.p <= -2 ? "↘" : "→";
        html += ' · <span class="gm-hover-slope" style="--slope-color:' + seg.c + '">' + arrow + " " +
          (seg.p > 0 ? "+" : "") + fmt(seg.p, 1) + " %</span>";
      }
      html += '<span class="gm-hover-ele">' + Math.round(point.ele) + " m</span>";
      html += '<span class="gm-hover-hint">clic : vue 360°</span>';
      return html;
    }

    function nearestByKm(km) {
      var best = data[0], bestDiff = Math.abs(best.km - km);
      for (var i = 1; i < data.length; i++) {
        var diff = Math.abs(data[i].km - km);
        if (diff < bestDiff) { best = data[i]; bestDiff = diff; }
      }
      return best;
    }

    function nearestByLatLng(lat, lng) {
      var best = data[0], bestDist = distSq(best, lat, lng);
      for (var i = 1; i < data.length; i++) {
        var d = distSq(data[i], lat, lng);
        if (d < bestDist) { best = data[i]; bestDist = d; }
      }
      return best;
    }

    function distSq(p, lat, lng) {
      var dLat = p.lat - lat, dLng = p.lon - lng;
      return dLat * dLat + dLng * dLng;
    }

    function showAt(point) {
      var gx = xForKm(point.km);
      var gy = yForEle(point.ele);
      if (guide) {
        guide.setAttribute("x1", gx);
        guide.setAttribute("x2", gx);
        guide.style.display = "";
      }
      if (dot) {
        dot.setAttribute("cx", gx);
        dot.setAttribute("cy", gy);
        dot.style.display = "";
      }
      var html = hoverHTML(point);
      ensureMapMarker().setLatLng([point.lat, point.lon]).addTo(map);
      mapMarker.setTooltipContent(html);
      if (tooltip) {
        tooltip.innerHTML = html;
        tooltip.hidden = false;
        var pct = (gx / width) * 100;
        tooltip.style.left = pct + "%";
        tooltip.classList.toggle("is-left", pct > 75);
        tooltip.classList.toggle("is-right", pct < 25);
      }
    }

    function hide() {
      if (guide) guide.style.display = "none";
      if (dot) dot.style.display = "none";
      if (mapMarker) map.removeLayer(mapMarker);
      if (tooltip) tooltip.hidden = true;
    }

    function onSvgMove(evt) {
      var rect = svg.getBoundingClientRect();
      var clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
      if (clientX === undefined) return;
      var relX = ((clientX - rect.left) / rect.width) * width;
      var km = ((relX - padL) / chartW) * totalKm;
      if (km < 0 || km > totalKm) {
        hide();
        return;
      }
      showAt(nearestByKm(km));
    }

    // Clic sur le profil : vue 360° la plus proche de ce point de la trace
    // (même popup que sur la carte, carte recentrée sur le point).
    svg.addEventListener("click", function (evt) {
      var rect = svg.getBoundingClientRect();
      var relX = ((evt.clientX - rect.left) / rect.width) * width;
      var km = ((relX - padL) / chartW) * totalKm;
      if (km < 0 || km > totalKm || !window.gmPanoramaxPoints) return;
      var point = nearestByKm(km);
      var latlng = L.latLng(point.lat, point.lon);
      var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      map.getContainer().scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      map.setView(latlng, Math.max(map.getZoom(), 15), { animate: !reduce });
      window.gmHandleTrackClick({ latlng: latlng }, map, window.gmPanoramaxPoints);
    });

    svg.addEventListener("mousemove", onSvgMove);
    svg.addEventListener("mouseleave", hide);
    svg.addEventListener("touchmove", onSvgMove, { passive: true });
    svg.addEventListener("touchend", hide);

    // Survol inverse : de la trace (carte) vers le profil.
    map.on("gm:track-hover", function (e) { showAt(nearestByLatLng(e.latlng.lat, e.latlng.lng)); });
    map.on("gm:track-hover-end", hide);
  };

  // Filtre par type de POI, appliqué à la fois aux marqueurs de la carte et
  // aux repères du profil altimétrique. markersByKind est un objet
  // { icone: [marqueurs Leaflet] } ; les repères du profil sont retrouvés
  // par leur classe CSS elevation-marker--<icone>.
  window.gmInitPOIFilter = function (filterBar, markersByKind, svg, map) {
    if (!filterBar || !map) return;

    var buttons = Array.prototype.slice.call(filterBar.querySelectorAll("[data-poi-kind]"));
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var kind = btn.getAttribute("data-poi-kind");
        var active = btn.classList.toggle("is-active");
        btn.setAttribute("aria-pressed", active ? "true" : "false");

        (markersByKind[kind] || []).forEach(function (m) {
          if (active) {
            if (!map.hasLayer(m)) m.addTo(map);
          } else if (map.hasLayer(m)) {
            map.removeLayer(m);
          }
        });

        if (svg) {
          var els = (svg.parentNode || svg).querySelectorAll(".elevation-marker--" + kind);
          els.forEach(function (el) { el.style.display = active ? "" : "none"; });
        }
      });
    });
  };

  // --- Fonds de carte -------------------------------------------------------

  var GM_ICONS = {
    layers: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2.5 8 12 13l9.5-5L12 3Z"/><path d="m2.5 12 9.5 5 9.5-5M2.5 16l9.5 5 9.5-5"/></svg>',
    locate: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/><circle cx="12" cy="12" r="8"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  };
  window.GM_ICONS = GM_ICONS;

  var IGN_WMTS = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";
  var OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
  var IGN_ATTR = '&copy; <a href="https://www.ign.fr/">IGN</a> – <a href="https://geoservices.ign.fr/">Géoplateforme</a>';

  // Fonds proposés (tous gratuits, sans clé). swatch : aperçu dans le menu.
  var GM_BASEMAPS = [
    { key: "plan", label: "Plan", hint: "OpenStreetMap", swatch: "linear-gradient(135deg,#f2efe9 55%,#aad3df 55%)",
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", opts: { maxZoom: 19, attribution: OSM_ATTR } },
    { key: "velo", label: "Vélo", hint: "CyclOSM : pistes et revêtements", swatch: "linear-gradient(135deg,#f6f2ea 45%,#2f7fe0 45% 55%,#f6f2ea 55%)",
      url: "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
      opts: { maxZoom: 20, attribution: '<a href="https://www.cyclosm.org/">CyclOSM</a> | ' + OSM_ATTR } },
    { key: "relief", label: "Relief", hint: "OpenTopoMap : courbes de niveau", swatch: "repeating-radial-gradient(circle at 70% 70%,#cfe0b4 0 4px,#b9a37e 4px 5px)",
      url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
      opts: { maxZoom: 17, attribution: OSM_ATTR + ', SRTM | style &copy; <a href="https://opentopomap.org/">OpenTopoMap</a> (CC-BY-SA)' } },
    { key: "ign", label: "IGN", hint: "Plan IGN", swatch: "linear-gradient(135deg,#f7f4ec 50%,#e3c48d 50% 60%,#9cc28e 60%)",
      url: IGN_WMTS + "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&FORMAT=image/png",
      opts: { maxZoom: 19, attribution: IGN_ATTR } },
    { key: "photo", label: "Photo aérienne", hint: "Orthophotos IGN", swatch: "linear-gradient(135deg,#5d6b45,#8a8a62 50%,#3f4a35)",
      url: IGN_WMTS + "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&FORMAT=image/jpeg",
      opts: { maxZoom: 19, attribution: IGN_ATTR } },
  ];

  function gmStoredBasemap() {
    try { return localStorage.getItem("gm-basemap"); } catch (e) { return null; }
  }

  // Ajoute à la carte le fond choisi (mémorisé d'une page à l'autre) et un
  // menu « Fond de carte » pour en changer.
  window.gmInitBasemaps = function (map, position) {
    var layers = {};
    var current = null;
    var stored = gmStoredBasemap();
    var initial = GM_BASEMAPS.some(function (b) { return b.key === stored; }) ? stored : "plan";

    function layerFor(b) {
      if (!layers[b.key]) {
        var opts = Object.assign({ subdomains: "abc" }, b.opts);
        layers[b.key] = L.tileLayer(b.url, opts);
      }
      return layers[b.key];
    }

    function select(key, list) {
      var b = GM_BASEMAPS.filter(function (x) { return x.key === key; })[0] || GM_BASEMAPS[0];
      if (current) map.removeLayer(current);
      current = layerFor(b).addTo(map);
      current.bringToBack();
      try { localStorage.setItem("gm-basemap", b.key); } catch (e) { /* stockage indisponible */ }
      if (list) {
        list.querySelectorAll("[data-basemap]").forEach(function (el) {
          var on = el.getAttribute("data-basemap") === b.key;
          el.classList.toggle("is-active", on);
          el.setAttribute("aria-checked", on ? "true" : "false");
        });
      }
      map.getContainer().setAttribute("data-basemap", b.key);
    }

    var Ctl = L.Control.extend({
      options: { position: position || "topright" },
      onAdd: function () {
        var box = L.DomUtil.create("div", "gm-basemap-control");
        var btn = L.DomUtil.create("button", "gm-map-btn gm-basemap-toggle", box);
        btn.type = "button";
        btn.innerHTML = GM_ICONS.layers;
        btn.title = "Fond de carte";
        btn.setAttribute("aria-label", "Changer de fond de carte");
        btn.setAttribute("aria-expanded", "false");
        var list = L.DomUtil.create("div", "gm-basemap-list", box);
        list.setAttribute("role", "radiogroup");
        list.setAttribute("aria-label", "Fond de carte");
        list.hidden = true;
        GM_BASEMAPS.forEach(function (b) {
          var item = L.DomUtil.create("button", "gm-basemap-item", list);
          item.type = "button";
          item.setAttribute("role", "radio");
          item.setAttribute("data-basemap", b.key);
          item.innerHTML = '<span class="gm-basemap-swatch" style="background:' + b.swatch + '"></span>' +
            '<span class="gm-basemap-text"><strong>' + b.label + "</strong><small>" + b.hint + "</small></span>" +
            '<span class="gm-basemap-check">' + GM_ICONS.check + "</span>";
          L.DomEvent.on(item, "click", function () { select(b.key, list); close(); });
        });
        function open() {
          // hauteur disponible : le menu défile s'il est plus haut que la carte
          box.style.setProperty("--gm-map-h", map.getContainer().clientHeight + "px");
          list.hidden = false;
          btn.setAttribute("aria-expanded", "true");
          box.classList.add("is-open");
        }
        function close() { list.hidden = true; btn.setAttribute("aria-expanded", "false"); box.classList.remove("is-open"); }
        L.DomEvent.on(btn, "click", function () { list.hidden ? open() : close(); });
        document.addEventListener("click", function (e) { if (!box.contains(e.target)) close(); });
        document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
        L.DomEvent.disableClickPropagation(box);
        L.DomEvent.disableScrollPropagation(box);
        select(initial, list);
        return box;
      },
    });
    new Ctl().addTo(map);
    return { select: function (key) { select(key, map.getContainer().querySelector(".gm-basemap-list")); } };
  };

  // Contrôle "Me localiser" intégré à la carte (même famille que les
  // boutons de zoom) : demande la position du visiteur (API de
  // géolocalisation du navigateur, nécessite son autorisation) et place un
  // marqueur "vous êtes ici" sur la carte Leaflet.
  window.gmInitLocateMe = function (map) {
    if (!map || !window.L) return;

    var LocateControl = L.Control.extend({
      options: { position: "topleft" },
      onAdd: function () {
        var container = L.DomUtil.create("div", "leaflet-bar gm-locate-control");
        var link = L.DomUtil.create("a", "gm-locate-btn", container);
        link.href = "#";
        link.title = "Me localiser sur la carte";
        link.setAttribute("role", "button");
        link.setAttribute("aria-label", "Me localiser sur la carte");
        link.innerHTML = GM_ICONS.locate;

        L.DomEvent.disableClickPropagation(container);
        L.DomEvent.disableScrollPropagation(container);

        var marker = null;

        L.DomEvent.on(link, "click", function (e) {
          L.DomEvent.stop(e);
          if (link.classList.contains("gm-locate-btn--loading")) return;

          if (!navigator.geolocation) {
            link.classList.add("gm-locate-btn--error");
            setTimeout(function () { link.classList.remove("gm-locate-btn--error"); }, 2000);
            return;
          }

          link.classList.add("gm-locate-btn--loading");

          navigator.geolocation.getCurrentPosition(
            function (pos) {
              var latlng = [pos.coords.latitude, pos.coords.longitude];
              if (marker) {
                marker.setLatLng(latlng);
              } else {
                marker = L.circleMarker(latlng, { radius: 8, className: "gm-my-location" }).addTo(map);
                marker.bindPopup("Vous êtes ici");
              }
              map.panTo(latlng);
              marker.openPopup();
              link.classList.remove("gm-locate-btn--loading");
            },
            function () {
              link.classList.remove("gm-locate-btn--loading");
              link.classList.add("gm-locate-btn--error");
              setTimeout(function () { link.classList.remove("gm-locate-btn--error"); }, 2000);
            },
            { enableHighAccuracy: true, timeout: 10000 }
          );
        });

        return container;
      },
    });

    new LocateControl().addTo(map);
  };

  // Active le lightbox sur toute image marquée data-lightbox (galerie photo).
  document.addEventListener("click", function (e) {
    var trigger = e.target.closest("[data-lightbox]");
    if (!trigger) return;
    e.preventDefault();
    var img = trigger.querySelector("img");
    window.gmOpenPhoto(
      trigger.getAttribute("href") || (img && img.src),
      trigger.getAttribute("data-caption") || (img && img.alt)
    );
  });

  // Bouton "Copier le lien" du bloc de partage.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-link]");
    if (!btn) return;
    var link = btn.getAttribute("data-copy-link");
    if (!link) return;

    var reset = btn.textContent;
    var status = document.querySelector("[data-share-status]");
    var done = function () {
      btn.textContent = "Lien copié !";
      btn.classList.add("share-btn--copied");
      if (status) status.textContent = "Lien de la sortie copié dans le presse-papiers.";
      setTimeout(function () {
        if (status) status.textContent = "";
        btn.textContent = reset;
        btn.classList.remove("share-btn--copied");
      }, 1800);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(done).catch(function () {
        window.prompt("Copiez ce lien :", link);
      });
    } else {
      window.prompt("Copiez ce lien :", link);
    }
  });

  // Bouton "Instagram" du bloc de partage. Il n'existe pas d'URL de partage
  // web pour Instagram (contrairement à Facebook/WhatsApp/X) : on utilise la
  // Web Share API avec un fichier quand le navigateur le permet (ouvre le
  // sélecteur natif de l'appareil, qui propose Instagram s'il est installé).
  // Sans ce support (desktop, navigateurs plus anciens), le lien garde son
  // comportement natif : téléchargement direct de l'image (attribut download).
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-ig-share]");
    if (!btn) return;
    if (!(navigator.share && navigator.canShare)) return; // comportement natif (téléchargement)

    var url = btn.getAttribute("data-ig-share");
    if (!url) return;
    e.preventDefault();

    fetch(url)
      .then(function (resp) { return resp.blob(); })
      .then(function (blob) {
        var file = new File([blob], "sortie.jpg", { type: blob.type || "image/jpeg" });
        if (navigator.canShare({ files: [file] })) {
          return navigator.share({ files: [file], title: btn.getAttribute("data-ig-title") || "" });
        }
        window.location.href = url;
      })
      .catch(function () {
        window.location.href = url;
      });
  });

  var prefersReducedMotion = function () {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  };

  // --- Fiche de sortie : trace colorisée selon la pente ---------------------

  // Charge la trace d'une sortie sur la carte détaillée :
  //  - en priorité slope.geojson (tronçons pré-calculés par
  //    tools/slope_colors.py, chacun avec sa couleur) ;
  //  - à défaut (fichier non généré, obsolète ou injoignable), le GPX
  //    d'origine, affiché d'une couleur uniforme, avec un avertissement dans
  //    la console des outils de développement.
  // Dans les deux cas un seul fichier est téléchargé.
  window.gmLoadRideTrack = function (map, opts) {
    function attachHover(layer) {
      layer.on("mousemove", function (ev) { map.fire("gm:track-hover", { latlng: ev.latlng }); });
      layer.on("mouseout", function () { map.fire("gm:track-hover-end"); });
    }

    function fit(layer) {
      var b = layer.getBounds();
      if (b.isValid()) map.fitBounds(b, { padding: [24, 24] });
    }

    function addSlope(data) {
      if (!data || !data.features || !data.features.length) throw new Error("GeoJSON vide");
      // Liseré sombre sous la trace : garde chaque couleur lisible sur le fond de carte.
      L.geoJSON(data, {
        interactive: false,
        style: { color: "#1f1b16", weight: 8, opacity: 0.45, lineCap: "round", lineJoin: "round" },
      }).addTo(map);
      var layer = L.geoJSON(data, {
        style: function (f) {
          return { color: f.properties.color, weight: 5, opacity: 1, lineCap: "round", lineJoin: "round" };
        },
      }).addTo(map);
      attachHover(layer);
      fit(layer);
      return layer;
    }

    function parseGPX(text) {
      var doc = new DOMParser().parseFromString(text, "application/xml");
      var pts = doc.getElementsByTagName("trkpt");
      if (!pts.length) pts = doc.getElementsByTagName("rtept");
      var latlngs = [];
      for (var i = 0; i < pts.length; i++) {
        var lat = parseFloat(pts[i].getAttribute("lat"));
        var lon = parseFloat(pts[i].getAttribute("lon"));
        if (isFinite(lat) && isFinite(lon)) latlngs.push([lat, lon]);
      }
      return latlngs;
    }

    function loadGPX() {
      return fetch(opts.gpxUrl)
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.text();
        })
        .then(function (text) {
          var latlngs = parseGPX(text);
          if (latlngs.length < 2) throw new Error("aucun point de trace");
          var layer = L.polyline(latlngs, { color: opts.color || "#b8562f", weight: 4, opacity: 0.9 }).addTo(map);
          attachHover(layer);
          fit(layer);
          return layer;
        })
        .catch(function (err) {
          console.error("[Cyclo Explore] Impossible de charger la trace GPX " + opts.gpxUrl + " : " + err.message);
          var el = map.getContainer();
          if (el && el.parentNode) {
            var msg = document.createElement("p");
            msg.className = "map-error";
            msg.setAttribute("role", "status");
            msg.textContent = "La trace n'a pas pu être chargée. Vous pouvez toujours télécharger le fichier GPX.";
            el.parentNode.insertBefore(msg, el.nextSibling);
          }
          return null;
        });
    }

    function fallback(reason) {
      console.warn(
        "[Cyclo Explore] Trace colorisée selon la pente indisponible (" + reason + ") : " +
        "affichage de la trace GPX d'origine en couleur uniforme. " +
        "Pour la générer : python3 tools/slope_colors.py"
      );
      return loadGPX();
    }

    if (!opts.slopeUrl) return fallback("slope.geojson absent ou obsolète lors de la génération du site");
    return fetch(opts.slopeUrl)
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status + " sur " + opts.slopeUrl);
        return r.json();
      })
      .then(addSlope)
      .catch(function (err) { return fallback(err.message); });
  };

  // --- Fiche de sortie : liste des POI reliée à la carte ---------------------

  // Cliquer sur un POI de la liste ou sur son icône dans le profil
  // altimétrique centre la carte dessus et ouvre sa popup (en réaffichant son
  // type s'il avait été masqué par le filtre).
  window.gmInitPOIList = function (section, map, registry, filterBar) {
    if (!map) return;
    var current = null;
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-poi-id]");
      if (!btn || !(btn.closest(".poi-section") || btn.closest(".elevation-chart"))) return;
      var entry = registry[btn.getAttribute("data-poi-id")];
      if (!entry) return;

      if (!map.hasLayer(entry.marker)) {
        var kindBtn = filterBar && filterBar.querySelector('[data-poi-kind="' + entry.kind + '"]');
        if (kindBtn && !kindBtn.classList.contains("is-active")) kindBtn.click();
        if (!map.hasLayer(entry.marker)) entry.marker.addTo(map);
      }

      if (current) current.classList.remove("is-current");
      current = section && section.querySelector('.poi-item[data-poi-id="' + btn.getAttribute("data-poi-id") + '"]');
      if (current) current.classList.add("is-current");

      var reduce = prefersReducedMotion();
      map.getContainer().scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      map.setView(entry.marker.getLatLng(), Math.max(map.getZoom(), 15), { animate: !reduce });
      entry.marker.openPopup();
    });
  };

  // --- Fiche de sortie : carrousel de photos ---------------------------------

  // Une photo à la fois, défilement automatique en fondu (boucle), flèches,
  // points de navigation, clavier (← →), balayage tactile. Le défilement
  // automatique s'arrête dès que l'utilisateur interagit et reprend après
  // un délai d'inactivité ; il est désactivé (mais peut être lancé) si
  // l'utilisateur a demandé à réduire les animations.
  function initCarousel(root) {
    var slides = Array.prototype.slice.call(root.querySelectorAll(".carousel-slide"));
    var n = slides.length;
    if (n < 2) return;

    var dots = Array.prototype.slice.call(root.querySelectorAll("[data-carousel-dot]"));
    var counter = root.querySelector("[data-carousel-counter]");
    var toggle = root.querySelector("[data-carousel-toggle]");
    var INTERVAL = 5000;
    var RESUME_DELAY = 10000;

    var index = 0;
    var timer = null;
    var resumeTimer = null;
    var paused = prefersReducedMotion(); // pause demandée explicitement (ou animations réduites)
    var hovering = false;

    function load(k) {
      var img = slides[k].querySelector("img[data-src]");
      if (img) {
        img.src = img.getAttribute("data-src");
        img.removeAttribute("data-src");
      }
    }

    function show(k) {
      k = (k + n) % n;
      if (k === index) return;
      var prev = slides[index];
      prev.classList.remove("is-active");
      prev.setAttribute("aria-hidden", "true");
      prev.inert = true;
      load(k);
      var next = slides[k];
      next.classList.add("is-active");
      next.removeAttribute("aria-hidden");
      next.inert = false;
      dots.forEach(function (d, i) {
        d.classList.toggle("is-active", i === k);
        if (i === k) d.setAttribute("aria-current", "true");
        else d.removeAttribute("aria-current");
      });
      if (counter) counter.textContent = k + 1 + " / " + n;
      index = k;
      load((k + 1) % n); // précharge la suivante
    }

    function stop() {
      clearInterval(timer);
      timer = null;
    }

    function start() {
      stop();
      clearTimeout(resumeTimer);
      if (paused || hovering || document.hidden) return;
      timer = setInterval(function () { show(index + 1); }, INTERVAL);
    }

    // Interaction de l'utilisateur : on suspend, puis on reprend après un
    // délai d'inactivité (sauf pause explicite).
    function interact() {
      stop();
      clearTimeout(resumeTimer);
      if (!paused) resumeTimer = setTimeout(start, RESUME_DELAY);
    }

    function renderToggle() {
      if (!toggle) return;
      toggle.classList.toggle("is-paused", paused);
      toggle.setAttribute("aria-label", paused ? "Lancer le défilement automatique" : "Mettre en pause le défilement automatique");
    }

    root.querySelector("[data-carousel-prev]").addEventListener("click", function () { show(index - 1); interact(); });
    root.querySelector("[data-carousel-next]").addEventListener("click", function () { show(index + 1); interact(); });
    dots.forEach(function (d) {
      d.addEventListener("click", function () { show(parseInt(d.getAttribute("data-carousel-dot"), 10)); interact(); });
    });
    if (toggle) {
      toggle.addEventListener("click", function () {
        paused = !paused;
        renderToggle();
        if (paused) {
          stop();
          clearTimeout(resumeTimer);
        } else {
          show(index + 1);
          start();
        }
      });
    }

    root.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { show(index - 1); interact(); e.preventDefault(); }
      else if (e.key === "ArrowRight") { show(index + 1); interact(); e.preventDefault(); }
    });

    root.addEventListener("mouseenter", function () { hovering = true; stop(); clearTimeout(resumeTimer); });
    root.addEventListener("mouseleave", function () { hovering = false; interact(); });
    root.addEventListener("focusin", function () { stop(); clearTimeout(resumeTimer); });
    root.addEventListener("focusout", function (e) { if (!root.contains(e.relatedTarget)) interact(); });

    var touchX = null;
    root.addEventListener("touchstart", function (e) { touchX = e.touches[0].clientX; }, { passive: true });
    root.addEventListener("touchend", function (e) {
      if (touchX === null) return;
      var dx = e.changedTouches[0].clientX - touchX;
      touchX = null;
      if (Math.abs(dx) > 40) { show(dx < 0 ? index + 1 : index - 1); interact(); }
    });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop();
      else if (!timer && !resumeTimer) start();
    });

    renderToggle();
    load(1);
    start();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-carousel]").forEach(initCarousel);
  });

  // --- Partage natif du navigateur (Web Share API) ---------------------------

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-native-share]").forEach(function (btn) {
      if (!navigator.share) return; // bouton laissé masqué : les autres options restent disponibles
      btn.hidden = false;
      btn.addEventListener("click", function () {
        navigator.share({
          title: btn.getAttribute("data-share-title") || document.title,
          text: btn.getAttribute("data-share-text") || "",
          url: btn.getAttribute("data-native-share") || window.location.href,
        }).catch(function () { /* partage annulé : rien à faire */ });
      });
    });
  });

  // --- Accueil : défilement des photos au survol d'un cartouche --------------

  // Chaque .ride-card-photo[data-photo-carousel] contient une miniature par
  // photo, superposées ; seules la première est chargée d'emblée, les autres
  // au premier survol.
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-photo-carousel]").forEach(function (box) {
      var layers = box.querySelectorAll(".ride-card-photo-layer");
      if (layers.length < 2) return;
      var card = box.closest(".ride-card") || box;
      var timer = null;
      var i = 0;

      card.addEventListener("mouseenter", function () {
        if (prefersReducedMotion()) return;
        layers.forEach(function (l) {
          if (l.hasAttribute("data-src")) {
            l.src = l.getAttribute("data-src");
            l.removeAttribute("data-src");
          }
        });
        i = 0;
        clearInterval(timer);
        timer = setInterval(function () {
          layers[i].classList.remove("is-active");
          i = (i + 1) % layers.length;
          layers[i].classList.add("is-active");
        }, 1200);
      });
      card.addEventListener("mouseleave", function () {
        clearInterval(timer);
        layers.forEach(function (layer, idx) {
          layer.classList.toggle("is-active", idx === 0);
        });
      });
    });
  });

  // --- Accueil : carte de toutes les sorties -----------------------------------

  function el(tag, className, text) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // Contenu de la popup d'une sortie : mêmes informations que son cartouche.
  function ridePopupContent(r) {
    var wrap = el("div", "ride-popup");
    if (r.thumb) {
      var img = el("img", "ride-popup-photo");
      img.src = r.thumb;
      img.alt = "";
      img.loading = "lazy";
      wrap.appendChild(img);
    }
    var body = el("div", "ride-popup-body");
    var title = el("h3", "ride-popup-title");
    var sw = el("span", "ride-swatch");
    sw.style.setProperty("--ride-color", r.color);
    sw.setAttribute("aria-hidden", "true");
    title.appendChild(sw);
    title.appendChild(document.createTextNode(r.title));
    body.appendChild(title);

    var facts = el("ul", "ride-facts ride-facts--compact");
    if (r.difficulty) facts.appendChild(el("li", "diff-badge diff-badge--" + (r.difficultyKey || ""), r.difficulty));
    if (r.duration) facts.appendChild(el("li", "ride-fact", "⏱ " + r.duration));
    if (r.elevation) facts.appendChild(el("li", "ride-fact", "↗ " + r.elevation + " m D+"));
    if (facts.children.length) body.appendChild(facts);

    if (r.summary) body.appendChild(el("p", "ride-popup-summary", r.summary));
    var link = el("a", "btn btn--primary btn--small", "Voir la sortie");
    link.href = r.url;
    body.appendChild(link);
    wrap.appendChild(body);
    return wrap;
  }

  // Crée la carte d'accueil. handlers.onSelect(slug|null) est appelé quand
  // une trace est sélectionnée (clic) ou désélectionnée (popup fermée).
  function initHomeMap(container, rides, handlers) {
    if (!container) return null;
    if (!window.L || !rides.length) {
      container.classList.add("home-map--unavailable");
      container.textContent = window.L ? "" : "La carte n'a pas pu être chargée.";
      return null;
    }

    var map = L.map(container, { scrollWheelZoom: false, zoomSnap: 0.25 });
    window.gmInitBasemaps(map, "topright");

    // Molette active seulement après un clic sur la carte : faire défiler la
    // page ne doit pas zoomer par accident.
    map.on("click focus", function () { map.scrollWheelZoom.enable(); });
    container.addEventListener("mouseleave", function () { map.scrollWheelZoom.disable(); });

    var layers = {};
    var visible = {};
    var highlighted = null;
    var selected = null;
    // Marges de recentrage : la popup ne doit pas passer sous les boutons de
    // la carte (zoom à gauche, fond de carte à droite).
    var popup = L.popup({ maxWidth: 300, minWidth: 240, className: "ride-popup-wrap",
      autoPanPaddingTopLeft: [64, 66], autoPanPaddingBottomRight: [64, 30] });

    rides.forEach(function (r) {
      var casing = L.polyline(r.coords, { color: "#ffffff", weight: 7, opacity: 0.85, interactive: false });
      var line = L.polyline(r.coords, { color: r.color, weight: 4, opacity: 0.95, interactive: false });
      // Ligne invisible et large : la cible du clic/survol, bien plus facile
      // à atteindre qu'un trait de 4 px (au doigt notamment).
      var hit = L.polyline(r.coords, { color: r.color, weight: 20, opacity: 0, className: "home-map-hit" });
      hit.bindTooltip(r.title, { sticky: true, direction: "top", className: "home-map-tooltip" });
      hit.on("mouseover", function () { setHighlight(r.slug); });
      hit.on("mouseout", function () { setHighlight(null); });
      hit.on("click", function (ev) {
        L.DomEvent.stopPropagation(ev);
        select(r.slug, ev.latlng);
      });
      layers[r.slug] = { ride: r, group: L.layerGroup([casing, line, hit]), casing: casing, line: line, hit: hit };
    });

    function restyle() {
      var focus = highlighted || selected;
      Object.keys(layers).forEach(function (slug) {
        var l = layers[slug];
        var isFocus = slug === focus;
        l.line.setStyle({ weight: isFocus ? 6 : 4, opacity: focus && !isFocus ? 0.35 : 0.95 });
        l.casing.setStyle({ weight: isFocus ? 10 : 7, opacity: focus && !isFocus ? 0.4 : 0.85 });
      });
      if (focus && layers[focus] && visible[focus]) {
        layers[focus].casing.bringToFront();
        layers[focus].line.bringToFront();
      }
    }

    function setHighlight(slug) {
      highlighted = slug;
      restyle();
    }

    function select(slug, latlng) {
      var l = layers[slug];
      if (!l) return;
      selected = slug;
      restyle();
      if (!latlng) {
        var c = l.ride.coords[Math.floor(l.ride.coords.length / 2)];
        latlng = L.latLng(c[0], c[1]);
      }
      popup.setLatLng(latlng).setContent(ridePopupContent(l.ride)).openOn(map);
      if (handlers && handlers.onSelect) handlers.onSelect(slug);
    }

    map.on("popupclose", function (e) {
      if (e.popup !== popup) return;
      selected = null;
      restyle();
      if (handlers && handlers.onSelect) handlers.onSelect(null);
    });

    function fitVisible(animate) {
      var bounds = null;
      Object.keys(visible).forEach(function (slug) {
        if (!visible[slug]) return;
        var b = layers[slug].line.getBounds();
        bounds = bounds ? bounds.extend(b) : L.latLngBounds(b.getSouthWest(), b.getNorthEast());
      });
      if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24], animate: !!animate && !prefersReducedMotion() });
      }
    }

    return {
      map: map,
      highlight: setHighlight,
      // Affiche uniquement les sorties de slugs (objet { slug: true }).
      setVisible: function (slugs, refit) {
        Object.keys(layers).forEach(function (slug) {
          var show = !!slugs[slug];
          visible[slug] = show;
          if (show && !map.hasLayer(layers[slug].group)) layers[slug].group.addTo(map);
          if (!show && map.hasLayer(layers[slug].group)) {
            map.removeLayer(layers[slug].group);
            if (selected === slug) map.closePopup(popup);
          }
        });
        restyle();
        if (refit) fitVisible(true);
      },
      fitVisible: fitVisible,
    };
  }

  // Filtres (tags + difficulté) de l'accueil, appliqués simultanément aux
  // cartouches et aux traces de la carte. Tags : cumulatifs (une sortie doit
  // les avoir tous) ; difficultés : au choix (une sortie doit avoir l'une
  // d'elles). L'état est reflété dans l'URL (#tags=...&difficulte=...) pour
  // rester partageable et rechargeable.
  document.addEventListener("DOMContentLoaded", function () {
    var explore = document.querySelector("[data-explore]");
    if (!explore) return;

    var cards = Array.prototype.slice.call(explore.querySelectorAll(".ride-card"));
    var cardBySlug = {};
    cards.forEach(function (c) { cardBySlug[c.getAttribute("data-slug")] = c; });

    var allBtn = explore.querySelector("[data-tag-all]");
    var tagBtns = Array.prototype.slice.call(explore.querySelectorAll("[data-tag]"));
    var diffBtns = Array.prototype.slice.call(explore.querySelectorAll("[data-difficulty]")).filter(function (b) {
      return b.tagName === "BUTTON";
    });
    var emptyMsg = explore.querySelector("[data-tag-empty]");
    var countEl = explore.querySelector("[data-ride-count]");
    var tagsToggle = explore.querySelector("[data-tags-toggle]");
    var tagsPanel = explore.querySelector("[data-tag-filter]");
    var tagsCount = explore.querySelector("[data-tags-count]");
    var activeTags = new Set();
    var activeDiffs = new Set();

    var rides = [];
    try {
      var dataEl = document.getElementById("home-map-data");
      rides = dataEl ? JSON.parse(dataEl.textContent) : [];
    } catch (err) {
      console.error("[Cyclo Explore] Données de la carte illisibles :", err);
    }

    // Défilement horizontal des cartouches : flèches gauche/droite, masquées
    // aux extrémités. Une flèche fait défiler d'une « page » de cartouches.
    var rail = explore.querySelector("[data-ride-grid]");
    var railPrev = explore.querySelector("[data-rail-prev]");
    var railNext = explore.querySelector("[data-rail-next]");
    function updateRail() {
      if (!rail) return;
      var max = rail.scrollWidth - rail.clientWidth;
      if (railPrev) railPrev.hidden = rail.scrollLeft <= 10;
      if (railNext) railNext.hidden = rail.scrollLeft >= max - 10;
    }
    function scrollRail(dir) {
      var card = rail.querySelector(".ride-card:not([hidden])");
      var step = card ? card.getBoundingClientRect().width + 20 : 320;
      var perPage = Math.max(1, Math.floor(rail.clientWidth / step));
      rail.scrollBy({ left: dir * perPage * step, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    }
    if (rail) {
      if (railPrev) railPrev.addEventListener("click", function () { scrollRail(-1); });
      if (railNext) railNext.addEventListener("click", function () { scrollRail(1); });
      rail.addEventListener("scroll", updateRail, { passive: true });
      window.addEventListener("resize", updateRail);
    }

    var selectedCard = null;
    var home = initHomeMap(document.getElementById("home-map"), rides, {
      onSelect: function (slug) {
        if (selectedCard) selectedCard.classList.remove("is-selected");
        selectedCard = slug ? cardBySlug[slug] : null;
        if (selectedCard) {
          selectedCard.classList.add("is-selected");
          // Amène le cartouche de la sortie cliquée dans la ligne visible,
          // sans faire défiler la page verticalement.
          var target = selectedCard.offsetLeft - (rail.clientWidth - selectedCard.offsetWidth) / 2;
          rail.scrollTo({ left: Math.max(0, target), behavior: prefersReducedMotion() ? "auto" : "smooth" });
        }
      },
    });

    // Survol / focus d'un cartouche -> mise en évidence de sa trace.
    cards.forEach(function (card) {
      var slug = card.getAttribute("data-slug");
      card.addEventListener("mouseenter", function () { if (home) home.highlight(slug); });
      card.addEventListener("mouseleave", function () { if (home) home.highlight(null); });
      card.addEventListener("focusin", function () { if (home) home.highlight(slug); });
      card.addEventListener("focusout", function () { if (home) home.highlight(null); });
    });

    function readHash() {
      var tags = window.location.hash.match(/tags=([^&]*)/);
      var diffs = window.location.hash.match(/difficulte=([^&]*)/);
      if (tags && tags[1]) {
        tags[1].split(",").forEach(function (t) {
          t = decodeURIComponent(t).trim().toLowerCase();
          if (t) activeTags.add(t);
        });
      }
      if (diffs && diffs[1]) {
        diffs[1].split(",").forEach(function (d) {
          d = decodeURIComponent(d).trim().toLowerCase();
          if (d) activeDiffs.add(d);
        });
      }
    }

    function writeHash() {
      var parts = [];
      if (activeTags.size) parts.push("tags=" + Array.from(activeTags).map(encodeURIComponent).join(","));
      if (activeDiffs.size) parts.push("difficulte=" + Array.from(activeDiffs).map(encodeURIComponent).join(","));
      var url = window.location.pathname + window.location.search + (parts.length ? "#" + parts.join("&") : "");
      window.history.replaceState(null, "", url);
    }

    function setPressed(btn, on) {
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    }

    function apply(refit) {
      tagBtns.forEach(function (b) { setPressed(b, activeTags.has(b.getAttribute("data-tag"))); });
      diffBtns.forEach(function (b) { setPressed(b, activeDiffs.has(b.getAttribute("data-difficulty"))); });
      if (allBtn) setPressed(allBtn, activeTags.size === 0 && activeDiffs.size === 0);
      if (tagsCount) tagsCount.textContent = activeTags.size ? " (" + activeTags.size + ")" : "";

      var tagList = Array.from(activeTags);
      var shown = {};
      var count = 0;
      cards.forEach(function (card) {
        var cardTags = (card.getAttribute("data-tags") || "").split(",").filter(Boolean);
        var okTags = tagList.every(function (t) { return cardTags.indexOf(t) !== -1; });
        var okDiff = activeDiffs.size === 0 || activeDiffs.has(card.getAttribute("data-difficulty"));
        var match = okTags && okDiff;
        card.hidden = !match;
        if (match) {
          shown[card.getAttribute("data-slug")] = true;
          count++;
        }
      });

      if (countEl) countEl.textContent = count + (count > 1 ? " sorties" : " sortie");
      if (emptyMsg) emptyMsg.style.display = count === 0 ? "block" : "none";
      if (home) home.setVisible(shown, refit);
      if (rail) {
        rail.scrollLeft = 0;
        updateRail();
      }
    }

    explore.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-tag], [data-tag-all], button[data-difficulty]");
      if (!btn || !explore.querySelector("[data-filters]").contains(btn)) return;
      if (btn.hasAttribute("data-tag-all")) {
        activeTags.clear();
        activeDiffs.clear();
      } else if (btn.hasAttribute("data-tag")) {
        var tag = btn.getAttribute("data-tag");
        if (activeTags.has(tag)) activeTags.delete(tag);
        else activeTags.add(tag);
      } else {
        var d = btn.getAttribute("data-difficulty");
        if (activeDiffs.has(d)) activeDiffs.delete(d);
        else activeDiffs.add(d);
      }
      writeHash();
      apply(true);
    });

    // Sur petit écran, la longue liste de tags est repliée par défaut.
    function setTagsOpen(open) {
      if (!tagsToggle || !tagsPanel) return;
      tagsToggle.setAttribute("aria-expanded", open ? "true" : "false");
      tagsPanel.hidden = !open;
    }
    if (tagsToggle) {
      tagsToggle.addEventListener("click", function () {
        setTagsOpen(tagsToggle.getAttribute("aria-expanded") !== "true");
      });
    }

    readHash();
    var narrow = window.matchMedia && window.matchMedia("(max-width: 700px)").matches;
    setTagsOpen(!narrow || activeTags.size > 0);
    apply(false);
    if (home) home.fitVisible(false);
  });
})();
