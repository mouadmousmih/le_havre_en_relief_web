// Imports CDN directs — pas besoin d'importmap, compatible tous les mobiles
import * as THREE from 'https://unpkg.com/three@0.158.0/build/three.module.js';
import { STLLoader }     from 'https://unpkg.com/three@0.158.0/examples/jsm/loaders/STLLoader.js';
import { OrbitControls } from 'https://unpkg.com/three@0.158.0/examples/jsm/controls/OrbitControls.js';

let renderer = null, scene, camera, controls, currentMesh = null, animId = null;

function initRenderer(canvas) {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(0x111827);

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100000);

  // Éclairage : ambiant doux + deux directionnels pour donner du volume
  scene.add(new THREE.AmbientLight(0xffffff, 0.45));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.85);
  d1.position.set(1, 3, 2);
  scene.add(d1);
  const d2 = new THREE.DirectionalLight(0x6699ff, 0.25);
  d2.position.set(-2, -1, -2);
  scene.add(d2);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping  = true;
  controls.dampingFactor  = 0.06;
  controls.rotateSpeed    = 0.7;
  controls.zoomSpeed      = 1.2;

  window.addEventListener('resize', () => fitCanvas(canvas));
}

function fitCanvas(canvas) {
  const container = canvas.parentElement;
  const w = container.clientWidth  || window.innerWidth;
  const h = container.clientHeight || window.innerHeight * 0.8;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

function loadSTL(url) {
  if (currentMesh) {
    scene.remove(currentMesh);
    currentMesh.geometry.dispose();
    currentMesh = null;
  }

  const loader = new STLLoader();
  loader.load(url, (geo) => {
    geo.computeBoundingBox();
    const center = new THREE.Vector3();
    geo.boundingBox.getCenter(center);
    geo.translate(-center.x, -center.y, -center.z);

    currentMesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({
      color: 0xD4D4D8, specular: 0x555555, shininess: 35, side: THREE.DoubleSide,
    }));
    scene.add(currentMesh);

    const size = new THREE.Vector3();
    geo.boundingBox.getSize(size);
    const d = Math.max(size.x, size.y, size.z) * 1.6;
    camera.position.set(0, d * 0.6, d);
    controls.target.set(0, 0, 0);
    controls.update();
  });
}

function animate() {
  animId = requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

window.openViewer = function () {
  const modal = document.getElementById('viewer-modal');
  modal.classList.remove('hidden');

  // Double rAF : attend que le navigateur ait calculé le layout
  // (important sur mobile où la modale était display:none)
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const canvas = document.getElementById('viewer-canvas');
    if (!renderer) {
      initRenderer(canvas);
      animate();
    }
    fitCanvas(canvas);
    if (window._stlViewUrl) loadSTL(window._stlViewUrl);
  }));
};

window.closeViewer = function () {
  document.getElementById('viewer-modal').classList.add('hidden');
};
