"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";

interface UnitData {
  id: string;
  name: string;
  type: string;
  status: "paid" | "maintenance" | "due" | "reconciled";
  statusText: string;
  metric: string;
  detail: string;
  floor: number;
}

const UNITS_DATA: Record<string, UnitData> = {
  "unit-4b": {
    id: "unit-4b",
    name: "Penthouse 4B",
    type: "3-Bed Executive Penthouse",
    status: "paid",
    statusText: "Rent Paid · KES 85,000",
    metric: "Active Lease · M-Pesa Auto-Match",
    detail: "Statement sent to Sarah K. · Zero arrears",
    floor: 3,
  },
  "unit-3b": {
    id: "unit-3b",
    name: "Suite 3B",
    type: "2-Bed Modern Suite",
    status: "reconciled",
    statusText: "Utilities Reconciled",
    metric: "Water & Power Sub-metered",
    detail: "Reading: 24.5 m³ · KES 3,850 billed",
    floor: 2,
  },
  "unit-2a": {
    id: "unit-2a",
    name: "Unit 2A",
    type: "2-Bed Garden Balcony",
    status: "maintenance",
    statusText: "Maintenance: In Progress",
    metric: "Plumbing Work Order #204",
    detail: "Assigned to vetted technician John M.",
    floor: 1,
  },
  "unit-1a": {
    id: "unit-1a",
    name: "Garden Suite 1A",
    type: "1-Bed Garden Residence",
    status: "due",
    statusText: "Rent Due in 3 Days",
    metric: "KES 42,000 · Due 5th",
    detail: "Automated SMS/Email notification queued",
    floor: 0,
  },
};

