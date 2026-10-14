import assert from "node:assert/strict";
import test from "node:test";

import { daysUntilRentalDate, rentalBusinessDate } from "./rentalDate.ts";

test("rental business date uses Nairobi time before and after local midnight", () => {
  assert.equal(rentalBusinessDate(new Date("2026-10-14T20:59:59.999Z")), "2026-10-14");
  assert.equal(rentalBusinessDate(new Date("2026-10-14T21:00:00.000Z")), "2026-10-15");
  assert.equal(rentalBusinessDate(new Date("2026-10-14T22:30:00.000Z")), "2026-10-15");
});

test("rental business date rejects an invalid instant", () => {
  assert.throws(() => rentalBusinessDate(new Date(Number.NaN)), RangeError);
});

test("rental due-date distance uses Nairobi calendar days", () => {
  assert.equal(
    daysUntilRentalDate("2026-10-15", new Date("2026-10-14T22:30:00.000Z")),
    0,
  );
  assert.equal(
    daysUntilRentalDate("2026-10-15", new Date("2026-10-15T21:00:00.000Z")),
    -1,
  );
  assert.equal(
    daysUntilRentalDate("2026-10-15", new Date("2026-10-14T20:59:59.999Z")),
    1,
  );
  assert.equal(daysUntilRentalDate("2026-02-30", new Date("2026-02-01T12:00:00.000Z")), null);
});
