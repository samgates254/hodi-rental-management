"use client";

export function AmbientMeshBackground() {
  return (
    <div
      className="hodi-ambient fixed inset-0 pointer-events-none z-0 overflow-hidden select-none"
      aria-hidden="true"
    >
      {/* Primary drifting amber warmth */}
      <div
        className="hodi-ambient-orb absolute -top-[20%] -left-[10%] w-[65vw] h-[65vw] max-w-[900px] max-h-[900px] rounded-full opacity-40 blur-[120px] animate-ambient-drift-1"
        style={{
          background:
            "radial-gradient(circle, rgba(198, 166, 107, 0.14) 0%, rgba(198, 166, 107, 0.03) 60%, transparent 80%)",
        }}
      />

      {/* Secondary deep forest architectural depth */}
      <div
        className="hodi-ambient-orb absolute top-[35%] -right-[15%] w-[60vw] h-[60vw] max-w-[850px] max-h-[850px] rounded-full opacity-35 blur-[130px] animate-ambient-drift-2"
        style={{
          background:
            "radial-gradient(circle, rgba(22, 61, 50, 0.10) 0%, rgba(22, 61, 50, 0.02) 65%, transparent 80%)",
        }}
      />

      {/* Tertiary subtle golden horizon drift */}
      <div
        className="hodi-ambient-orb absolute bottom-[-15%] left-[25%] w-[50vw] h-[50vw] max-w-[700px] max-h-[700px] rounded-full opacity-30 blur-[110px] animate-ambient-drift-3"
        style={{
          background:
            "radial-gradient(circle, rgba(198, 166, 107, 0.10) 0%, rgba(22, 61, 50, 0.04) 50%, transparent 75%)",
        }}
      />
    </div>
  );
}
