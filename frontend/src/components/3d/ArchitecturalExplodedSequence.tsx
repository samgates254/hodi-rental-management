"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Container } from "@/components/ui/Container";

const SEQUENCE_STEPS = [
  {
    step: "01",
    tag: "ESTATE STRUCTURE",
    title: "One unified digital record for every building.",
    description:
      "Map residential estates, commercial blocks, and multi-unit towers into clean hierarchical portfolios. Know exactly how many units are rentable, occupied, or scheduled for turnaround.",
    highlight: "Portfolio Organization & Unit Capacity",
  },
  {
    step: "02",
    tag: "TENANCY & LEASES",
    title: "Active lease history without the spreadsheet clutter.",
    description:
      "Assign tenants to units with immutable dates, security deposits, and customized rent schedules. Never double-book a unit or lose track of lease amendment terms.",
    highlight: "Atomic Unit Locking & Non-Overlapping Leases",
  },
  {
    step: "03",
    tag: "AUTOMATED RECONCILIATION",
    title: "Direct M-Pesa matching and strict conservation ledger.",
    description:
      "Every payment automatically matches against open invoices and water/electricity utility meters using HODI's double-entry allocation engine. Zero manual calculations.",
    highlight: "Real-Time Daraja STK Push & Water Sub-Meters",
  },
  {
    step: "04",
    tag: "COORDINATED CARE",
    title: "Vetted maintenance from report to resolution.",
    description:
      "When a tenant flags a repair, caretaker dispatch, quotation approvals, and work order receipts stay unified against the specific unit record.",
    highlight: "Emergency Priority Scoring & Quotation Approvals",
  },
];

