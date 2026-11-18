<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { positionStore } from '$lib/stores/position';
  import { logStore, type AttemptEntry } from '$lib/stores/log';
  import { moveAbs } from '$lib/api/control';
  import { toasts } from '$lib/stores/toast';

  let container: HTMLDivElement;
  let scene: any;
  let camera: any;
  let renderer: any;
  let controls: any;
  let probe: any;
  let scanBoxMesh: any;
  let highlightRing: any;
  let axesHelper: any;
  let zPlane: any;
  let trails: Record<string, { points: number[][]; mesh: any }> = {};
  let frameId: number;
  let THREE: any;

  // We auto-frame the camera once data first arrives (and on every scanBox
  // change), but NOT on every subsequent attempt point — that would yank the
  // view around mid-campaign. The Auto-fit button re-frames on demand.
  let framedOnce = false;

  export let scanBox: { width: number; height: number; depth: number } | null = null;

  // Physical bed size in mm. Drives grid extent, axis length, and default
  // camera framing so the scene matches the real lab geometry. Override per
  // deployment (the lab rig has a ~100mm working area).
  export let bedSize = 100;

  const OUTCOME_COLORS: Record<string, number> = {
    glitch: 0x00c853,
    hang: 0xff5252,
    crash: 0xf9a825,
    nothing: 0x607d8b,
  };

  onMount(async () => {
    THREE = await import('three');
    const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js');

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0b0f);

    camera = new THREE.PerspectiveCamera(40, container.clientWidth / container.clientHeight, 0.01, 5000);
    camera.position.set(bedSize * 0.8, bedSize * 0.8, bedSize * 0.8);
    camera.up.set(0, 0, 1);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambient);
    const dir = new THREE.DirectionalLight(0xffffff, 0.7);
    dir.position.set(bedSize * 0.1, bedSize * 0.2, bedSize * 0.3);
    scene.add(dir);

    // Axes emanate from the logical origin (bottom-left of the scan area).
    // Scaled with the probe (reactive below) so they don't dwarf a small scan.
    axesHelper = new THREE.AxesHelper(bedSize / 4);
    scene.add(axesHelper);

    // Two grids for multi-scale reference, both spanning [0, bedSize] in X/Y.
    // Fine: 1mm divisions, dim. Coarse overlay: 10mm divisions, brighter.
    const fineGrid = new THREE.GridHelper(bedSize, bedSize, 0x222637, 0x1c2030);
    fineGrid.rotation.x = Math.PI / 2;
    fineGrid.position.set(bedSize / 2, bedSize / 2, 0);
    scene.add(fineGrid);

    const coarseGrid = new THREE.GridHelper(bedSize, 10, 0x3a4258, 0x2e3447);
    coarseGrid.rotation.x = Math.PI / 2;
    // Tiny Z lift avoids z-fighting with the coincident fine-grid lines.
    coarseGrid.position.set(bedSize / 2, bedSize / 2, 0.02);
    scene.add(coarseGrid);

    // Base cone is "5mm" tall; the reactive probeScale below shrinks it to
    // match the scan extent so it doesn't visually swamp small grids.
    const coneGeo = new THREE.ConeGeometry(2, 5, 16);
    const coneMat = new THREE.MeshStandardMaterial({ color: 0x00d18f });
    probe = new THREE.Mesh(coneGeo, coneMat);
    probe.rotation.x = Math.PI;
    scene.add(probe);

    // Translucent horizontal plane that tracks the probe's Z, giving a visual
    // reference for height (otherwise Z is indistinguishable in the top view).
    // Colored blue→red across the scan's depth range (reactive below).
    const zPlaneMat = new THREE.MeshBasicMaterial({
      color: 0x2196f3,
      transparent: true,
      opacity: 0.12,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    zPlane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), zPlaneMat);
    scene.add(zPlane);

    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(bedSize / 2, bedSize / 2, 0);

    for (const outcome of Object.keys(OUTCOME_COLORS)) {
      trails[outcome] = { points: [], mesh: null };
    }

    renderer.domElement.addEventListener('dblclick', onDoubleClick);

    const ro = new ResizeObserver(() => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    ro.observe(container);

    function animate() {
      frameId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();
  });

  onDestroy(() => {
    if (frameId) cancelAnimationFrame(frameId);
    renderer?.dispose();
  });

  // ── Scan extent → inverse scaling ────────────────────────────────────────
  // XY bbox + Z range of the attempt cloud, recomputed when the log changes.
  $: pointsStats = (() => {
    const log = $logStore;
    if (log.length === 0) return null;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    for (const e of log) {
      if (e.x < minX) minX = e.x; if (e.x > maxX) maxX = e.x;
      if (e.y < minY) minY = e.y; if (e.y > maxY) maxY = e.y;
      if (e.z < minZ) minZ = e.z; if (e.z > maxZ) maxZ = e.z;
    }
    return { extentXY: Math.max(maxX - minX, maxY - minY), zMin: minZ, zMax: maxZ };
  })();

  // Characteristic XY size of the scan: the calibration box when present, else
  // the live attempt cloud's extent. Null only when there's no data at all.
  $: extentMax = scanBox
    ? Math.max(scanBox.width, scanBox.height)
    : pointsStats && pointsStats.extentXY > 0
    ? pointsStats.extentXY
    : null;

  // Probe ≈ 4% of the scan extent (2mm on a 50mm grid, 0.2mm on a 5mm grid);
  // 5mm fallback when no scan data exists yet. probeScale is relative to the
  // 5mm base cone, and is the common factor for rings/axes too.
  $: probeSize = extentMax != null && extentMax > 0 ? extentMax * 0.04 : 5;
  $: probeScale = probeSize / 5;

  $: if (probe) probe.scale.setScalar(probeScale);
  $: if (axesHelper) axesHelper.scale.setScalar(probeScale);

  $: if (probe && $positionStore) {
    probe.position.set($positionStore.x, $positionStore.y, $positionStore.z);
  }

  // ── Z reference plane: position, size, depth-coded color ──────────────────
  $: if (zPlane && $positionStore) {
    const cx = scanBox ? scanBox.width / 2 : bedSize / 2;
    const cy = scanBox ? scanBox.height / 2 : bedSize / 2;
    zPlane.position.set(cx, cy, $positionStore.z ?? 0);
  }
  $: if (zPlane) {
    const sz = scanBox
      ? Math.max(scanBox.width, scanBox.height) * 1.1
      : pointsStats && pointsStats.extentXY > 0
      ? pointsStats.extentXY * 1.1
      : bedSize;
    zPlane.scale.set(sz, sz, 1);
  }
  $: if (zPlane && THREE) updateZPlaneColor($positionStore?.z ?? 0);

  // ── Scan box outline + auto-frame on data arrival ─────────────────────────
  $: if (scene && scanBox) {
    updateScanBox(scanBox);
    autoFrame(); // re-frame on every scanBox change, per spec
    framedOnce = true;
  }

  let prevLogLen = 0;
  $: if (scene && $logStore.length > prevLogLen) {
    for (let i = prevLogLen; i < $logStore.length; i++) {
      addAttemptPoint($logStore[i]);
    }
    prevLogLen = $logStore.length;
    // Frame once the data has real extent (≥2 distinct points); later points
    // don't re-frame. autoFrame() returns false on a still-degenerate bbox.
    if (!framedOnce && autoFrame()) {
      framedOnce = true;
    }
  }

  function clamp(v: number, lo: number, hi: number): number {
    return Math.max(lo, Math.min(hi, v));
  }

  function updateZPlaneColor(z: number) {
    let frac = 0.5;
    if (scanBox && scanBox.depth > 0) {
      frac = clamp(z / scanBox.depth, 0, 1);
    } else if (pointsStats && pointsStats.zMax > pointsStats.zMin) {
      frac = clamp((z - pointsStats.zMin) / (pointsStats.zMax - pointsStats.zMin), 0, 1);
    }
    // blue (z_min) → red (z_max)
    const c = new THREE.Color(0x2196f3).lerp(new THREE.Color(0xff5252), frac);
    zPlane.material.color.copy(c);
  }

  function updateScanBox(box: { width: number; height: number; depth: number }) {
    if (scanBoxMesh) {
      scene.remove(scanBoxMesh);
      scanBoxMesh.geometry.dispose();
      scanBoxMesh.material.dispose();
    }
    const geo = new THREE.BoxGeometry(box.width, box.height, box.depth);
    const edges = new THREE.EdgesGeometry(geo);
    const mat = new THREE.LineBasicMaterial({ color: 0x00d18f, opacity: 0.6, transparent: true });
    scanBoxMesh = new THREE.LineSegments(edges, mat);
    scanBoxMesh.position.set(box.width / 2, box.height / 2, box.depth / 2);
    scene.add(scanBoxMesh);
  }

  function addAttemptPoint(entry: AttemptEntry) {
    if (!THREE) return;
    const outcome = entry.outcome;
    const trail = trails[outcome];
    if (!trail) return;
    trail.points.push([entry.x, entry.y, entry.z]);
    if (trail.mesh) {
      scene.remove(trail.mesh);
      trail.mesh.geometry.dispose();
      trail.mesh.material.dispose();
    }
    const positions = new Float32Array(trail.points.flat());
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    // World-sized points scaled with the scan extent (same factor as the
    // probe) so they read correctly once the camera auto-frames the data,
    // instead of dominating a small grid at a fixed pixel size.
    const mat = new THREE.PointsMaterial({
      color: OUTCOME_COLORS[outcome],
      size: Math.max(probeSize * 0.6, 0.02),
      sizeAttenuation: true,
    });
    trail.mesh = new THREE.Points(geo, mat);
    scene.add(trail.mesh);
  }

  export function highlightPoint(x: number, y: number, z: number) {
    if (!THREE) return;
    if (highlightRing) {
      scene.remove(highlightRing);
      highlightRing.geometry.dispose();
      highlightRing.material.dispose();
    }
    const geo = new THREE.RingGeometry(3, 4, 24);
    const mat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide });
    highlightRing = new THREE.Mesh(geo, mat);
    highlightRing.position.set(x, y, z + 0.01);
    highlightRing.scale.setScalar(probeScale); // match probe/points scaling
    scene.add(highlightRing);
    controls.target.set(x, y, z);
  }

  export function resetView() {
    if (!camera || !controls) return;
    camera.position.set(bedSize * 0.8, bedSize * 0.8, bedSize * 0.8);
    controls.target.set(bedSize / 2, bedSize / 2, 0);
  }

  // Bounding box of everything that matters: the scan box (if any) plus all
  // attempt points. Drives both auto-framing and the manual Auto-fit button.
  function buildBBox(): any {
    const box = new THREE.Box3();
    if (scanBox) {
      box.expandByPoint(new THREE.Vector3(0, 0, 0));
      box.expandByPoint(new THREE.Vector3(scanBox.width, scanBox.height, scanBox.depth));
    }
    for (const trail of Object.values(trails)) {
      for (const p of trail.points) {
        box.expandByPoint(new THREE.Vector3(p[0], p[1], p[2]));
      }
    }
    return box;
  }

  function autoFrame(notify = false): boolean {
    if (!THREE || !camera || !controls) return false;
    const box = buildBBox();
    if (box.isEmpty()) {
      if (notify) toasts.info('No data to frame yet');
      return false;
    }
    // Expand the bbox 10% so data isn't flush against the frame edge.
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).multiplyScalar(1.1);
    let maxDim = Math.max(size.x, size.y, size.z);
    if (maxDim < 1e-3) {
      // A single point (or coincident points) has no extent to frame yet —
      // don't latch on it. An explicit Auto-fit click still centers on it
      // using a small default span.
      if (!notify) return false;
      maxDim = 2;
    }
    // Camera distance so the bbox fills ~70% of the vertical viewport, placed
    // along the (1,1,1) isometric diagonal toward the bbox center.
    const fov = (camera.fov * Math.PI) / 180;
    const dist = maxDim / 2 / Math.tan(fov / 2) / 0.7;
    const off = dist / Math.sqrt(3);
    camera.position.set(center.x + off, center.y + off, center.z + off);
    controls.target.copy(center);
    return true;
  }

  export function autoFit() {
    autoFrame(true);
  }

  async function onDoubleClick(ev: MouseEvent) {
    if (!THREE || !camera || !renderer) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((ev.clientX - rect.left) / rect.width) * 2 - 1,
      -((ev.clientY - rect.top) / rect.height) * 2 + 1
    );
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, camera);
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    const point = new THREE.Vector3();
    if (raycaster.ray.intersectPlane(plane, point)) {
      try {
        await moveAbs(point.x, point.y, $positionStore.z);
      } catch {
        toasts.error('Move failed');
      }
    }
  }
</script>

<div class="scene-wrap">
  <div bind:this={container} class="scene"></div>
  <div class="overlay">
    <button on:click={resetView}>Reset view</button>
    <button on:click={autoFit}>Auto-fit to data</button>
  </div>
</div>

<style>
  .scene-wrap { position: relative; width: 100%; height: 100%; min-height: 300px; }
  .scene { width: 100%; height: 100%; background: #0a0b0f; }
  .overlay {
    position: absolute;
    top: 0.5rem;
    left: 0.5rem;
    display: flex;
    gap: 0.5rem;
  }
  .overlay button {
    font-size: 11px;
    padding: 0.25rem 0.5rem;
    opacity: 0.7;
  }
  .overlay button:hover { opacity: 1; }
</style>