export function ArchitecturalHero3D() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [hoveredUnit, setHoveredUnit] = useState<UnitData | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isExploded, setIsExploded] = useState(false);
  const [isWebGLSupported, setIsWebGLSupported] = useState(true);

  // Expose toggle for button or external control
  const toggleExploded = useCallback(() => {
    setIsExploded((prev) => !prev);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    // Check WebGL availability
    try {
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (!gl) {
        setIsWebGLSupported(false);
        return;
      }
    } catch {
      setIsWebGLSupported(false);
      return;
    }

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const isMobile = window.innerWidth < 768;

    // Scene & Renderer
    const scene = new THREE.Scene();

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });

    const maxPr = isMobile ? 1.5 : Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(maxPr);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // Camera
    const width = container.clientWidth;
    const height = container.clientHeight;
    renderer.setSize(width, height);

    const camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 100);
    // Classical isometric viewpoint
    const initialCamPos = new THREE.Vector3(12.5, 10.5, 12.5);
    camera.position.copy(initialCamPos);
    const lookTarget = new THREE.Vector3(0, 2.2, 0);
    camera.lookAt(lookTarget);

    // Architectural Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.25);
    scene.add(ambientLight);

    // Warm Sun Directional
    const sunLight = new THREE.DirectionalLight(0xfff5e6, 2.4);
    sunLight.position.set(12, 22, 10);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 1024;
    sunLight.shadow.mapSize.height = 1024;
    sunLight.shadow.camera.near = 0.5;
    sunLight.shadow.camera.far = 40;
    sunLight.shadow.camera.left = -8;
    sunLight.shadow.camera.right = 8;
    sunLight.shadow.camera.top = 8;
    sunLight.shadow.camera.bottom = -8;
    sunLight.shadow.bias = -0.0005;
    scene.add(sunLight);

    // Soft Forest Fill
    const fillLight = new THREE.DirectionalLight(0x84b19f, 0.9);
    fillLight.position.set(-10, -5, -10);
    scene.add(fillLight);

    // Warm Amber Architectural Rim
    const rimLight = new THREE.PointLight(0xc6a66b, 1.4, 25);
    rimLight.position.set(-6, 8, 6);
    scene.add(rimLight);

    // --- MATERIALS (HODI Palette) ---
    const materials = {
      ground: new THREE.MeshStandardMaterial({
        color: 0x1f2e26, // deep slate forest ground
        roughness: 0.85,
        metalness: 0.1,
      }),
      lawn: new THREE.MeshStandardMaterial({
        color: 0x2b4235, // manicured landscape green
        roughness: 0.9,
      }),
      concreteBase: new THREE.MeshStandardMaterial({
        color: 0xe8e4dc, // crisp limestone / ivory concrete
        roughness: 0.45,
        metalness: 0.05,
      }),
      concreteFloor: new THREE.MeshStandardMaterial({
        color: 0xf3f0ea, // ivory floorplate
        roughness: 0.4,
        metalness: 0.05,
      }),
      woodLouvers: new THREE.MeshStandardMaterial({
        color: 0xc6a66b, // warm amber teak slats
        roughness: 0.6,
        metalness: 0.15,
      }),
      forestFrame: new THREE.MeshStandardMaterial({
        color: 0x163d32, // HODI brand dark forest
        roughness: 0.35,
        metalness: 0.3,
      }),
      glass: new THREE.MeshPhysicalMaterial({
        color: 0xdae8e5,
        transparent: true,
        opacity: 0.65,
        roughness: 0.1,
        metalness: 0.1,
        transmission: 0.6,
        ior: 1.5,
      }),
      glassHighlighted: new THREE.MeshPhysicalMaterial({
        color: 0xffe6a3,
        transparent: true,
        opacity: 0.85,
        roughness: 0.15,
        emissive: 0xc6a66b,
        emissiveIntensity: 0.45,
      }),
      foliage: new THREE.MeshStandardMaterial({
        color: 0x244f42,
        roughness: 0.8,
      }),
      bollardLight: new THREE.MeshStandardMaterial({
        color: 0xffe8b3,
        emissive: 0xffc766,
        emissiveIntensity: 1.2,
      }),
    };

    // --- PROCEDURAL ARCHITECTURAL COMPLEX ---
    const rootGroup = new THREE.Group();
    scene.add(rootGroup);

    // Ground Platform
    const groundGeo = new THREE.BoxGeometry(9.4, 0.35, 9.4);
    const groundMesh = new THREE.Mesh(groundGeo, materials.ground);
    groundMesh.position.y = -0.175;
    groundMesh.receiveShadow = true;
    rootGroup.add(groundMesh);

    // Landscaped Courtyard Insets
    const lawnGeo = new THREE.BoxGeometry(3.6, 0.05, 3.2);
    const lawn = new THREE.Mesh(lawnGeo, materials.lawn);
    lawn.position.set(-2.4, 0.025, 2.4);
    lawn.receiveShadow = true;
    rootGroup.add(lawn);

    // Minimalist Trees
    const treeGeo = new THREE.ConeGeometry(0.45, 1.2, 5);
    const trunkGeo = new THREE.CylinderGeometry(0.08, 0.08, 0.4, 5);
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5a483a, roughness: 0.9 });

    [
      [-3.2, 3.2],
      [-1.6, 3.4],
      [-3.4, 1.8],
    ].forEach(([tx, tz]) => {
      const tree = new THREE.Group();
      const trunk = new THREE.Mesh(trunkGeo, trunkMat);
      trunk.position.y = 0.2;
      trunk.castShadow = true;
      const crown = new THREE.Mesh(treeGeo, materials.foliage);
      crown.position.y = 0.8;
      crown.castShadow = true;
      tree.add(trunk, crown);
      tree.position.set(tx, 0, tz);
      rootGroup.add(tree);
    });

    // Pathway Bollard Lights
    const bollardGeo = new THREE.CylinderGeometry(0.06, 0.06, 0.35, 6);
    [
      [1.8, 3.4],
      [2.8, 3.4],
      [3.8, 3.4],
    ].forEach(([bx, bz]) => {
      const bollard = new THREE.Mesh(bollardGeo, materials.bollardLight);
      bollard.position.set(bx, 0.175, bz);
      rootGroup.add(bollard);
    });

    // Floor Groups (for exploded floorplan animations)
    const floorGroups: THREE.Group[] = [];
    const interactiveMeshes: THREE.Mesh[] = [];

    // Helper: Create a floorplate
    const createSlab = (width: number, depth: number, height: number = 0.2) => {
      const slab = new THREE.Mesh(
        new THREE.BoxGeometry(width, height, depth),
        materials.concreteFloor
      );
      slab.castShadow = true;
      slab.receiveShadow = true;
      return slab;
    };

    // --- LEVEL 0: Ground Floor (Unit 1A + Foyer) ---
    const floor0 = new THREE.Group();
    const slab0 = createSlab(5.6, 5.2, 0.22);
    slab0.position.y = 0.11;
    floor0.add(slab0);

    // Foyer Entry Frame
    const foyerFrame = new THREE.Mesh(
      new THREE.BoxGeometry(1.6, 1.4, 2.2),
      materials.forestFrame
    );
    foyerFrame.position.set(1.6, 0.85, 1.4);
    foyerFrame.castShadow = true;
    floor0.add(foyerFrame);

    // Unit 1A Volume
    const unit1AGeo = new THREE.BoxGeometry(2.8, 1.35, 3.6);
    const unit1AMesh = new THREE.Mesh(unit1AGeo, materials.glass);
    unit1AMesh.position.set(-1.1, 0.85, 0.4);
    unit1AMesh.castShadow = true;
    unit1AMesh.receiveShadow = true;
    unit1AMesh.userData = { unitId: "unit-1a", defaultMat: materials.glass };
    floor0.add(unit1AMesh);
    interactiveMeshes.push(unit1AMesh);

    // Timber slats on ground
    const slatsGeo = new THREE.BoxGeometry(0.08, 1.35, 1.8);
    const slats0 = new THREE.Mesh(slatsGeo, materials.woodLouvers);
    slats0.position.set(0.35, 0.85, 1.3);
    floor0.add(slats0);

    floor0.userData = { baseElevation: 0, targetElevation: 0 };
    rootGroup.add(floor0);
    floorGroups.push(floor0);

    // --- LEVEL 1: Floor 1 (Unit 2A Balcony) ---
    const floor1 = new THREE.Group();
    const slab1 = createSlab(5.8, 5.4, 0.22);
    slab1.position.y = 1.65;
    floor1.add(slab1);

    // Unit 2A Volume
    const unit2AGeo = new THREE.BoxGeometry(3.2, 1.35, 3.8);
    const unit2AMesh = new THREE.Mesh(unit2AGeo, materials.glass);
    unit2AMesh.position.set(-1.0, 2.45, 0.4);
    unit2AMesh.castShadow = true;
    unit2AMesh.userData = { unitId: "unit-2a", defaultMat: materials.glass };
    floor1.add(unit2AMesh);
    interactiveMeshes.push(unit2AMesh);

    // Cantilever Balcony with Green Frame
    const balconyGeo = new THREE.BoxGeometry(1.8, 0.12, 1.4);
    const balcony = new THREE.Mesh(balconyGeo, materials.forestFrame);
    balcony.position.set(-1.8, 1.8, 2.6);
    balcony.castShadow = true;
    floor1.add(balcony);

    // Balcony Railing Glass
    const railGeo = new THREE.BoxGeometry(1.8, 0.5, 0.06);
    const rail = new THREE.Mesh(railGeo, materials.glass);
    rail.position.set(-1.8, 2.1, 3.25);
    floor1.add(rail);

    floor1.userData = { baseElevation: 0, targetElevation: 0 };
    rootGroup.add(floor1);
    floorGroups.push(floor1);

    // --- LEVEL 2: Floor 2 (Unit 3B Executive) ---
    const floor2 = new THREE.Group();
    const slab2 = createSlab(5.6, 5.2, 0.22);
    slab2.position.y = 3.25;
    floor2.add(slab2);

    // Unit 3B Volume
    const unit3BGeo = new THREE.BoxGeometry(3.6, 1.35, 3.4);
    const unit3BMesh = new THREE.Mesh(unit3BGeo, materials.glass);
    unit3BMesh.position.set(0.6, 4.05, -0.4);
    unit3BMesh.castShadow = true;
    unit3BMesh.userData = { unitId: "unit-3b", defaultMat: materials.glass };
    floor2.add(unit3BMesh);
    interactiveMeshes.push(unit3BMesh);

    // Architectural Gold Teak Louvers
    for (let i = 0; i < 4; i++) {
      const louver = new THREE.Mesh(
        new THREE.BoxGeometry(0.06, 1.35, 0.45),
        materials.woodLouvers
      );
      louver.position.set(2.45, 4.05, -1.2 + i * 0.7);
      floor2.add(louver);
    }

    floor2.userData = { baseElevation: 0, targetElevation: 0 };
    rootGroup.add(floor2);
    floorGroups.push(floor2);

    // --- LEVEL 3: Rooftop / Penthouse (Unit 4B) ---
    const floor3 = new THREE.Group();
    const slab3 = createSlab(5.2, 4.8, 0.2);
    slab3.position.y = 4.85;
    floor3.add(slab3);

    // Unit 4B Penthouse Volume
    const unit4BGeo = new THREE.BoxGeometry(3.4, 1.25, 2.8);
    const unit4BMesh = new THREE.Mesh(unit4BGeo, materials.glass);
    unit4BMesh.position.set(-0.5, 5.6, -0.6);
    unit4BMesh.castShadow = true;
    unit4BMesh.userData = { unitId: "unit-4b", defaultMat: materials.glass };
    floor3.add(unit4BMesh);
    interactiveMeshes.push(unit4BMesh);

    // Rooftop Pergola Canopy
    const pergola = new THREE.Mesh(
      new THREE.BoxGeometry(2.4, 0.08, 1.8),
      materials.forestFrame
    );
    pergola.position.set(1.4, 6.2, 0.8);
    pergola.castShadow = true;
    floor3.add(pergola);

    // Rooftop Terrace Parapet
    const parapet = new THREE.Mesh(
      new THREE.BoxGeometry(5.2, 0.35, 0.08),
      materials.concreteBase
    );
    parapet.position.set(0, 5.1, 2.35);
    floor3.add(parapet);

    floor3.userData = { baseElevation: 0, targetElevation: 0 };
    rootGroup.add(floor3);
    floorGroups.push(floor3);

    // --- INTERACTIVE ORBIT & HOVER PHYSICS ---
    let targetAzimuth = 0;
    let currentAzimuth = 0;
    let targetElevation = 0;
    let currentElevation = 0;
    let isDragging = false;
    let previousPointerX = 0;
    let previousPointerY = 0;
    let hoveredMesh: THREE.Mesh | null = null;

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2(-999, -999);

    const minAzimuthAngle = -Math.PI / 4.5; // bounded to ~40 degrees left
    const maxAzimuthAngle = Math.PI / 4.5; // bounded to ~40 degrees right
    const minElevationAngle = -0.2;
    const maxElevationAngle = 0.35;

    // Pointer event handlers with passive touch guards
    const onPointerDown = (e: PointerEvent) => {
      isDragging = true;
      previousPointerX = e.clientX;
      previousPointerY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
    };

    const onPointerMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      if (isDragging) {
        const deltaX = e.clientX - previousPointerX;
        const deltaY = e.clientY - previousPointerY;
        previousPointerX = e.clientX;
        previousPointerY = e.clientY;

        targetAzimuth += deltaX * 0.005;
        targetAzimuth = Math.max(minAzimuthAngle, Math.min(maxAzimuthAngle, targetAzimuth));

        targetElevation += deltaY * 0.003;
        targetElevation = Math.max(minElevationAngle, Math.min(maxElevationAngle, targetElevation));
      }
    };

    const onPointerUp = (e: PointerEvent) => {
      isDragging = false;
      try {
        canvas.releasePointerCapture(e.pointerId);
      } catch {
        // ignore
      }
    };

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);

    // Resize handler
    const handleResize = () => {
      if (!container || !renderer) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    // IntersectionObserver to pause loop offscreen
    let isVisible = true;
    const observer = new IntersectionObserver(
      (entries) => {
        isVisible = entries[0].isIntersecting;
      },
      { threshold: 0.1 }
    );
    observer.observe(container);

    // --- ANIMATION RAF LOOP ---
    let animationId: number;
    const clock = new THREE.Clock();

    const render = () => {
      animationId = requestAnimationFrame(render);
      if (!isVisible) return;

      const elapsed = clock.getElapsedTime();

      // Gentle ambient idle sway if not dragging and motion is permitted
      if (!isDragging && !prefersReducedMotion) {
        const idleSway = Math.sin(elapsed * 0.45) * 0.06;
        targetAzimuth = THREE.MathUtils.lerp(targetAzimuth, idleSway, 0.03);
      }

      currentAzimuth = THREE.MathUtils.lerp(currentAzimuth, targetAzimuth, 0.08);
      currentElevation = THREE.MathUtils.lerp(currentElevation, targetElevation, 0.08);

      // Rotate root complex gently within bounds
      rootGroup.rotation.y = currentAzimuth;
      rootGroup.rotation.x = currentElevation;

      // Handle Exploded Floorplan lift
      const floorOffsets = isExploded ? [0, 0.9, 1.8, 2.7] : [0, 0, 0, 0];
      floorGroups.forEach((floor, idx) => {
        floor.position.y = THREE.MathUtils.lerp(floor.position.y, floorOffsets[idx], 0.09);
      });

      // Raycasting for unit hover tooltips
      raycaster.setFromCamera(pointer, camera);
      const intersects = raycaster.intersectObjects(interactiveMeshes);

      if (intersects.length > 0) {
        const hit = intersects[0].object as THREE.Mesh;
        if (hit !== hoveredMesh) {
          if (hoveredMesh) {
            hoveredMesh.material = hoveredMesh.userData.defaultMat;
          }
          hoveredMesh = hit;
          hit.material = materials.glassHighlighted;

          const unitKey = hit.userData.unitId as string;
          const data = UNITS_DATA[unitKey];
          if (data) {
            setHoveredUnit(data);
          }
        }

        // Project 3D center of hit object to screen 2D pixel coordinates
        if (hoveredMesh) {
          const worldPos = new THREE.Vector3();
          hoveredMesh.getWorldPosition(worldPos);
          worldPos.y += 0.8; // tooltip floating slightly above
          const projected = worldPos.clone().project(camera);
          const rect = container.getBoundingClientRect();
          const screenX = ((projected.x + 1) / 2) * rect.width;
          const screenY = ((-projected.y + 1) / 2) * rect.height;
          setTooltipPos({ x: screenX, y: screenY });
        }
      } else {
        if (hoveredMesh) {
          hoveredMesh.material = hoveredMesh.userData.defaultMat;
          hoveredMesh = null;
          setHoveredUnit(null);
        }
      }

      renderer.render(scene, camera);
    };

    render();

    return () => {
      cancelAnimationFrame(animationId);
      observer.disconnect();
      window.removeEventListener("resize", handleResize);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);

      // Dispose geometries and materials
      Object.values(materials).forEach((m) => m.dispose());
      scene.clear();
      renderer.dispose();
    };
  }, [isExploded]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full min-h-[460px] max-h-[600px] overflow-hidden rounded-2xl select-none touch-pan-y"
      style={{
        background:
          "linear-gradient(145deg, rgba(22, 61, 50, 0.95) 0%, rgba(15, 38, 32, 0.98) 100%)",
        border: "1px solid rgba(198, 166, 107, 0.22)",
        boxShadow:
          "inset 0 1px 1px rgba(255, 255, 255, 0.15), 0 24px 60px -12px rgba(10, 25, 20, 0.4)",
      }}
    >
      {/* Interactive 3D Canvas */}
      {isWebGLSupported ? (
        <canvas
          ref={canvasRef}
          className="w-full h-full cursor-grab active:cursor-grabbing block"
          style={{ touchAction: "pan-y" }}
          aria-label="Interactive 3D model of a modern apartment complex managed by HODI"
        />
      ) : (
        /* Fallback for environments where WebGL is unavailable */
        <div className="w-full h-full flex flex-col items-center justify-center p-8 text-center bg-teal text-white">
          <p className="font-editorial text-2xl mb-2">Connected Property Operations</p>
          <p className="text-sm opacity-80 max-w-sm">
            Interactive 3D visualization previewing real-time rental unit states and automated reconciliation.
          </p>
        </div>
      )}

      {/* Floating 3D Hover Tooltip (Glassmorphism) */}
      {hoveredUnit && (
        <div
          className="absolute pointer-events-none z-30 transition-all duration-150 ease-out -translate-x-1/2 -translate-y-full"
          style={{
            left: `${tooltipPos.x}px`,
            top: `${tooltipPos.y - 12}px`,
          }}
        >
          <div
            className="px-4 py-3 rounded-xl min-w-[220px] max-w-[280px] text-xs shadow-2xl border"
            style={{
              background: "rgba(22, 61, 50, 0.92)",
              backdropFilter: "blur(16px)",
              borderColor: "rgba(198, 166, 107, 0.35)",
              color: "#ffffff",
              boxShadow: "0 14px 34px -4px rgba(0, 0, 0, 0.5), inset 0 1px 1px rgba(255, 255, 255, 0.2)",
            }}
          >
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="font-bold tracking-tight text-white">{hoveredUnit.name}</span>
              <span
                className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider"
                style={{
                  background:
                    hoveredUnit.status === "paid"
                      ? "rgba(34, 197, 94, 0.2)"
                      : hoveredUnit.status === "maintenance"
                      ? "rgba(245, 158, 11, 0.2)"
                      : hoveredUnit.status === "reconciled"
                      ? "rgba(59, 130, 246, 0.2)"
                      : "rgba(198, 166, 107, 0.25)",
                  color:
                    hoveredUnit.status === "paid"
                      ? "#86efac"
                      : hoveredUnit.status === "maintenance"
                      ? "#fde047"
                      : hoveredUnit.status === "reconciled"
                      ? "#93c5fd"
                      : "#fef08a",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                }}
              >
                {hoveredUnit.statusText}
              </span>
            </div>
            <div className="text-[11px] text-emerald-100/90 font-medium">{hoveredUnit.metric}</div>
            <div className="text-[10px] text-emerald-200/60 mt-0.5">{hoveredUnit.detail}</div>
          </div>
        </div>
      )}

      {/* Interactive Controls Overlay */}
      <div className="absolute bottom-4 left-4 right-4 z-20 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-black/40 backdrop-blur-md border border-white/10 text-[11px] text-white/80">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
          <span>Interactive 3D · Drag to orbit · Hover units</span>
        </div>

        <button
          type="button"
          onClick={toggleExploded}
          className="pointer-events-auto px-3.5 py-1.5 rounded-lg text-xs font-semibold tracking-tight transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
          style={{
            background: isExploded
              ? "rgba(198, 166, 107, 0.95)"
              : "rgba(255, 255, 255, 0.15)",
            color: isExploded ? "#163d32" : "#ffffff",
            border: "1px solid rgba(255, 255, 255, 0.2)",
            backdropFilter: "blur(12px)",
          }}
          aria-pressed={isExploded}
        >
          {isExploded ? "Assemble Estate" : "Explode Floorplan"}
        </button>
      </div>
    </div>
  );
}