export function ArchitecturalExplodedSequence() {
  const sectionRef = useRef<HTMLElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [scrollProgress, setScrollProgress] = useState(0);

  useEffect(() => {
    const section = sectionRef.current;
    const canvas = canvasRef.current;
    if (!section || !canvas) return;

    // Check WebGL
    try {
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (!gl) return;
    } catch {
      return;
    }

    const isMobile = window.innerWidth < 768;
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
    renderer.toneMappingExposure = 1.15;

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    renderer.setSize(width, height);

    const camera = new THREE.PerspectiveCamera(35, width / height, 0.1, 100);
    camera.position.set(13, 11, 13);
    camera.lookAt(new THREE.Vector3(0, 2.5, 0));

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4);
    scene.add(ambientLight);

    const sun = new THREE.DirectionalLight(0xfff3db, 2.6);
    sun.position.set(14, 24, 12);
    sun.castShadow = true;
    sun.shadow.mapSize.width = 1024;
    sun.shadow.mapSize.height = 1024;
    sun.shadow.bias = -0.0005;
    scene.add(sun);

    const forestBounce = new THREE.DirectionalLight(0x84b19f, 0.9);
    forestBounce.position.set(-10, -5, -10);
    scene.add(forestBounce);

    const amberAccent = new THREE.PointLight(0xc6a66b, 1.8, 30);
    amberAccent.position.set(-5, 9, 7);
    scene.add(amberAccent);

    // Materials
    const mPodium = new THREE.MeshStandardMaterial({ color: 0x1f2e26, roughness: 0.85 });
    const mSlab = new THREE.MeshStandardMaterial({ color: 0xf5f3ee, roughness: 0.35, metalness: 0.05 });
    const mForestFrame = new THREE.MeshStandardMaterial({ color: 0x163d32, roughness: 0.4, metalness: 0.25 });
    const mTeak = new THREE.MeshStandardMaterial({ color: 0xc6a66b, roughness: 0.55, metalness: 0.15 });
    const mGlass = new THREE.MeshPhysicalMaterial({
      color: 0xe6f2ee,
      transparent: true,
      opacity: 0.7,
      roughness: 0.1,
      metalness: 0.1,
      transmission: 0.5,
    });
    const mPulse = new THREE.MeshStandardMaterial({
      color: 0x86efac,
      emissive: 0x22c55e,
      emissiveIntensity: 0.8,
    });

    const rootGroup = new THREE.Group();
    scene.add(rootGroup);

    // Ground Podium
    const podium = new THREE.Mesh(new THREE.BoxGeometry(9.6, 0.35, 9.6), mPodium);
    podium.position.y = -0.175;
    podium.receiveShadow = true;
    rootGroup.add(podium);

    // Tiers
    const tiers: THREE.Group[] = [];

    // Floor 0 (Ground)
    const tier0 = new THREE.Group();
    const slab0 = new THREE.Mesh(new THREE.BoxGeometry(5.8, 0.22, 5.4), mSlab);
    slab0.position.y = 0.11;
    slab0.castShadow = true;
    slab0.receiveShadow = true;
    tier0.add(slab0);

    const gUnit1 = new THREE.Mesh(new THREE.BoxGeometry(2.8, 1.35, 3.6), mGlass);
    gUnit1.position.set(-1.1, 0.85, 0.4);
    gUnit1.castShadow = true;
    tier0.add(gUnit1);

    const fFrame = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.4, 2.2), mForestFrame);
    fFrame.position.set(1.6, 0.85, 1.4);
    tier0.add(fFrame);

    rootGroup.add(tier0);
    tiers.push(tier0);

    // Floor 1
    const tier1 = new THREE.Group();
    const slab1 = new THREE.Mesh(new THREE.BoxGeometry(6.0, 0.22, 5.6), mSlab);
    slab1.position.y = 1.65;
    slab1.castShadow = true;
    tier1.add(slab1);

    const unit2 = new THREE.Mesh(new THREE.BoxGeometry(3.2, 1.35, 3.8), mGlass);
    unit2.position.set(-1.0, 2.45, 0.4);
    unit2.castShadow = true;
    tier1.add(unit2);

    const balcony = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.12, 1.4), mForestFrame);
    balcony.position.set(-1.8, 1.8, 2.6);
    tier1.add(balcony);

    rootGroup.add(tier1);
    tiers.push(tier1);

    // Floor 2
    const tier2 = new THREE.Group();
    const slab2 = new THREE.Mesh(new THREE.BoxGeometry(5.8, 0.22, 5.4), mSlab);
    slab2.position.y = 3.25;
    slab2.castShadow = true;
    tier2.add(slab2);

    const unit3 = new THREE.Mesh(new THREE.BoxGeometry(3.6, 1.35, 3.4), mGlass);
    unit3.position.set(0.6, 4.05, -0.4);
    unit3.castShadow = true;
    tier2.add(unit3);

    for (let i = 0; i < 4; i++) {
      const louv = new THREE.Mesh(new THREE.BoxGeometry(0.06, 1.35, 0.45), mTeak);
      louv.position.set(2.45, 4.05, -1.2 + i * 0.7);
      tier2.add(louv);
    }

    // Glowing Utility Meter indicator on floor 2
    const meterNode = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 12), mPulse);
    meterNode.position.set(0.6, 4.2, 1.6);
    tier2.add(meterNode);

    rootGroup.add(tier2);
    tiers.push(tier2);

    // Floor 3 (Roof / Penthouse)
    const tier3 = new THREE.Group();
    const slab3 = new THREE.Mesh(new THREE.BoxGeometry(5.4, 0.2, 5.0), mSlab);
    slab3.position.y = 4.85;
    slab3.castShadow = true;
    tier3.add(slab3);

    const unit4 = new THREE.Mesh(new THREE.BoxGeometry(3.4, 1.25, 2.8), mGlass);
    unit4.position.set(-0.5, 5.6, -0.6);
    unit4.castShadow = true;
    tier3.add(unit4);

    const pergola = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.08, 1.8), mForestFrame);
    pergola.position.set(1.4, 6.2, 0.8);
    tier3.add(pergola);

    rootGroup.add(tier3);
    tiers.push(tier3);

    // Scroll tracker
    let targetProgress = 0;
    let currentProgress = 0;

    const handleScroll = () => {
      const rect = section.getBoundingClientRect();
      const scrollableDist = section.offsetHeight - window.innerHeight;
      if (scrollableDist <= 0) return;

      const progress = Math.min(1, Math.max(0, -rect.top / scrollableDist));
      targetProgress = progress;
      setScrollProgress(progress);

      const stepIndex = Math.min(
        SEQUENCE_STEPS.length - 1,
        Math.floor(progress * SEQUENCE_STEPS.length)
      );
      setActiveStepIndex(stepIndex);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();

    const handleResize = () => {
      if (!canvas || !renderer) return;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    let isVisible = true;
    const observer = new IntersectionObserver((entries) => {
      isVisible = entries[0].isIntersecting;
    });
    observer.observe(section);

    let animId: number;
    const render = () => {
      animId = requestAnimationFrame(render);
      if (!isVisible) return;

      currentProgress = THREE.MathUtils.lerp(currentProgress, targetProgress, 0.09);

      // Rotate camera angle based on scroll
      const baseRotation = -0.25 + currentProgress * 0.7;
      rootGroup.rotation.y = baseRotation;
      rootGroup.rotation.x = 0.02 + currentProgress * 0.05;

      // Explode floors proportionally
      const maxLifts = [0, 1.1, 2.2, 3.3];
      tiers.forEach((tier, idx) => {
        tier.position.y = THREE.MathUtils.lerp(
          tier.position.y,
          maxLifts[idx] * currentProgress,
          0.1
        );
      });

      renderer.render(scene, camera);
    };
    render();

    return () => {
      cancelAnimationFrame(animId);
      observer.disconnect();
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleResize);
      scene.clear();
      renderer.dispose();
    };
  }, []);

  const activeStep = SEQUENCE_STEPS[activeStepIndex];

  return (
    <section
      ref={sectionRef}
      className="relative min-h-[220vh] bg-[#163d32] text-white py-20 overflow-clip"
      aria-label="Interactive 3D architectural breakdown of HODI property management"
    >
      <div className="sticky top-0 h-screen w-full flex items-center justify-center overflow-hidden">
        <Container className="w-full h-full flex flex-col justify-between py-10 md:py-16">
          {/* Top Header */}
          <div className="flex items-center justify-between border-b border-white/15 pb-4">
            <div>
              <p className="text-[11px] uppercase tracking-widest text-amber-300 font-semibold mb-1">
                3D Architectural Sequence · Scroll-Linked Progression
              </p>
              <h2 className="font-editorial text-2xl md:text-3xl text-white">
                Deconstructing Modern Rental Operations
              </h2>
            </div>
            <div className="hidden sm:flex items-center gap-2 text-xs text-white/60">
              <span>Scroll to Explode</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
            </div>
          </div>

          {/* Main Grid: Left Story Copy, Right Sticky 3D Canvas */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center my-auto">
            {/* Left Story Card */}
            <div className="lg:col-span-5 z-20">
              <div
                className="hodi-glass-card p-6 md:p-8 rounded-2xl border"
                style={{
                  background: "rgba(22, 61, 50, 0.72)",
                  backdropFilter: "blur(20px)",
                  borderColor: "rgba(198, 166, 107, 0.25)",
                  boxShadow:
                    "inset 0 1px 1px rgba(255, 255, 255, 0.2), 0 20px 48px -8px rgba(0, 0, 0, 0.5)",
                }}
              >
                <div className="flex items-center justify-between gap-4 mb-4">
                  <span className="text-3xl font-editorial text-amber-300">
                    {activeStep.step}
                  </span>
                  <span className="px-2.5 py-1 rounded text-[11px] font-bold tracking-wider uppercase bg-white/10 text-emerald-300 border border-white/10">
                    {activeStep.tag}
                  </span>
                </div>

                <h3 className="font-editorial text-xl md:text-2xl text-white mb-3 leading-snug">
                  {activeStep.title}
                </h3>
                <p className="text-sm md:text-base text-emerald-100/80 leading-relaxed mb-6">
                  {activeStep.description}
                </p>

                <div className="pt-4 border-t border-white/15 flex items-center justify-between text-xs">
                  <span className="text-amber-200 font-medium">
                    {activeStep.highlight}
                  </span>
                  <span className="text-white/50">
                    Step {activeStepIndex + 1} of {SEQUENCE_STEPS.length}
                  </span>
                </div>
              </div>

              {/* Progress Steps Dots */}
              <div className="flex items-center gap-2 mt-6">
                {SEQUENCE_STEPS.map((s, idx) => (
                  <div
                    key={s.step}
                    className={`h-1.5 rounded-full transition-all duration-300 ${
                      idx === activeStepIndex
                        ? "w-8 bg-amber-400"
                        : "w-2 bg-white/20"
                    }`}
                  />
                ))}
              </div>
            </div>

            {/* Right Interactive 3D Canvas */}
            <div className="lg:col-span-7 h-[360px] sm:h-[440px] md:h-[520px] relative">
              <canvas
                ref={canvasRef}
                className="w-full h-full block rounded-2xl select-none"
                style={{ touchAction: "pan-y" }}
                aria-label="3D model dynamically exploding across floor tiers as page is scrolled"
              />
              <div className="absolute bottom-2 right-2 px-3 py-1 rounded bg-black/40 backdrop-blur-md text-[11px] text-white/60 border border-white/10">
                Floor Elevation: {Math.round(scrollProgress * 100)}%
              </div>
            </div>
          </div>

          {/* Bottom Indicators */}
          <div className="flex items-center justify-between text-xs text-white/50 pt-2 border-t border-white/10">
            <span>HODI Rental OS Architecture</span>
            <span>Exploded Floorplan Visualization</span>
          </div>
        </Container>
      </div>
    </section>
  );
}
