"use client";

import { useEffect, useRef } from "react";

export function useTilt<T extends HTMLElement = HTMLElement>(
  maxRotation: number = 6,
  scale: number = 1.015
) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (prefersReducedMotion) return;

    let targetRotX = 0;
    let targetRotY = 0;
    let currentRotX = 0;
    let currentRotY = 0;
    let isHovering = false;
    let animId: number;

    const lerp = (a: number, b: number, n: number) => (1 - n) * a + n * b;

    const updateTilt = () => {
      currentRotX = lerp(currentRotX, targetRotX, 0.12);
      currentRotY = lerp(currentRotY, targetRotY, 0.12);

      if (el) {
        if (isHovering) {
          el.style.transform = `perspective(1000px) rotateX(${currentRotX.toFixed(2)}deg) rotateY(${currentRotY.toFixed(2)}deg) scale3d(${scale}, ${scale}, 1)`;
        } else {
          el.style.transform = `perspective(1000px) rotateX(${currentRotX.toFixed(2)}deg) rotateY(${currentRotY.toFixed(2)}deg) scale3d(1, 1, 1)`;
        }
      }

      if (
        isHovering ||
        Math.abs(currentRotX - targetRotX) > 0.05 ||
        Math.abs(currentRotY - targetRotY) > 0.05
      ) {
        animId = requestAnimationFrame(updateTilt);
      } else {
        if (el) el.style.transform = "";
      }
    };

    const handlePointerMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      const rect = el.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width; // 0 to 1
      const y = (e.clientY - rect.top) / rect.height; // 0 to 1

      // Cursor at top tilts card down (positive rotX); cursor at right tilts card to right (positive rotY)
      targetRotX = (0.5 - y) * (maxRotation * 2);
      targetRotY = (x - 0.5) * (maxRotation * 2);

      if (!isHovering) {
        isHovering = true;
        el.style.willChange = "transform";
        cancelAnimationFrame(animId);
        animId = requestAnimationFrame(updateTilt);
      }
    };

    const handlePointerLeave = () => {
      isHovering = false;
      targetRotX = 0;
      targetRotY = 0;
    };

    el.addEventListener("pointermove", handlePointerMove);
    el.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      cancelAnimationFrame(animId);
      el.removeEventListener("pointermove", handlePointerMove);
      el.removeEventListener("pointerleave", handlePointerLeave);
      if (el) {
        el.style.transform = "";
        el.style.willChange = "";
      }
    };
  }, [maxRotation, scale]);

  return ref;
}
