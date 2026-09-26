# Pure algorithm engines

This directory documents the deterministic, pure-Python algorithm layer under
`backend/`. It is independent of Django and the database. Public application
imports are through `engines.*`; canonical formulas and result types live in
`rental_os.algorithms.*`.

## Boundaries

- `rental_os.algorithms` is the sole source of algorithm behavior. Engine
  facades validate application-facing inputs, adapt records, delegate, and
  enforce boundary invariants; they must not reimplement formulas or ordering.
- These modules do not read or write a database, create models, emit API
  responses, authorize users, schedule work, access a clock, or perform I/O.
- Callers supply effective dates and timestamps explicitly. These functions
  return values only; persistence, posting, idempotency, and external effects
  belong to separately reviewed application services.
- Monetary values are integer KES cents (minor units), never floating-point
  money. `engines.money` exposes the canonical money validation and rounding
  helpers.
- Inputs that do not satisfy a facade's contract raise the relevant
  `ValueError` subclass. Errors are not converted into success-shaped defaults.

Run the pure algorithm and facade tests from `backend/`, where both public
package roots are importable:

```sh
python -m unittest discover -s rental_os/tests -p 'test*.py'
python -m unittest discover -s engines -p 'test*.py'
python -m unittest tests.unit.test_engine_import_boundary
```

## Public facades

### Money — `engines.money`

Exports `require_cents`, `round_half_up_div`, and `MoneyError`. Values must be
integers (booleans are rejected); cents are non-negative unless
`allow_zero=False`. Division rounding is exact integer ROUND_HALF_UP for a
non-negative numerator and positive denominator.

### Move-in proration — `engines.proration`

`prorate_move_in(monthly_rent_cents, move_in)` accepts non-negative integer
cents and an exact `datetime.date` (not `datetime`). Move-in is inclusive:
`occupied_days = days_in_month - move_in.day + 1`, and the charge is
ROUND_HALF_UP of monthly cents times occupied days divided by days in month.
Full-month occupancy returns the full rent. The immutable
`MoveInProration` result includes the dates/day counts, input rent, integer
`charge_cents`, and formatted `charge_kes`. Invalid input raises
`ProrationError` or `MoneyError`.

### Payment allocation — `engines.allocation`

`allocate(...)` accepts integer `payment_cents`, tenant/currency/source
identifiers, an exact effective date, an explicit ISO-8601 UTC execution
timestamp, a list/tuple of `AllocationCharge` records (or complete mappings),
and a policy ID/version. Production is locked to `CANONICAL_PRIORITY` v2.
Every charge must belong to the payment tenant. Allocation and tie-break
ordering are performed only by `rental_os.algorithms.allocation`; the facade
does not construct rankings or synthesize identifiers.

The result (`AllocationFacadeResult`) includes allocation lines, allocated and
overpayment cents, state, policy metadata, and balanced canonical postings.
The facade checks `allocated_cents + overpayment_cents == payment_cents` and
rejects any overpayment posting to account `2030`. Input and policy violations
raise `AllocationError` or `MoneyError`.

### Security-deposit application — `engines.deposit`

`apply_deposit(...)` uses the same explicit tenant, currency, source, effective
date, UTC timestamp, and locked policy contract, taking `held_cents` and
`DepositCharge` records (or complete mappings). Cross-tenant charges are
rejected. The immutable result separates `applied_cents` from
`refundable_cents`; their sum must equal held cents. Its `postings` tuple is
always empty: this calculation does not post refundable deposits or route
remainders to account `2020`. Application and refund persistence are outside
this layer.

### Delinquency — `engines.delinquency`

`assess(obligations=..., as_of=..., grace_days=...)` classifies posted open
balances against the caller-supplied civil date. The exact-date boundary and
non-negative integer grace-days are required. A balance is CURRENT through its
due date, GRACE_PERIOD through due date plus the inclusive grace interval, then
DELINQUENT; zero/closed balances are settled or excluded by lifecycle.
`DelinquencyResult` contains portfolio status, status-bucket cents, and
per-obligation assessments. It does not use the system clock or write ledger
state.

### Meter validation — `engines.meter`

`validate(captured=..., history=..., modulus=..., leak_factor_millis=...,
leak_min_units=...)` validates integer dial values and delegates to the
canonical validator. It identifies plausible rollover, tampered backward
movement, and suspected leaks against historical consumption; invalid
historical decreases raise `MeterHistoryError`. The result contains status,
consumption where available, rollover, baseline, and reason. It neither prices
consumption nor reads meter records.

### Tariff pricing — `engines.tariff`

`price(consumption=..., tariffs=..., as_of=...)` accepts integer non-negative
consumption and canonical `Tariff` / `TariffBand` records, validates integer
cents and effective dates, then delegates to the canonical pricing algorithm.
Exactly one tariff must cover `as_of`; cumulative bands are filled from the
bottom, and consumption beyond a capped schedule is rejected. Fixed and
minimum charges follow the canonical contract. The `TariffBill` exposes fixed,
energy, minimum, and total charge cents plus per-band detail. Meter validation
is a separate step; this facade performs no I/O.

### Maintenance priority — `engines.maintenance.priority`

`score(hazard=..., vulnerability=..., building_age_years=...,
age_band_value=...)` delegates to the canonical weighted score and emergency
override. Supply either a building age in years or its 1–5 age band, using
`None` for the other required argument. The result reports the normalized
bands, score in integer millis, rounded score, priority class, and whether the
emergency override applied. Priority class 1 is most urgent.

### Technician matching — `engines.maintenance.technician_matching`

`match(jobs=..., technicians=...)` accepts lists/tuples of canonical `Job` and
`Technician` records, then delegates to the deterministic maximum-weight
matching algorithm; it does not greedily rank jobs. The result is
`MatchResult`. Domain constraints and assignment weights are owned by the
canonical algorithm, not the facade.

## Tests and handoff

Canonical behavior tests live in `backend/rental_os/tests/`; boundary and
contract tests live beside each facade under `backend/engines/*/tests/`.
`backend/tests/unit/test_engine_import_boundary.py` checks that public facade
imports do not load Django.

No occupancy algorithm is provided by this integration. The existing
`engines.occupancy` package remains an empty placeholder; no behavior should be
inferred from it. Integration into Django models, API endpoints, permissions,
tenant-aware persistence, or transaction workflows requires a separate
application-layer change and review.
