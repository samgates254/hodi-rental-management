"use client";

import { useEffect, useRef } from "react";

export function useMagnetic<T extends HTMLElement = HTMLElement>(
  strength: number = 0.35,
  maxDistance: number = 10
) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (prefersReducedMotion) return;

    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;
    let isHovering = false;
    let animId: number;

    const lerp = (a: number, b: number, n: number) => (1 - n) * a + n * b;

    const updatePosition = () => {
      currentX = lerp(currentX, targetX, 0.18);
      currentY = lerp(currentY, targetY, 0.18);

      if (el) {
        el.style.transform = `translate3d(${currentX.toFixed(2)}px, ${currentY.toFixed(2)}px, 0)`;
      }

      if (
        isHovering ||
        Math.abs(currentX - targetX) > 0.05 ||
        Math.abs(currentY - targetY) > 0.05
      ) {
        animId = requestAnimationFrame(updatePosition);
      } else {
        if (el) el.style.transform = "translate3d(0, 0, 0)";
      }
    };

    const handlePointerMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return; // Touch devices retain standard touch response
      const rect = el.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const distX = (e.clientX - centerX) * strength;
      const distY = (e.clientY - centerY) * strength;

      targetX = Math.max(-maxDistance, Math.min(maxDistance, distX));
      targetY = Math.max(-maxDistance, Math.min(maxDistance, distY));

      if (!isHovering) {
        isHovering = true;
        cancelAnimationFrame(animId);
        animId = requestAnimationFrame(updatePosition);
      }
    };

    const handlePointerLeave = () => {
      isHovering = false;
      targetX = 0;
      targetY = 0;
    };

    el.addEventListener("pointermove", handlePointerMove);
    el.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      cancelAnimationFrame(animId);
      el.removeEventListener("pointermove", handlePointerMove);
      el.removeEventListener("pointerleave", handlePointerLeave);
      if (el) el.style.transform = "";
    };
  }, [strength, maxDistance]);

  return ref;
}
