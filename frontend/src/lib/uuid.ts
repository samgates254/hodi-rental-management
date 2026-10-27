export function createUUID(): string {
  const cryptoAPI = globalThis.crypto;

  if (typeof cryptoAPI?.randomUUID === "function") {
    return cryptoAPI.randomUUID();
  }

  if (typeof cryptoAPI?.getRandomValues !== "function") {
    throw new Error(
      "Secure random number generation is unavailable. " +
        "Open HODI using HTTPS or localhost and try again.",
    );
  }

  const bytes = cryptoAPI.getRandomValues(new Uint8Array(16));

  // Set UUID version 4 and RFC 4122 variant bits.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  );

  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join(""),
  ].join("-");
}
