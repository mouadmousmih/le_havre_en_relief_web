/* Viewer 3D STL — utilise THREE global (chargé via <script> dans le HTML) */
'use strict';

let renderer = null, scene, camera, controls, currentMesh = null, animId = null;

function initRenderer(canvas) {
  const w = canvas.parentElement.clientWidth  || window.innerWidth;
  const h = canvas.parentElement.clientHeight || window.innerHeight;

  renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h, false);
  renderer.setClearColor(0x111827);

  scene  = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100000);

  scene.add(new THREE.AmbientLight(0xffffff, 0.45));

  var d1 = new THREE.DirectionalLight(0xffffff, 0.85);
  d1.position.set(1, 3, 2);
  scene.add(d1);

  var d2 = new THREE.DirectionalLight(0x6699ff, 0.25);
  d2.position.set(-2, -1, -2);
  scene.add(d2);

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.rotateSpeed   = 0.7;
  controls.zoomSpeed     = 1.2;

  window.addEventListener('resize', function() { fitCanvas(); });
}

function fitCanvas() {
  if (!renderer) return;
  var canvas    = document.getElementById('viewer-canvas');
  var container = canvas.parentElement;
  var w = container.clientWidth  || window.innerWidth;
  var h = container.clientHeight || window.innerHeight;
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

  var loader = new THREE.STLLoader();
  loader.load(url, function(geo) {
    geo.computeBoundingBox();
    var center = new THREE.Vector3();
    geo.boundingBox.getCenter(center);
    geo.translate(-center.x, -center.y, -center.z);

    var mat = new THREE.MeshPhongMaterial({
      color: 0xD4D4D8, specular: 0x555555, shininess: 35,
      side: THREE.DoubleSide,
    });
    currentMesh = new THREE.Mesh(geo, mat);
    scene.add(currentMesh);

    var size = new THREE.Vector3();
    geo.boundingBox.getSize(size);
    var d = Math.max(size.x, size.y, size.z) * 1.6;
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

window.openViewer = function() {
  var modal = document.getElementById('viewer-modal');
  modal.classList.remove('hidden');

  // setTimeout laisse le navigateur calculer le layout avant d'initialiser WebGL
  setTimeout(function() {
    var canvas = document.getElementById('viewer-canvas');
    if (!renderer) {
      initRenderer(canvas);
      animate();
    }
    fitCanvas();
    if (window._stlViewUrl) loadSTL(window._stlViewUrl);
  }, 80);
};

window.closeViewer = function() {
  document.getElementById('viewer-modal').classList.add('hidden');
};
