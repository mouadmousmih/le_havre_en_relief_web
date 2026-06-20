'use strict';

document.addEventListener('DOMContentLoaded', () => lucide.createIcons());

// ── Carte Leaflet ──
const map = L.map('map', { zoomControl: true }).setView([46.5, 2.3], 5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19,
}).addTo(map);

let zoneRect         = null;
let currentLat       = null;
let currentLon       = null;
let currentAddrName  = '';   // nom d'affichage Nominatim pour le nom du fichier

// ── Éléments DOM ──
const addressInput   = document.getElementById('address-input');
const searchBtn      = document.getElementById('search-btn');
const addressResult  = document.getElementById('address-result');
const generateBtn    = document.getElementById('generate-btn');

const progressBlock  = document.getElementById('progress-block');
const progressBar    = document.getElementById('progress-bar');
const progressMsg    = document.getElementById('progress-msg');
const stepEls        = document.querySelectorAll('.step');

const downloadBlock  = document.getElementById('download-block');
const downloadLink   = document.getElementById('download-link');
const fileInfo       = document.getElementById('file-info');

const errorBlock     = document.getElementById('error-block');
const errorMsg       = document.getElementById('error-msg');

// ── Helpers ──

function getRadius() {
  return parseInt(document.querySelector('input[name="radius"]:checked').value, 10);
}

function getVariant() {
  return document.querySelector('input[name="variant"]:checked').value;
}

function getServices() {
  return document.querySelector('input[name="services"]:checked').value;
}

function makeFilename(displayName, radius, variant) {
  // Garde rue + ville (2 premières parties de Nominatim), normalise en slug
  const parts = (displayName || 'maquette')
    .split(',')
    .slice(0, 2)
    .map(s => s.trim())
    .join(' ');
  const slug = parts
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')   // supprime les accents
    .replace(/[^a-z0-9\s]/g, '')
    .trim()
    .replace(/\s+/g, '_')
    .slice(0, 35);
  return `${slug || 'maquette'}_${radius}m_${variant}`;
}

function computeBboxBounds(lat, lon, radiusM) {
  const deltaLat = radiusM / 111320;
  const deltaLon = radiusM / (111320 * Math.cos(lat * Math.PI / 180));
  return [
    [lat - deltaLat, lon - deltaLon],
    [lat + deltaLat, lon + deltaLon],
  ];
}

function updateZoneRect() {
  if (currentLat === null) return;
  const bounds = computeBboxBounds(currentLat, currentLon, getRadius());
  if (zoneRect) map.removeLayer(zoneRect);
  zoneRect = L.rectangle(bounds, {
    color: '#3B82F6', weight: 2,
    fillColor: '#3B82F6', fillOpacity: 0.08,
  }).addTo(map);
  map.fitBounds(bounds, { padding: [100, 100], maxZoom: 13 });
}

function setStep(stepNum) {
  stepEls.forEach((el) => {
    const n = parseInt(el.dataset.step, 10);
    el.classList.remove('active', 'done');
    if (n < stepNum)   el.classList.add('done');
    if (n === stepNum) el.classList.add('active');
  });
  const pct = ((stepNum - 1) / (stepEls.length - 1)) * 100;
  progressBar.style.width = pct + '%';
}

function resetUI() {
  progressBlock.classList.add('hidden');
  downloadBlock.classList.add('hidden');
  errorBlock.classList.add('hidden');
  progressBar.style.width = '0%';
  progressMsg.textContent  = '';
  stepEls.forEach(el => el.classList.remove('active', 'done'));
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorBlock.classList.remove('hidden');
  progressBlock.classList.add('hidden');
  generateBtn.disabled = false;
}

// ── Géocodage ──

searchBtn.addEventListener('click', async () => {
  const q = addressInput.value.trim();
  if (!q) return;

  searchBtn.textContent = '...';
  searchBtn.disabled    = true;
  addressResult.classList.add('hidden');

  try {
    const res  = await fetch('/geocode?' + new URLSearchParams({ q }));
    const data = await res.json();

    if (data.found) {
      currentLat      = data.lat;
      currentLon      = data.lon;
      currentAddrName = data.display_name;
      addressResult.textContent = data.display_name;
      addressResult.classList.remove('hidden');
      generateBtn.disabled = false;
      updateZoneRect();
    } else {
      addressResult.textContent = data.error || 'Adresse introuvable';
      addressResult.classList.remove('hidden');
    }
  } catch {
    addressResult.textContent = 'Erreur de connexion';
    addressResult.classList.remove('hidden');
  }

  searchBtn.innerHTML = '<i data-lucide="search"></i> Chercher';
  searchBtn.disabled  = false;
  lucide.createIcons();
});

addressInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') searchBtn.click();
});

document.querySelectorAll('input[name="radius"]').forEach((radio) => {
  radio.addEventListener('change', updateZoneRect);
});

// ── Génération via SSE ──

generateBtn.addEventListener('click', () => {
  if (currentLat === null) return;

  resetUI();
  progressBlock.classList.remove('hidden');
  generateBtn.disabled = true;

  const params = new URLSearchParams({
    lat: currentLat, lon: currentLon,
    radius: getRadius(),
    variant: getVariant(),
    services: getServices(),
  });

  const es = new EventSource('/generate?' + params);

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === 'progress') {
      setStep(data.step);
      progressMsg.textContent = data.msg;
    }

    else if (data.type === 'done') {
      stepEls.forEach(el => { el.classList.remove('active'); el.classList.add('done'); });
      progressBar.style.width = '100%';
      progressMsg.textContent = data.msg;

      const filename = makeFilename(currentAddrName, getRadius(), getVariant());
      window._stlViewUrl = '/view/' + data.file;
      downloadLink.href  = '/download/' + data.file + '?name=' + encodeURIComponent(filename);
      fileInfo.textContent = `${filename}.stl — ${data.dims} — ${data.size_kb} Ko`;
      downloadBlock.classList.remove('hidden');
      generateBtn.disabled = false;
      es.close();
    }

    else if (data.type === 'error') {
      showError(data.msg);
      es.close();
    }
  };

  es.onerror = () => {
    showError('Connexion interrompue. Vérifiez que le serveur est en ligne.');
    es.close();
  };
});
