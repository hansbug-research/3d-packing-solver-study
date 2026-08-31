import * as THREE from "three";

const count = 10_000;
const started = performance.now();
const geometry = new THREE.BoxGeometry(1, 1, 1);
const material = new THREE.MeshBasicMaterial({ color: 0x2f6f95 });
material.clippingPlanes = [new THREE.Plane(new THREE.Vector3(0, 1, 0), -0.5)];
const mesh = new THREE.InstancedMesh(geometry, material, count);
const transform = new THREE.Object3D();

for (let index = 0; index < count; index += 1) {
  transform.position.set(index % 100, Math.floor(index / 100) % 100, Math.floor(index / 10_000));
  transform.rotation.set(0, (index % 4) * Math.PI / 2, 0);
  transform.updateMatrix();
  mesh.setMatrixAt(index, transform.matrix);
}
mesh.instanceMatrix.needsUpdate = true;
mesh.updateMatrixWorld(true);
mesh.computeBoundingBox();
mesh.computeBoundingSphere();

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
camera.position.set(50, 50, 140);
camera.lookAt(50, 50, 0);
camera.updateMatrixWorld(true);
const raycaster = new THREE.Raycaster(
  new THREE.Vector3(50, 50, 140),
  new THREE.Vector3(0, 0, -1),
);
const hits = raycaster.intersectObject(mesh, false);

console.log(JSON.stringify({
  schema_version: 1,
  library: "three",
  version: THREE.REVISION,
  node: process.version,
  renderer_created: false,
  instances: count,
  bounding_box: mesh.boundingBox?.getSize(new THREE.Vector3()).toArray(),
  instance_id_found: hits[0]?.instanceId ?? null,
  clipping_planes: material.clippingPlanes.length,
  elapsed_ms: Number((performance.now() - started).toFixed(3)),
  heap_used_bytes: process.memoryUsage().heapUsed,
  scope: "non-rendering data-layer smoke; no GPU/FPS claim",
}));
