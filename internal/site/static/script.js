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
  window.gmHandleTrackClick = function (ev, map, panoramaxPoints) {
    if (!panoramaxPoints || !panoramaxPoints.length) return;

    function distMeters(lat1, lon1, lat2, lon2) {
      var R = 6371000;
      var toRad = function (d) { return (d * Math.PI) / 180; };
      var dLat = toRad(lat2 - lat1);
      var dLon = toRad(lon2 - lon1);
      var a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
      return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    var clickLat = ev.latlng.lat;
    var clickLon = ev.latlng.lng;
    var best = null;
    var bestDist = 200; // mètres : au-delà, pas de vue panoramax "ici" (marge généreuse : cliquer précisément sur une ligne fine à l'écran est imprécis, et le point panoramax n'est pas forcément exactement sur la trace enregistrée)

    panoramaxPoints.forEach(function (p) {
      var d = distMeters(clickLat, clickLon, p.lat, p.lon);
      if (d < bestDist) {
        bestDist = d;
        best = p;
      }
    });
    if (!best) return;

    var wrap = document.createElement("div");
    wrap.className = "gm-track-panoramax-popup";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "gm-track-panoramax-btn";
    btn.textContent = "🧭 Voir en 360° · " + best.label;
    btn.addEventListener("click", function () {
      window.gmOpenPanoramax(best.endpoint, best.sequence, best.picture);
    });
    wrap.appendChild(btn);

    L.popup().setLatLng([best.lat, best.lon]).setContent(wrap).openOn(map);
  };

  // Construit le contenu d'une popup Leaflet pour un point d'intérêt.
  // lat/lon sont optionnels : s'ils sont fournis, un lien discret pour
  // signaler une erreur à cet endroit sur OpenStreetMap est ajouté.
  window.gmPoiPopup = function (label, note, lat, lon) {
    var div = document.createElement("div");
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
  window.gmInitProfileHover = function (svg, map, data) {
    if (!svg || !map || !data || !data.length) return;

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
        mapMarker = L.circleMarker([0, 0], { radius: 7, className: "gm-hover-marker" });
      }
      return mapMarker;
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
      ensureMapMarker().setLatLng([point.lat, point.lon]).addTo(map);
    }

    function hide() {
      if (guide) guide.style.display = "none";
      if (dot) dot.style.display = "none";
      if (mapMarker) map.removeLayer(mapMarker);
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

        (markersByKind[kind] || []).forEach(function (m) {
          if (active) {
            if (!map.hasLayer(m)) m.addTo(map);
          } else if (map.hasLayer(m)) {
            map.removeLayer(m);
          }
        });

        if (svg) {
          var els = svg.querySelectorAll(".elevation-marker--" + kind);
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
    var done = function () {
      btn.textContent = "Lien copié !";
      btn.classList.add("share-btn--copied");
      setTimeout(function () {
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

  // Défilement en fondu des photos d'une sortie au survol de sa carte, sur
  // l'accueil (chaque .ride-card-photo[data-photo-carousel] contient
  // plusieurs .ride-card-photo-layer superposés, un par photo).
  document.addEventListener("DOMContentLoaded", function () {
    var cards = document.querySelectorAll("[data-photo-carousel]");
    cards.forEach(function (card) {
      var layers = card.querySelectorAll(".ride-card-photo-layer");
      if (layers.length < 2) return;

      var timer = null;
      var i = 0;

      card.addEventListener("mouseenter", function () {
        i = 0;
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

  // Filtre des sorties par tags sur la page d'accueil. Les cartes sont déjà
  // toutes dans le DOM (chaque .ride-card porte data-tags="tag1,tag2,...") ;
  // on affiche/masque en JS, sans rechargement. L'état est reflété dans le
  // hash de l'URL (#tags=...) pour rester partageable/rechargeable.
  document.addEventListener("DOMContentLoaded", function () {
    var filterBar = document.querySelector("[data-tag-filter]");
    if (!filterBar) return;

    var cards = Array.prototype.slice.call(document.querySelectorAll(".ride-card"));
    var allBtn = filterBar.querySelector("[data-tag-all]");
    var tagBtns = Array.prototype.slice.call(filterBar.querySelectorAll("[data-tag]"));
    var emptyMsg = document.querySelector("[data-tag-empty]");
    var active = new Set();

    function readHash() {
      var m = window.location.hash.match(/tags=([^&]*)/);
      if (!m || !m[1]) return;
      m[1].split(",").forEach(function (t) {
        t = decodeURIComponent(t).trim().toLowerCase();
        if (t) active.add(t);
      });
    }

    function writeHash() {
      var url = window.location.pathname + window.location.search;
      if (active.size) {
        url += "#tags=" + Array.from(active).map(encodeURIComponent).join(",");
      }
      window.history.replaceState(null, "", url);
    }

    function apply() {
      tagBtns.forEach(function (btn) {
        btn.classList.toggle("is-active", active.has(btn.getAttribute("data-tag")));
      });
      if (allBtn) allBtn.classList.toggle("is-active", active.size === 0);

      var visible = 0;
      var activeList = Array.from(active);
      cards.forEach(function (card) {
        var cardTags = (card.getAttribute("data-tags") || "").split(",").filter(Boolean);
        var matches = activeList.length === 0 || activeList.every(function (t) {
          return cardTags.indexOf(t) !== -1;
        });
        card.style.display = matches ? "" : "none";
        if (matches) visible++;
      });

      if (emptyMsg) emptyMsg.style.display = visible === 0 ? "" : "none";
    }

    filterBar.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-tag], [data-tag-all]");
      if (!btn) return;
      if (btn.hasAttribute("data-tag-all")) {
        active.clear();
      } else {
        var tag = btn.getAttribute("data-tag");
        if (active.has(tag)) active.delete(tag);
        else active.add(tag);
      }
      writeHash();
      apply();
    });

    readHash();
    apply();
  });
})();
