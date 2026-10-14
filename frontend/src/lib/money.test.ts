import assert from "node:assert/strict";
import test from "node:test";
import {
  centsToDecimal,
  formatMinor,
  minorToShillingsInput,
  payableHalfShillings,
  payableWholeShillings,
  shillingsToCents,
  wholeShillingsToCents,
} from "./money.ts";

test("formats cents without binary floating point", () => {
  assert.equal(formatMinor(0), "KES 0.00");
  assert.equal(formatMinor(10), "KES 0.10");
  assert.equal(formatMinor(1), "KES 0.01");
  assert.equal(formatMinor(100000), "KES 1,000.00");
  assert.equal(formatMinor(-250), "-KES 2.50");
  assert.equal(formatMinor(4500000, "KES", { trailingZeros: false }), "KES 45,000");
  assert.equal(formatMinor(1010, "KES", { trailingZeros: false }), "KES 10.10");
  assert.equal(formatMinor(Number.NaN), "—");
  assert.equal(formatMinor(1.5), "—");
  assert.equal(centsToDecimal(1010), "10.10");
  assert.equal(centsToDecimal(4500000), "45000.00");
  assert.equal(centsToDecimal(-1), "-0.01");
});

test("parses shilling input on the decimal string and rejects extra precision", () => {
  assert.equal(shillingsToCents("0"), 0);
  assert.equal(shillingsToCents("0.1"), 10);
  assert.equal(shillingsToCents("0.10"), 10);
  assert.equal(shillingsToCents("10.10"), 1010);
  assert.equal(shillingsToCents("1.005"), undefined);
  assert.equal(shillingsToCents("10.999"), undefined);
  assert.equal(shillingsToCents("45,000"), 4500000);
  assert.equal(shillingsToCents("45 000.50"), 4500050);
  assert.equal(shillingsToCents("-1"), undefined);
  assert.equal(shillingsToCents("-0.01"), undefined);
  assert.equal(shillingsToCents(""), undefined);
  assert.equal(shillingsToCents("1e2"), undefined);
  assert.equal(shillingsToCents("10."), undefined);
  assert.equal(shillingsToCents("92233720368547758.08"), undefined);
  assert.equal(wholeShillingsToCents("1500"), 150000);
  assert.equal(wholeShillingsToCents("1500.50"), undefined);
  assert.equal(wholeShillingsToCents("0"), 0);
  assert.equal(minorToShillingsInput(1010), "10.10");
  assert.equal(minorToShillingsInput(4500000), "45000");
  assert.equal(minorToShillingsInput(1), "0.01");
});

test("offers whole-shilling payment amounts only when the split is exact", () => {
  assert.equal(payableWholeShillings(150000), 1500);
  assert.equal(payableWholeShillings(150050), undefined);
  assert.equal(payableWholeShillings(0), undefined);
  assert.equal(payableWholeShillings(-100), undefined);
  assert.equal(payableHalfShillings(200000), 1000);
  assert.equal(payableHalfShillings(150000), 750);
  assert.equal(payableHalfShillings(150100), undefined);
  assert.equal(payableHalfShillings(100), undefined);
  assert.equal(payableHalfShillings(10100), undefined);
});
