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

  window.gmOpenPanoramax = function (endpoint, sequence, picture) {
    // Le composant se base sur la query string de la page (ex: ?focus=pic&pic=...)
    // avant l'attribut "picture" si elle est présente. On la vide pour être
    // certain qu'il utilise bien la photo qu'on lui demande.
    if (window.location.search) {
      window.history.replaceState(null, "", window.location.pathname + window.location.hash);
    }

    var wrap = document.createElement("div");
    wrap.className = "gm-panoramax";

    var el = document.createElement("pnx-photo-viewer");
    el.setAttribute("endpoint", endpoint);
    if (sequence) el.setAttribute("sequence", sequence);
    el.setAttribute("picture", picture);
    el.setAttribute("widgets", "false");
    wrap.appendChild(el);

    openModal(wrap);
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

  function gmPanoramaxButtonContent(label, endpoint, sequence, picture) {
    var wrap = document.createElement("div");
    wrap.className = "gm-track-panoramax-popup";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "gm-track-panoramax-btn";
    btn.textContent = "🧭 Voir en 360°" + (label ? " · " + label : "");
    btn.addEventListener("click", function () {
      window.gmOpenPanoramax(endpoint, sequence, picture);
    });
    wrap.appendChild(btn);
    return wrap;
  }

  function gmPanoramaxEmptyContent() {
    var wrap = document.createElement("div");
    wrap.className = "gm-track-panoramax-popup gm-track-panoramax-popup--empty";
    wrap.textContent = "Aucune photo à 360° à cet endroit.";
    return wrap;
  }

  // Interroge l'API Panoramax (standard STAC, filtre bbox) pour trouver la
  // photo la plus proche de (lat, lon), dans un rayon de radiusM. Renvoie
  // une promesse résolue avec {id, sequence, lat, lon} ou null si rien à
  // proximité (ou en cas d'erreur réseau).
  window.gmFindNearestPanoramax = function (lat, lon, radiusM, endpoint) {
    var dLat = radiusM / 111320;
    var dLon = radiusM / (111320 * Math.cos((lat * Math.PI) / 180));
    var bbox = [lon - dLon, lat - dLat, lon + dLon, lat + dLat].join(",");
    var url = endpoint.replace(/\/$/, "") + "/search?bbox=" + encodeURIComponent(bbox) + "&limit=10";

    return fetch(url)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var features = (data && data.features) || [];
        if (!features.length) return null;

        var best = null;
        var bestDist = Infinity;
        features.forEach(function (f) {
          var coords = f.geometry && f.geometry.coordinates;
          if (!coords) return;
          var d = gmDistMeters(lat, lon, coords[1], coords[0]);
          if (d < bestDist) {
            bestDist = d;
            best = { id: f.id, sequence: f.collection, lat: coords[1], lon: coords[0] };
          }
        });
        return best;
      })
      .catch(function () {
        return null;
      });
  };

  // Clic sur la carte : ouvre immédiatement une popup avec un indicateur de
  // chargement, puis l'actualise avec un bouton "Voir en 360°" si une vue
  // panoramax existe près de l'endroit cliqué, ou un message sinon. Vérifie
  // d'abord les points catalogués à la main dans points.md (rapide, pas de
  // réseau) ; à défaut, interroge l'API Panoramax en direct pour trouver
  // n'importe quelle photo existante à proximité, même non cataloguée.
  var gmTrackClickSeq = 0;

  window.gmHandleTrackClick = function (ev, map, panoramaxPoints) {
    var seq = ++gmTrackClickSeq;
    var clickLat = ev.latlng.lat;
    var clickLon = ev.latlng.lng;

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
      L.popup().setLatLng([best.lat, best.lon])
        .setContent(gmPanoramaxButtonContent(best.label, best.endpoint, best.sequence, best.picture))
        .openOn(map);
      return;
    }

    var popup = L.popup().setLatLng(ev.latlng).setContent(gmPanoramaxLoadingContent()).openOn(map);

    window.gmFindNearestPanoramax(clickLat, clickLon, 25, GM_PANORAMAX_DEFAULT_ENDPOINT).then(function (found) {
      // Un clic plus récent a eu lieu, ou la popup a été refermée entre-temps.
      if (seq !== gmTrackClickSeq || !map.hasLayer(popup)) return;

      if (found) {
        popup.setContent(gmPanoramaxButtonContent("", GM_PANORAMAX_DEFAULT_ENDPOINT, found.sequence, found.id));
      } else {
        popup.setContent(gmPanoramaxEmptyContent());
      }
    });
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
        link.innerHTML = "📍";

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
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);

    // Molette active seulement après un clic sur la carte : faire défiler la
    // page ne doit pas zoomer par accident.
    map.on("click focus", function () { map.scrollWheelZoom.enable(); });
    container.addEventListener("mouseleave", function () { map.scrollWheelZoom.disable(); });

    var layers = {};
    var visible = {};
    var highlighted = null;
    var selected = null;
    var popup = L.popup({ maxWidth: 300, minWidth: 240, className: "ride-popup-wrap", autoPanPadding: [20, 20] });

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

    var selectedCard = null;
    var home = initHomeMap(document.getElementById("home-map"), rides, {
      onSelect: function (slug) {
        if (selectedCard) selectedCard.classList.remove("is-selected");
        selectedCard = slug ? cardBySlug[slug] : null;
        if (selectedCard) selectedCard.classList.add("is-selected");
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
