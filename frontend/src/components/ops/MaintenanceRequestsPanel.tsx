"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { clientApi } from "@/lib/clientApi";
import { useRequiresApproval } from "@/hooks/useRequiresApproval";
import { apiErrorMessage, asList, formatWhen, getList, humanize, type ListPayload } from "@/lib/opsApi";
import { MAINTENANCE_ASSIGNEE_STAFF_ROLES } from "@/lib/organizationRoles";
import { rentalBusinessDate } from "@/lib/rentalDate";
import "./ops.css";

type UnitRow = { id: number | string; building: number | string; name: string };
type BuildingRow = { id: number | string; property: number | string; name: string };
type PropertyRow = { id: number | string; organization: number | string; name: string };
type TenantRow = { id: number | string; organization: number | string; full_name?: string; first_name: string; last_name: string };
type StaffRow = { user: number | string; first_name?: string; last_name?: string; username?: string; role: string; organization: number | string; is_active: boolean };
type MembershipRow = { user: number | string; role: string; organization: number | string; is_active: boolean };

type WorkOrder = {
  id: number | string;
  assignee: number | null;
  assignee_name?: string | null;
  assigned_to_me?: boolean;
  status: string;
  assignment_status?: "NOT_REQUIRED" | "PENDING" | "ACCEPTED" | "DECLINED" | null;
  assignment_responded_at?: string | null;
  assignment_decline_reason?: string;
  assigned_at?: string | null;
  completed_at?: string | null;
  notes?: string;
};

type RepairQuotation = {
  id: number | string;
  labour_estimate_cents: number;
  materials_estimate_cents: number;
  other_estimate_cents: number;
  total_estimate_cents: number;
  explanation: string;
  status: string;
  decision_notes?: string;
  revision_of?: number | null;
  has_itemized_lines?: boolean;
  lines?: Array<{
    id: number;
    category: "MATERIAL" | "LABOUR" | "TRANSPORT" | "OTHER";
    description: string;
    quantity: string;
    unit: string;
    unit_price_cents: number;
    line_total_cents: number;
  }>;
};

type QuotationDraftLine = {
  category: "MATERIAL" | "LABOUR" | "TRANSPORT" | "OTHER";
  description: string;
  quantity: string;
  unit: string;
  unit_price_cents: string;
};

const emptyQuotationLine = (): QuotationDraftLine => ({
  category: "MATERIAL", description: "", quantity: "1", unit: "item", unit_price_cents: "0",
});

function quotationLineMinor(line: QuotationDraftLine): bigint {
  const quantityMatch = /^(\d+)(?:\.(\d{0,3}))?$/.exec(line.quantity.trim());
  const price = /^\d+$/.test(line.unit_price_cents) ? BigInt(line.unit_price_cents) : BigInt(0);
  if (!quantityMatch || price === BigInt(0)) return BigInt(0);
  const quantityMilli = BigInt(quantityMatch[1]) * BigInt(1000) + BigInt((quantityMatch[2] ?? "").padEnd(3, "0") || "0");
  return (quantityMilli * price + BigInt(500)) / BigInt(1000);
}

function formatMinorAmount(value: bigint) {
  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: "KES",
  }).format(Number(value) / 100);
}

function makeIdempotencyKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, token => {
    const value = Math.floor(Math.random() * 16);
    return (token === "x" ? value : (value & 0x3) | 0x8).toString(16);
  });
}

function quantityMilli(value: string): bigint | null {
  const match = /^(\d+)(?:\.(\d{0,3}))?$/.exec(value.trim());
  if (!match) return null;
  return BigInt(match[1]) * BigInt(1000) + BigInt((match[2] ?? "").padEnd(3, "0") || "0");
}

function formatQuantityMilli(value: bigint) {
  const whole = value / BigInt(1000);
  const fractional = String(value % BigInt(1000)).padStart(3, "0").replace(/0+$/, "");
  return fractional ? `${whole}.${fractional}` : String(whole);
}

type RepairCompletion = {
  id: number | string;
  diagnosis: string;
  failure_category: string;
  resolution_summary: string;
  outcome: string;
  actual_total_cents: number | null;
  status: string;
  follow_up_required: boolean;
  follow_up_reason?: string;
  verified_at?: string | null;
  verified_by_name?: string | null;
  can_add_evidence?: boolean;
};

type CompletionEvidence = {
  id: number;
  category: "BEFORE_PHOTO" | "AFTER_PHOTO" | "WORK_DOCUMENT" | "MATERIAL_RECEIPT" | "OTHER";
  caption: string;
  evidence_reference: string;
  recorded_by_name: string;
  created_at: string;
};

type TurnoverChecklist = { item_key: string; label: string; passed: boolean; notes: string };
type TurnoverAssessment = {
  id: number;
  property_name: string;
  building_name: string;
  unit_name: string;
  status: "REQUESTED" | "FAILED" | "READY";
  outstanding_issues: string;
  requested_by_name: string;
  requested_at: string;
  assessed_by_name: string | null;
  assessed_at: string | null;
  revision_of: number | null;
  checklist_items: Array<{ id: number; item_key: string; label: string; passed: boolean; notes: string }>;
};

type TurnoverState = { assessments: TurnoverAssessment[]; can_request: boolean; can_confirm_ready: boolean };

type MaterialPurchase = {
  id: number;
  quotation: number;
  quotation_line: number;
  supplier_name: string;
  supplier_reference: string;
  description: string;
  quantity: string;
  received_quantity: string;
  unit: string;
  unit_price_cents: number | null;
  purchase_total_cents: number | null;
  purchase_date: string;
  status: "RECORDED" | "PARTIALLY_RECEIVED" | "RECEIVED";
  overrun_reason: string;
  can_acknowledge_receipt: boolean;
  receipts: Array<{ id: number; quantity: string; evidence_reference: string; notes: string; acknowledged_by_name: string; created_at: string }>;
};

type MaterialPurchaseState = {
  purchases: MaterialPurchase[];
  can_record_purchase: boolean;
  can_acknowledge_receipt: boolean;
  cost_overrun_authorization_required: boolean;
};

function remainingPurchaseQuantity(purchase: MaterialPurchase) {
  const ordered = quantityMilli(purchase.quantity) ?? BigInt(0);
  const received = quantityMilli(purchase.received_quantity) ?? BigInt(0);
  return ordered > received ? formatQuantityMilli(ordered - received) : "0";
}

type JobCostSummary = {
  approved_total_cents: number | null;
  approved_material_budget_cents: number | null;
  approved_quotation_is_current: boolean;
  recorded_purchase_total_cents: number;
  recorded_labour_actual_cents: number;
  reported_material_consumption_cost_cents: number;
  recorded_other_actual_cents: number;
  recorded_job_cost_cents: number;
  variance_cents: number | null;
  over_budget: boolean;
  cost_summary_status: "PROVISIONAL" | "FINAL_RECORDED";
  materials_reconciled: boolean;
  supplier_payment_status: "NOT_TRACKED";
};

type MaintenanceRequestRow = {
  id: number | string;
  organization: number | string;
  unit: number | string;
  tenant: number | string | null;
  title: string;
  description: string;
  status: string;
  category: string;
  hazard: number;
  vulnerability: number;
  priority_class: number;
  emergency_override: boolean;
  safety_override: boolean;
  safety_override_reason?: string;
  triage_notes?: string;
  requires_approval: boolean;
  follow_up_at?: string | null;
  follow_up_reason?: string;
  follow_up_assignee_name?: string | null;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
  closed_at?: string | null;
  work_order?: WorkOrder | null;
  quotations?: RepairQuotation[];
  completion?: RepairCompletion | null;
};

type Assignee = { id: string; label: string };
type SupplierOption = { id: number; organization: number; business_name: string };

export default function MaintenanceRequestsPanel({
  organizationId,
  canWrite,
}: {
  organizationId: string;
  canWrite: boolean;
}) {
  const [requests, setRequests] = useState<MaintenanceRequestRow[]>([]);
  const [units, setUnits] = useState<UnitRow[]>([]);
  const [buildings, setBuildings] = useState<BuildingRow[]>([]);
  const [properties, setProperties] = useState<PropertyRow[]>([]);
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierOption[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [declineReason, setDeclineReason] = useState("");
  const [quotationLines, setQuotationLines] = useState<QuotationDraftLine[]>([emptyQuotationLine()]);
  const [quotationExplanation, setQuotationExplanation] = useState("");
  const [editingQuotationId, setEditingQuotationId] = useState<string | null>(null);
  const [materialPurchases, setMaterialPurchases] = useState<MaterialPurchaseState | null>(null);
  const [jobCostSummary, setJobCostSummary] = useState<JobCostSummary | null>(null);
  const [purchaseLoading, setPurchaseLoading] = useState(false);
  useEffect(() => {
    clientApi.get<SupplierOption[]>("/api/v1/marketplace/commerce/suppliers/")
      .then(result => setSuppliers(result.data.filter(item => String(item.organization) === organizationId)))
      .catch(() => setSuppliers([]));
  }, [organizationId]);
  const [purchaseError, setPurchaseError] = useState("");
  const [purchaseNotice, setPurchaseNotice] = useState("");
  const [purchaseIdempotencyKey, setPurchaseIdempotencyKey] = useState(makeIdempotencyKey);
  const [purchaseOverrunReason, setPurchaseOverrunReason] = useState("");
  const [receiptIdempotencyKeys, setReceiptIdempotencyKeys] = useState<Record<string, string>>({});
  const [costOverrunReason, setCostOverrunReason] = useState("");
  const [completionEvidence, setCompletionEvidence] = useState<CompletionEvidence[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const [evidenceNotice, setEvidenceNotice] = useState("");
  const [turnoverState, setTurnoverState] = useState<TurnoverState | null>(null);
  const [turnoverLoading, setTurnoverLoading] = useState(false);
  const [turnoverError, setTurnoverError] = useState("");
  const [turnoverNotice, setTurnoverNotice] = useState("");
  const [turnoverKey, setTurnoverKey] = useState(makeIdempotencyKey);
  const [turnoverChecklist, setTurnoverChecklist] = useState<TurnoverChecklist[]>([{ item_key: "", label: "", passed: false, notes: "" }]);
  const [turnoverIssues, setTurnoverIssues] = useState("");
  const [confirmTurnoverReady, setConfirmTurnoverReady] = useState(false);

  const load = useCallback(async () => {
    if (!organizationId) return;
    setLoading(true);
    setError("");
    try {
      const requestRows = await getList<MaintenanceRequestRow>("/api/v1/maintenance/requests/queue/");
      setRequests(requestRows.filter(row => String(row.organization) === organizationId));
      if (!canWrite) return;
      const [unitRows, buildingRows, propertyRows, tenantRows] = await Promise.all([
        getList<UnitRow>("/api/v1/properties/units/"),
        getList<BuildingRow>("/api/v1/properties/buildings/"),
        getList<PropertyRow>("/api/v1/properties/"),
        getList<TenantRow>("/api/v1/tenants/"),
      ]);
      const orgProperties = propertyRows.filter(row => String(row.organization) === organizationId);
      const propertyIds = new Set(orgProperties.map(row => String(row.id)));
      const orgBuildings = buildingRows.filter(row => propertyIds.has(String(row.property)));
      const buildingIds = new Set(orgBuildings.map(row => String(row.id)));
      setProperties(orgProperties);
      setBuildings(orgBuildings);
      setUnits(unitRows.filter(row => buildingIds.has(String(row.building))));
      setTenants(tenantRows.filter(row => String(row.organization) === organizationId));

      let people: Assignee[] = [];
      try {
        const staff = await clientApi.get<ListPayload<StaffRow>>("/api/v1/organizations/staff/", {
          params: { organization: organizationId },
        });
        people = asList(staff.data).filter(row =>
          row.is_active && MAINTENANCE_ASSIGNEE_STAFF_ROLES.includes(row.role as typeof MAINTENANCE_ASSIGNEE_STAFF_ROLES[number]),
        ).map(row => ({
          id: String(row.user),
          label: [row.first_name, row.last_name].filter(Boolean).join(" ") || row.username || `User ${row.user}`,
        }));
      } catch {
        const memberships = await getList<MembershipRow>("/api/v1/organizations/memberships/");
        people = memberships
          .filter(row => String(row.organization) === organizationId && row.is_active)
          .map(row => ({ id: String(row.user), label: `User ${row.user} · ${humanize(row.role)}` }));
      }
      setAssignees(people);
    } catch (loadError) {
      setError(apiErrorMessage(loadError, "Maintenance requests couldn’t be loaded."));
    } finally {
      setLoading(false);
    }
  }, [canWrite, organizationId]);

  const loadMaterialData = useCallback(async (requestId: string) => {
    const requestRow = requests.find(row => String(row.id) === requestId);
    const canReadMaterials = canWrite || Boolean(requestRow?.work_order?.assigned_to_me);
    if (!requestId || !canReadMaterials) return;
    setPurchaseLoading(true);
    setPurchaseError("");
    try {
      const response = await clientApi.get<MaterialPurchaseState>(`/api/v1/maintenance/requests/${requestId}/purchases/`);
      setMaterialPurchases(response.data);
      if (response.data.can_record_purchase) {
        const summary = await clientApi.get<JobCostSummary>(`/api/v1/maintenance/requests/${requestId}/cost-summary/`);
        setJobCostSummary(summary.data);
      } else {
        setJobCostSummary(null);
      }
    } catch (loadError) {
      setPurchaseError(apiErrorMessage(loadError, "Job material records couldn’t be loaded."));
      setMaterialPurchases(null);
      setJobCostSummary(null);
    } finally {
      setPurchaseLoading(false);
    }
  }, [canWrite, requests]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setEditingQuotationId(null);
    setQuotationLines([emptyQuotationLine()]);
    setQuotationExplanation("");
    setPurchaseIdempotencyKey(makeIdempotencyKey());
    setPurchaseOverrunReason("");
    setReceiptIdempotencyKeys({});
    setCostOverrunReason("");
    setPurchaseNotice("");
    setPurchaseError("");
    if ((canWrite || requests.some(row => String(row.id) === selectedId && row.work_order?.assigned_to_me)) && selectedId) void loadMaterialData(selectedId);
    else {
      setMaterialPurchases(null);
      setJobCostSummary(null);
    }
  }, [canWrite, loadMaterialData, requests, selectedId]);

  const selected = requests.find(row => String(row.id) === selectedId) ?? null;
  const loadSupplementalData = useCallback(async (requestId: string, completionId: number | string | undefined) => {
    setEvidenceError("");
    setTurnoverError("");
    if (completionId && (canWrite || requests.some(row => String(row.id) === requestId && row.work_order?.assigned_to_me))) {
      setEvidenceLoading(true);
      try {
        const response = await clientApi.get<CompletionEvidence[]>(`/api/v1/maintenance/requests/${requestId}/completions/${completionId}/evidence/`);
        setCompletionEvidence(response.data);
      } catch (loadError) {
        setCompletionEvidence([]);
        setEvidenceError(apiErrorMessage(loadError, "Completion evidence couldn’t be loaded."));
      } finally {
        setEvidenceLoading(false);
      }
    } else {
      setCompletionEvidence([]);
    }
    if (canWrite) {
      setTurnoverLoading(true);
      try {
        const response = await clientApi.get<TurnoverState>(`/api/v1/maintenance/requests/${requestId}/turnover-assessments/`);
        setTurnoverState(response.data);
      } catch (loadError) {
        setTurnoverState(null);
        setTurnoverError(apiErrorMessage(loadError, "Turnover history couldn’t be loaded."));
      } finally {
        setTurnoverLoading(false);
      }
    } else {
      setTurnoverState(null);
    }
  }, [canWrite, requests]);

  useEffect(() => {
    if (!selectedId) {
      setCompletionEvidence([]);
      setTurnoverState(null);
      return;
    }
    void loadSupplementalData(selectedId, selected?.completion?.id);
  }, [loadSupplementalData, selected?.completion?.id, selectedId]);

  const latestQuotation = selected?.quotations?.[0] ?? null;
  const requiresApproval = useRequiresApproval(latestQuotation?.status);
  const currentApprovedMaterialLines = latestQuotation?.status === "APPROVED"
    ? (latestQuotation.lines ?? []).filter(line => line.category === "MATERIAL")
    : [];
  const quotationSubtotals = useMemo(() => {
    const totals = { LABOUR: BigInt(0), MATERIAL: BigInt(0), OTHER: BigInt(0) };
    quotationLines.forEach(line => {
      const total = quotationLineMinor(line);
      if (line.category === "LABOUR") totals.LABOUR += total;
      else if (line.category === "MATERIAL") totals.MATERIAL += total;
      else totals.OTHER += total;
    });
    return totals;
  }, [quotationLines]);
  const unitLabel = useMemo(() => {
    const map = new Map<string, string>();
    units.forEach(unit => {
      const building = buildings.find(item => String(item.id) === String(unit.building));
      const property = properties.find(item => String(item.id) === String(building?.property));
      map.set(String(unit.id), `${property?.name ?? "Property"} · ${unit.name}`);
    });
    return map;
  }, [buildings, properties, units]);
  const tenantLabel = useMemo(() => {
    const map = new Map<string, string>();
    tenants.forEach(tenant => {
      map.set(String(tenant.id), tenant.full_name || `${tenant.first_name} ${tenant.last_name}`.trim());
    });
    return map;
  }, [tenants]);

  function assigneeName(id: number | null | undefined) {
    if (id == null) return "Unassigned";
    return assignees.find(person => person.id === String(id))?.label ?? `User ${id}`;
  }

  async function createRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const tenant = String(form.get("tenant") ?? "");
      await clientApi.post("/api/v1/maintenance/requests/", {
        unit: Number(form.get("unit")),
        tenant: tenant ? Number(tenant) : null,
        title: String(form.get("title") ?? "").trim(),
        description: String(form.get("description") ?? "").trim(),
        hazard: Number(form.get("hazard")),
        vulnerability: Number(form.get("vulnerability")),
      });
      setShowCreate(false);
      setNotice("Maintenance request opened. Priority was scored by the server.");
      await load();
    } catch (createError) {
      setError(apiErrorMessage(createError, "The request couldn’t be opened."));
    } finally {
      setBusy(false);
    }
  }

  async function assign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/assign/`, {
        user_id: Number(form.get("user_id")),
        notes: String(form.get("notes") ?? ""),
      });
      setNotice("Request assigned.");
      await load();
    } catch (assignError) {
      setError(apiErrorMessage(assignError, "The request couldn’t be assigned."));
    } finally {
      setBusy(false);
    }
  }

  async function triage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/triage/`, {
        category: String(form.get("category") ?? "OTHER").trim().toUpperCase(),
        hazard: Number(form.get("hazard")),
        vulnerability: Number(form.get("vulnerability")),
        notes: String(form.get("notes") ?? ""),
        safety_override: form.get("safety_override") === "on",
        safety_override_reason: String(form.get("safety_override_reason") ?? ""),
        requires_approval: form.get("requires_approval") === "on",
      });
      setNotice("Triage details saved.");
      await load();
    } catch (triageError) {
      setError(apiErrorMessage(triageError, "Triage details couldn’t be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function submitQuotation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const lines = quotationLines.map(line => ({
        ...line,
        quantity: line.quantity.trim(),
        unit_price_cents: line.unit_price_cents,
      }));
      const quote = editingQuotationId
        ? await clientApi.patch<RepairQuotation>(`/api/v1/maintenance/requests/${selected.id}/quotations/${editingQuotationId}/`, {
            lines, explanation: quotationExplanation.trim(),
          }).then(response => response.data)
        : await clientApi.post<RepairQuotation>(`/api/v1/maintenance/requests/${selected.id}/quotations/`, {
            lines, explanation: quotationExplanation.trim(),
          }).then(response => response.data);
      setEditingQuotationId(String(quote.id));
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/quotations/${quote.id}/submit/`, {});
      setEditingQuotationId(null);
      setQuotationLines([emptyQuotationLine()]);
      setQuotationExplanation("");
      setNotice("Quotation submitted for review.");
      await load();
    } catch (quoteError) {
      setError(apiErrorMessage(quoteError, "The quotation couldn’t be submitted."));
    } finally { setBusy(false); }
  }

  function editQuotationDraft(quote: RepairQuotation) {
    setEditingQuotationId(String(quote.id));
    setQuotationExplanation(quote.explanation);
    setQuotationLines((quote.lines ?? []).map(line => ({
      category: line.category,
      description: line.description,
      quantity: String(line.quantity),
      unit: line.unit,
      unit_price_cents: String(line.unit_price_cents),
    })).concat((quote.lines ?? []).length === 0 ? [emptyQuotationLine()] : []));
    setError("");
    setNotice("Draft loaded for editing.");
  }

  async function recordMaterialPurchase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const latestQuotation = selected.quotations?.[0];
    if (!latestQuotation || latestQuotation.status !== "APPROVED") {
      setPurchaseError("A purchase requires the current approved quotation.");
      return;
    }
    setBusy(true); setPurchaseError(""); setPurchaseNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/purchases/`, {
        quotation_id: latestQuotation.id,
        quotation_line_id: Number(form.get("quotation_line_id")),
        supplier_name: String(form.get("supplier_name") ?? "").trim(),
        supplier_profile: form.get("supplier_profile") ? Number(form.get("supplier_profile")) : null,
        supplier_reference: String(form.get("supplier_reference") ?? "").trim(),
        quantity: String(form.get("quantity") ?? "").trim(),
        unit_price_cents: String(form.get("unit_price_cents") ?? "").trim(),
        purchase_date: String(form.get("purchase_date") ?? ""),
        idempotency_key: purchaseIdempotencyKey,
        overrun_reason: String(form.get("authorize_overrun") === "on" ? form.get("overrun_reason") ?? "" : "").trim(),
      });
      setPurchaseIdempotencyKey(makeIdempotencyKey());
      setPurchaseOverrunReason("");
      setPurchaseNotice("Purchase recorded. This does not confirm receipt or supplier payment.");
      await Promise.all([loadMaterialData(String(selected.id)), load()]);
    } catch (purchaseError) {
      setPurchaseError(apiErrorMessage(purchaseError, "The material purchase couldn’t be recorded."));
    } finally { setBusy(false); }
  }

  async function acknowledgeReceipt(event: FormEvent<HTMLFormElement>, purchase: MaterialPurchase) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const purchaseKey = String(purchase.id);
    const requestKey = receiptIdempotencyKeys[purchaseKey] ?? makeIdempotencyKey();
    setReceiptIdempotencyKeys(previous => ({ ...previous, [purchaseKey]: requestKey }));
    setBusy(true); setPurchaseError(""); setPurchaseNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/purchases/${purchase.id}/receipts/`, {
        quantity: String(form.get("received_quantity") ?? "").trim(),
        evidence_reference: String(form.get("evidence_reference") ?? "").trim(),
        notes: String(form.get("receipt_notes") ?? "").trim(),
        idempotency_key: requestKey,
      });
      setReceiptIdempotencyKeys(previous => ({ ...previous, [purchaseKey]: makeIdempotencyKey() }));
      setPurchaseNotice("Receipt acknowledged. The reference is recorded; it does not confirm supplier payment.");
      await loadMaterialData(String(selected.id));
    } catch (receiptError) {
      setPurchaseError(apiErrorMessage(receiptError, "Material receipt couldn’t be acknowledged."));
    } finally { setBusy(false); }
  }

  async function startWork() {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/start/`, {});
      setNotice("Work started."); await load();
    } catch (startError) { setError(apiErrorMessage(startError, "Work couldn’t be started.")); }
    finally { setBusy(false); }
  }

  async function respondToAssignment(accept: boolean, reason = "") {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/${accept ? "accept" : "decline"}/`,
        accept ? {} : { reason });
      setNotice(accept ? "Assignment accepted." : "Assignment declined and returned to the property team.");
      await load();
    } catch (responseError) {
      setError(apiErrorMessage(responseError, "Your assignment response couldn’t be saved."));
    } finally { setBusy(false); }
  }

  async function scheduleFollowUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected?.work_order?.assignee) return;
    const form = new FormData(event.currentTarget);
    const localTime = String(form.get("follow_up_at") ?? "");
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/follow-up/`, {
        follow_up_at: new Date(localTime).toISOString(),
        reason: String(form.get("reason") ?? "").trim(),
        assignee_id: selected.work_order.assignee,
      });
      setNotice("Repair follow-up scheduled."); await load();
    } catch (scheduleError) {
      setError(apiErrorMessage(scheduleError, "Follow-up couldn’t be scheduled."));
    } finally { setBusy(false); }
  }

  async function submitCompletion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const materialDescription = String(form.get("material_description") ?? "").trim();
    const materialPurchaseId = String(form.get("purchase_id") ?? "").trim();
    const linkedPurchase = materialPurchaseId
      ? materialPurchases?.purchases.find(purchase => String(purchase.id) === materialPurchaseId)
      : undefined;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/complete/`, {
        diagnosis: String(form.get("diagnosis") ?? "").trim(),
        failure_category: String(form.get("failure_category") ?? "OTHER").trim().toUpperCase(),
        resolution_summary: String(form.get("resolution_summary") ?? "").trim(),
        outcome: String(form.get("outcome") ?? "FIXED"),
        labour_cost_cents: Number(form.get("labour_cost_cents")),
        materials_cost_cents: Number(form.get("materials_cost_cents")),
        other_cost_cents: Number(form.get("other_cost_cents") || 0),
        follow_up_reason: String(form.get("follow_up_reason") ?? "").trim(),
        materials: materialDescription || materialPurchaseId ? [{
          description: materialDescription || linkedPurchase?.description || "",
          quantity: String(form.get("quantity") || "1"),
          unit: String(form.get("unit") || linkedPurchase?.unit || "piece"),
          unit_cost_cents: Number(form.get("unit_cost_cents") || linkedPurchase?.unit_price_cents || 0),
          ...(materialPurchaseId ? { purchase_id: Number(materialPurchaseId) } : {}),
        }] : [],
      });
      setNotice("Repair submitted for verification."); await load();
    } catch (completionError) { setError(apiErrorMessage(completionError, "Completion couldn’t be submitted.")); }
    finally { setBusy(false); }
  }

  async function addCompletionEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected?.completion) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setEvidenceError(""); setEvidenceNotice("");
    try {
      const response = await clientApi.post<{ evidence: CompletionEvidence; idempotent_replay: boolean }>(
        `/api/v1/maintenance/requests/${selected.id}/completions/${selected.completion.id}/evidence/`, {
          category: String(form.get("category") ?? "OTHER"),
          caption: String(form.get("caption") ?? "").trim(),
          evidence_reference: String(form.get("evidence_reference") ?? "").trim(),
        },
      );
      setEvidenceNotice(response.data.idempotent_replay ? "Evidence reference was already recorded." : "Evidence reference recorded for review.");
      await loadSupplementalData(String(selected.id), selected.completion.id);
      event.currentTarget.reset();
    } catch (saveError) {
      setEvidenceError(apiErrorMessage(saveError, "The evidence reference couldn’t be recorded."));
    } finally { setBusy(false); }
  }

  async function requestTurnoverInspection() {
    if (!selected) return;
    setBusy(true); setTurnoverError(""); setTurnoverNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/turnover-assessments/`, {
        idempotency_key: turnoverKey,
      });
      setTurnoverKey(makeIdempotencyKey());
      setTurnoverChecklist([{ item_key: "", label: "", passed: false, notes: "" }]);
      setTurnoverIssues(""); setConfirmTurnoverReady(false);
      setTurnoverNotice("Vacant-unit inspection requested. Unit status has not changed.");
      await loadSupplementalData(String(selected.id), selected.completion?.id);
    } catch (requestError) {
      setTurnoverError(apiErrorMessage(requestError, "The turnover inspection couldn’t be requested."));
    } finally { setBusy(false); }
  }

  async function recordTurnoverAssessment(event: FormEvent<HTMLFormElement>, assessment: TurnoverAssessment) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true); setTurnoverError(""); setTurnoverNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/turnover-assessments/${assessment.id}/assess/`, {
        ready: Boolean(turnoverState?.can_confirm_ready && confirmTurnoverReady),
        outstanding_issues: turnoverIssues.trim(),
        checklist_items: turnoverChecklist.map(item => ({ ...item, item_key: item.item_key.trim(), label: item.label.trim(), notes: item.notes.trim() })),
      });
      setTurnoverNotice(confirmTurnoverReady ? "Readiness decision recorded. The unit status and lease history were not changed." : "Inspection recorded as not ready.");
      await loadSupplementalData(String(selected.id), selected.completion?.id);
    } catch (assessmentError) {
      setTurnoverError(apiErrorMessage(assessmentError, "The inspection decision couldn’t be saved."));
    } finally { setBusy(false); }
  }

  async function decideQuote(quote: RepairQuotation, approved: boolean) {
    if (!selected) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/quotations/${quote.id}/decision/`, {
        approved,
        notes: approved ? "Approved for the submitted scope." : "Please revise and resubmit this estimate.",
      });
      setNotice(approved ? "Quotation approved." : "Quotation rejected."); await load();
    } catch (decisionError) { setError(apiErrorMessage(decisionError, "The quotation decision couldn’t be saved.")); }
    finally { setBusy(false); }
  }

  async function verifyCompletion(approved: boolean, overrunReason = "") {
    if (!selected?.completion) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await clientApi.post(`/api/v1/maintenance/requests/${selected.id}/verify/`, {
        completion_id: selected.completion.id,
        approved,
        notes: approved ? "Repair checked and accepted." : "Please complete the follow-up work described by the property team.",
        authorize_cost_overrun: Boolean(overrunReason.trim()),
        cost_overrun_reason: overrunReason.trim(),
      });
      setCostOverrunReason("");
      setNotice(approved ? "Repair verified and closed." : "Further repair work requested."); await load();
    } catch (verificationError) { setError(apiErrorMessage(verificationError, "The verification decision couldn’t be saved.")); }
    finally { setBusy(false); }
  }

  const finished = selected && ["COMPLETED", "CLOSED", "CANCELLED"].includes(selected.status);
  const repairSteps = ["Request logged", "Technician assigned", "Completion submitted", "Work verified"];
  const repairStepIndex = selected?.status === "CLOSED" && selected.completion?.status === "VERIFIED"
    ? repairSteps.length
    : selected?.completion
      ? 3
      : selected?.work_order?.assignee
        ? 2
        : 1;

  return (
    <section className="ops-panel [&_.ops-form-actions]:sticky [&_.ops-form-actions]:bottom-0 [&_.ops-form-actions]:z-10 [&_.ops-form-actions]:bg-[var(--hodi-surface)] [&_.ops-form-actions]:p-2 md:[&_.ops-form-actions]:static md:[&_.ops-form-actions]:bg-transparent md:[&_.ops-form-actions]:p-0" id="maintenance-requests">
      <div className="ops-heading">
        <div>
          <span className="ops-kicker">MAINTENANCE</span>
          <h2>Requests & work orders</h2>
          <p>Open a request, assign it, complete the work order, then close it. Priority comes from the server.</p>
        </div>
        <div className="ops-actions">
          <button type="button" className="ops-button" onClick={() => void load()} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
          {canWrite && (
            <button type="button" className="ops-button ops-button--primary" onClick={() => setShowCreate(open => !open)}>
              {showCreate ? "Cancel" : "New request"}
            </button>
          )}
        </div>
      </div>
      {error && <p className="ops-alert" role="alert">{error}</p>}
      {notice && <p className="ops-success" role="status">{notice}</p>}
      {showCreate && canWrite && (
        <form className="ops-form" onSubmit={event => void createRequest(event)}>
          <div className="ops-grid">
            <label>Unit
              <select name="unit" required defaultValue="">
                <option value="" disabled>Select a unit</option>
                {units.map(unit => <option key={unit.id} value={unit.id}>{unitLabel.get(String(unit.id)) ?? unit.name}</option>)}
              </select>
            </label>
            <label>Tenant <span>(optional)</span>
              <select name="tenant" defaultValue="">
                <option value="">No tenant</option>
                {tenants.map(tenant => (
                  <option key={tenant.id} value={tenant.id}>{tenantLabel.get(String(tenant.id))}</option>
                ))}
              </select>
            </label>
            <label>Hazard 1–5
              <input name="hazard" type="number" min={1} max={5} defaultValue={3} required />
            </label>
            <label>Vulnerability 1–5
              <input name="vulnerability" type="number" min={1} max={5} defaultValue={1} required />
            </label>
          </div>
          <label>Title<input name="title" required maxLength={200} /></label>
          <label>Description<textarea name="description" required /></label>
          <div className="ops-form-actions">
            <button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Open request"}</button>
          </div>
        </form>
      )}
      {loading && !requests.length && <p className="ops-status">Loading maintenance requests…</p>}
      {!loading && !error && requests.length === 0 && (
        <div className="ops-empty">
          <strong>No maintenance requests</strong>
          <p>Reported work for this organization will show priority, status, and the assigned person.</p>
        </div>
      )}
      {requests.length > 0 && (
        <div className="ops-table-wrap">
          <table className="ops-table">
            <thead>
              <tr><th>Request</th><th>Where</th><th>Tenant</th><th>Priority</th><th>Status</th><th>Assignee</th></tr>
            </thead>
            <tbody>
              {requests.map(row => (
                <tr key={row.id}>
                  <td>
                    <button type="button" className="ops-button" onClick={() => setSelectedId(String(row.id))}>{row.title}</button>
                    <div className="ops-note">{formatWhen(row.created_at)}</div>
                  </td>
                  <td>{unitLabel.get(String(row.unit)) ?? `Unit ${row.unit}`}</td>
                  <td>{row.tenant ? tenantLabel.get(String(row.tenant)) ?? `Tenant ${row.tenant}` : "—"}</td>
                  <td><span className={`ops-pill ${row.emergency_override ? "is-hot" : ""}`}>{row.emergency_override ? "Emergency · " : ""}Class {row.priority_class}</span></td>
                  <td>{humanize(row.status)}</td>
                  <td>{assigneeName(row.work_order?.assignee)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <div className="ops-detail border-l-4 border-sky-700">
          <div className="ops-heading">
            <div>
              <span className="ops-kicker">REQUEST {selected.id}</span>
              <h2>{selected.title}</h2>
              <p>{selected.description}</p>
            </div>
            <button type="button" className="ops-button" onClick={() => setSelectedId("")}>Close details</button>
          </div>
          {selected.status === "CANCELLED" ? (
            <p className="ops-status ops-lifecycle-cancelled">This repair request was cancelled.</p>
          ) : (
            <ol className="ops-lifecycle" aria-label="Repair progress">
              {repairSteps.map((step, index) => {
                const complete = index < repairStepIndex;
                const active = index === repairStepIndex;
                return (
                  <li key={step} data-complete={complete ? "true" : "false"} data-active={active ? "true" : "false"} aria-current={active ? "step" : undefined}>
                    <span className="ops-lifecycle-marker" aria-hidden="true">{complete ? "✓" : String(index + 1).padStart(2, "0")}</span>
                    <span>{step}</span>
                  </li>
                );
              })}
            </ol>
          )}
          <dl className="ops-meta">
            <div><dt>Property / unit</dt><dd>{unitLabel.get(String(selected.unit)) ?? `Unit ${selected.unit}`}</dd></div>
            <div><dt>Tenant</dt><dd>{selected.tenant ? tenantLabel.get(String(selected.tenant)) ?? `Tenant ${selected.tenant}` : "—"}</dd></div>
            <div><dt>Status</dt><dd>{humanize(selected.status)}</dd></div>
            <div><dt>Priority</dt><dd>Class {selected.priority_class}{selected.emergency_override ? " · emergency override" : ""}</dd></div>
            <div><dt>Work order</dt><dd>{selected.work_order ? `${humanize(selected.work_order.status)} · ${assigneeName(selected.work_order.assignee)}` : "—"}</dd></div>
            <div><dt>Assignment response</dt><dd>{humanize(selected.work_order?.assignment_status ?? "Not recorded")}</dd></div>
            <div><dt>Opened</dt><dd>{formatWhen(selected.created_at)}</dd></div>
            <div><dt>Assigned</dt><dd>{formatWhen(selected.work_order?.assigned_at)}</dd></div>
            <div><dt>Completed</dt><dd>{formatWhen(selected.completed_at || selected.work_order?.completed_at)}</dd></div>
            <div><dt>Closed</dt><dd>{formatWhen(selected.closed_at)}</dd></div>
          </dl>
          {selected.work_order?.assignment_decline_reason && (
            <p className="ops-alert"><strong>Technician declined:</strong> {selected.work_order.assignment_decline_reason} Reassign this request to continue.</p>
          )}
          {selected.follow_up_at && (
            <article className="ops-note">
              <strong>Follow-up scheduled · {formatWhen(selected.follow_up_at)}</strong>
              <p>{selected.follow_up_reason}</p>
              <p>Responsible: {selected.follow_up_assignee_name ?? "Assigned repair team"}</p>
            </article>
          )}
          {canWrite && !finished && (
            <form className="ops-form" onSubmit={event => void triage(event)}>
              <h3>Triage and safety</h3>
              <div className="ops-grid">
                <label>Repair category
                  <select name="category" defaultValue={selected.category || "OTHER"}>
                    {["OTHER", "PLUMBING", "ELECTRICAL", "CARPENTRY", "HVAC", "MASONRY"].map(category => <option key={category}>{category}</option>)}
                  </select>
                </label>
                <label>Hazard 1–5<input name="hazard" type="number" min={1} max={5} defaultValue={selected.hazard} required /></label>
                <label>Vulnerability 1–5<input name="vulnerability" type="number" min={1} max={5} defaultValue={selected.vulnerability} required /></label>
              </div>
              <label>Internal triage notes<textarea name="notes" defaultValue={selected.triage_notes ?? ""} /></label>
              <label className="ops-check"><input name="safety_override" type="checkbox" defaultChecked={selected.safety_override} /> Safety exception to quotation approval</label>
              <label>Safety exception reason<input name="safety_override_reason" defaultValue={selected.safety_override_reason ?? ""} maxLength={500} /></label>
              <label className="ops-check"><input name="requires_approval" type="checkbox" defaultChecked={selected.requires_approval} /> Require an approved quotation before work starts</label>
              <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Save triage"}</button></div>
            </form>
          )}
          {canWrite && !finished && (
            <form className="ops-form" onSubmit={event => void assign(event)}>
              <div className="ops-grid">
                <label>Assign to
                  <select name="user_id" required defaultValue="">
                    <option value="" disabled>Select a person</option>
                    {assignees.map(person => <option key={person.id} value={person.id}>{person.label}</option>)}
                  </select>
                </label>
                <label>Notes<input name="notes" maxLength={500} /></label>
              </div>
              <div className="ops-form-actions">
                <button className="ops-button ops-button--primary" disabled={busy || assignees.length === 0}>
                  {busy ? "Saving…" : "Assign"}
                </button>
              </div>
              {assignees.length === 0 && <p className="ops-note">No staff membership was returned, so assignment isn’t available.</p>}
            </form>
          )}
          {selected.quotations?.map(quote => (
            <article className="ops-note" key={quote.id}>
              <strong>Quotation{quote.revision_of ? " · revised" : ""} · {humanize(quote.status)} · {formatMinorAmount(BigInt(quote.total_estimate_cents))}</strong>
              <p>{quote.explanation}</p>
              {quote.has_itemized_lines && quote.lines?.length ? (
                <ol>
                  {quote.lines.map(line => (
                    <li key={line.id}>
                      {humanize(line.category)} · {line.description}: {line.quantity} {line.unit} × {formatMinorAmount(BigInt(line.unit_price_cents))} = {formatMinorAmount(BigInt(line.line_total_cents))}
                    </li>
                  ))}
                </ol>
              ) : <p>Legacy aggregate quotation · Labour {formatMinorAmount(BigInt(quote.labour_estimate_cents))}, materials {formatMinorAmount(BigInt(quote.materials_estimate_cents))}, other {formatMinorAmount(BigInt(quote.other_estimate_cents))}.</p>}
              <p>Labour {formatMinorAmount(BigInt(quote.labour_estimate_cents))} · Materials {formatMinorAmount(BigInt(quote.materials_estimate_cents))} · Other, including transport {formatMinorAmount(BigInt(quote.other_estimate_cents))}</p>
              {selected.work_order?.assigned_to_me && quote.status === "DRAFT" && (
                <button type="button" className="ops-button" disabled={busy} onClick={() => editQuotationDraft(quote)}>Edit draft</button>
              )}
              {canWrite && quote.status === "PENDING" && (
                <div className="ops-form-actions">
                  <button type="button" className="ops-button ops-button--primary" disabled={busy} onClick={() => void decideQuote(quote, true)}>Approve scope</button>
                  <button type="button" className="ops-button" disabled={busy} onClick={() => void decideQuote(quote, false)}>Reject / revise</button>
                </div>
              )}
            </article>
          ))}
          {(canWrite || selected.work_order?.assigned_to_me) && (
            <section className="ops-form" aria-labelledby="job-materials-heading">
              <h3 id="job-materials-heading">Job materials and recorded costs</h3>
              {selected.work_order?.assigned_to_me && requiresApproval && (
                <p className="ops-pill is-hot" role="status">Awaiting Supervisor Approval</p>
              )}
              {purchaseLoading && <p className="ops-status">Loading purchase and receipt records…</p>}
              {purchaseError && <p className="ops-alert" role="alert">{purchaseError}</p>}
              {purchaseNotice && <p className="ops-status" role="status">{purchaseNotice}</p>}
              {canWrite && jobCostSummary && (
                <article className="ops-note" aria-live="polite">
                  <strong>Cost summary · {humanize(jobCostSummary.cost_summary_status)}</strong>
                  <p>Approved quotation: {jobCostSummary.approved_total_cents == null ? "No approved quotation" : formatMinorAmount(BigInt(jobCostSummary.approved_total_cents))}</p>
                  {!jobCostSummary.approved_quotation_is_current && jobCostSummary.approved_total_cents != null && <p>The latest quotation revision is not approved; this comparison is provisional.</p>}
                  <p>Recorded purchases: {formatMinorAmount(BigInt(jobCostSummary.recorded_purchase_total_cents))}</p>
                  <p>Actual labour: {formatMinorAmount(BigInt(jobCostSummary.recorded_labour_actual_cents))} · Reported consumed materials: {formatMinorAmount(BigInt(jobCostSummary.reported_material_consumption_cost_cents))} · Actual other: {formatMinorAmount(BigInt(jobCostSummary.recorded_other_actual_cents))}</p>
                  <p>Recorded job cost: {formatMinorAmount(BigInt(jobCostSummary.recorded_job_cost_cents))}</p>
                  {jobCostSummary.variance_cents != null && (
                    <p className={jobCostSummary.over_budget ? "ops-alert" : "ops-note"}>
                      {jobCostSummary.over_budget ? "Over budget by " : jobCostSummary.variance_cents < 0 ? "Under budget by " : "At budget by "}{formatMinorAmount(BigInt(Math.abs(jobCostSummary.variance_cents)))}
                    </p>
                  )}
                  <p>{jobCostSummary.materials_reconciled ? "Consumed material values reconcile to the recorded use." : "Material consumption and purchase records need reconciliation; the total is provisional."}</p>
                  <p>Supplier payment: not tracked in HODI.</p>
                </article>
              )}
              {purchaseLoading === false && materialPurchases?.purchases.length === 0 && <p className="ops-note">No job purchases have been recorded.</p>}
              {materialPurchases?.purchases.map(purchase => (
                <article className="ops-note" key={purchase.id}>
                  <strong>{purchase.description} · {humanize(purchase.status)}</strong>
                  <p>{purchase.quantity} {purchase.unit} purchased · {purchase.received_quantity} received{purchase.supplier_name ? ` · ${purchase.supplier_name}` : ""}{purchase.supplier_reference ? ` · Ref ${purchase.supplier_reference}` : ""}</p>
                  <p>Recorded {formatWhen(purchase.purchase_date)}{purchase.purchase_total_cents == null ? "" : ` · ${formatMinorAmount(BigInt(purchase.purchase_total_cents))}`} · Purchase entry does not confirm supplier payment.</p>
                  {purchase.receipts.map(receipt => (
                    <p key={receipt.id}>Received {receipt.quantity} · {receipt.evidence_reference} · acknowledged by {receipt.acknowledged_by_name} · {formatWhen(receipt.created_at)}</p>
                  ))}
                  {purchase.overrun_reason && <p>Authorized purchase variance: {purchase.overrun_reason}</p>}
                  {purchase.can_acknowledge_receipt && purchase.status !== "RECEIVED" && (
                    <form className="ops-form" onSubmit={event => void acknowledgeReceipt(event, purchase)}>
                      <h4>Acknowledge materials received</h4>
                      <p>Record a delivery or receipt reference. HODI does not independently verify the referenced document.</p>
                      <div className="ops-grid">
                        <label>Quantity received<input name="received_quantity" type="number" min="0.001" max={remainingPurchaseQuantity(purchase)} step="0.001" defaultValue={remainingPurchaseQuantity(purchase)} required /></label>
                        <label>Receipt / delivery reference<input name="evidence_reference" maxLength={500} required /></label>
                      </div>
                      <label>Notes<input name="receipt_notes" maxLength={500} /></label>
                      <button className="ops-button" disabled={busy || purchaseLoading}>{busy ? "Saving…" : "Record receipt"}</button>
                    </form>
                  )}
                </article>
              ))}
              {materialPurchases?.can_record_purchase && latestQuotation?.status === "APPROVED" && currentApprovedMaterialLines.length > 0 && (
                <form className="ops-form" onSubmit={event => void recordMaterialPurchase(event)}>
                  <h4>Record a purchase against approved material</h4>
                  <p>Only material requirements on the current approved quotation can authorize a purchase. Overruns require an owner or property manager reason.</p>
                  <label>Approved material line
                    <select name="quotation_line_id" required defaultValue={String(currentApprovedMaterialLines[0].id)}>
                      {currentApprovedMaterialLines.map(line => (
                        <option key={line.id} value={line.id}>{line.description} · {line.quantity} {line.unit} · estimate {formatMinorAmount(BigInt(line.line_total_cents))}</option>
                      ))}
                    </select>
                  </label>
                  <div className="ops-grid">
                    <label>Supplier profile (optional)<select name="supplier_profile" defaultValue=""><option value="">Manual supplier record</option>{suppliers.map(item => <option key={item.id} value={item.id}>{item.business_name}</option>)}</select></label>
                    <label>Supplier name<input name="supplier_name" maxLength={200} required /></label>
                    <label>Supplier reference (optional)<input name="supplier_reference" maxLength={200} /></label>
                    <label>Quantity purchased<input name="quantity" type="number" min="0.001" step="0.001" required /></label>
                    <label>Actual unit price (KES cents)<input name="unit_price_cents" type="number" min={0} step={1} required /></label>
                    <label>Purchase date<input name="purchase_date" type="date" defaultValue={rentalBusinessDate()} required /></label>
                  </div>
                  <label className="ops-check"><input name="authorize_overrun" type="checkbox" /> Authorize a material budget overrun</label>
                  <label>Overrun reason<textarea value={purchaseOverrunReason} onChange={event => setPurchaseOverrunReason(event.target.value)} maxLength={2000} /></label>
                  <button className="ops-button ops-button--primary" disabled={busy || purchaseLoading}>{busy ? "Saving…" : "Record purchase"}</button>
                </form>
              )}
              {materialPurchases?.can_record_purchase && latestQuotation && latestQuotation.status !== "APPROVED" && (
                <div>
                  <p className="ops-note">Purchases are paused until the latest quotation revision is approved.</p>
                  <button type="button" className="ops-button" disabled>Log materials</button>
                </div>
              )}
            </section>
          )}
          {selected.work_order?.assigned_to_me && selected.work_order.status === "ASSIGNED" && selected.work_order.assignment_status === "PENDING" && (
            <form className="ops-form" onSubmit={event => {
              event.preventDefault();
              void respondToAssignment(false, declineReason);
            }}>
              <h3>Respond to assignment</h3>
              <p>Accept this repair or decline with a reason so the property team can reassign it.</p>
              <div className="ops-form-actions">
                <button type="button" className="ops-button ops-button--primary" disabled={busy} onClick={() => void respondToAssignment(true)}>Accept assignment</button>
                <label>Reason for declining<input value={declineReason} onChange={event => setDeclineReason(event.target.value)} maxLength={500} required /></label>
                <button type="submit" className="ops-button" disabled={busy || !declineReason.trim()}>Decline assignment</button>
              </div>
            </form>
          )}
          {selected.work_order?.assigned_to_me && selected.work_order.status === "ASSIGNED" && (selected.work_order.assignment_status === "ACCEPTED" || selected.work_order.assignment_status === "NOT_REQUIRED" || !selected.work_order.assignment_status) && (
            <>
            {requiresApproval && <p className="ops-pill is-hot" role="status">Awaiting Supervisor Approval</p>}
            <div className="ops-form-actions">
              <button type="button" className="ops-button ops-button--primary" disabled={busy || requiresApproval} onClick={() => void startWork()}>
                {busy ? "Saving…" : "Start assigned work"}
              </button>
            </div>
            </>
          )}
          {selected.work_order?.assigned_to_me && selected.work_order.status === "IN_PROGRESS" && (
            <form className="ops-form" onSubmit={event => void submitCompletion(event)}>
              <h3>Submit repair for verification</h3>
              {requiresApproval && <p className="ops-pill is-hot" role="status">Awaiting Supervisor Approval</p>}
              <label>Diagnosis<input name="diagnosis" required /></label>
              <div className="ops-grid">
                <label>Failure category<input name="failure_category" required maxLength={50} /></label>
                <label>Outcome
                  <select name="outcome" defaultValue="FIXED">
                    <option value="FIXED">Fixed</option><option value="PARTIALLY_FIXED">Partially fixed</option>
                    <option value="REPLACED">Replaced</option><option value="NO_FAULT_FOUND">No fault found</option>
                    <option value="NEEDS_FOLLOW_UP">Needs follow-up</option>
                  </select>
                </label>
                <label>Labour cost (KES cents)<input name="labour_cost_cents" type="number" min={0} step={1} required /></label>
                <label>Materials cost (KES cents)<input name="materials_cost_cents" type="number" min={0} step={1} required /></label>
                <label>Other cost (KES cents)<input name="other_cost_cents" type="number" min={0} step={1} defaultValue={0} /></label>
              </div>
              <label>Resolution summary<textarea name="resolution_summary" required /></label>
              <label>Follow-up reason<input name="follow_up_reason" maxLength={500} /></label>
              <div className="ops-grid">
                {materialPurchases?.purchases.some(purchase => purchase.status !== "RECORDED") && (
                  <label>Use received job material (optional)
                    <select name="purchase_id" defaultValue="">
                      <option value="">Record an unlinked material use</option>
                      {materialPurchases.purchases.filter(purchase => quantityMilli(purchase.received_quantity) !== null && (quantityMilli(purchase.received_quantity) ?? BigInt(0)) > BigInt(0)).map(purchase => (
                        <option key={purchase.id} value={purchase.id}>{purchase.description} · {purchase.received_quantity} {purchase.unit} received</option>
                      ))}
                    </select>
                  </label>
                )}
                <label>Material used (optional)<input name="material_description" maxLength={200} /></label>
                <label>Quantity<input name="quantity" type="number" min="0.001" step="0.001" defaultValue="1" /></label>
                <label>Unit<input name="unit" defaultValue="piece" maxLength={30} /></label>
                <label>Unit cost (KES cents)<input name="unit_cost_cents" type="number" min={0} step={1} defaultValue={0} /></label>
              </div>
              <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy || requiresApproval}>{busy ? "Saving…" : "Submit completion"}</button></div>
            </form>
          )}
          {selected.work_order?.assigned_to_me && !finished && selected.work_order.assignment_status !== "PENDING" && !selected.quotations?.some(quote => quote.status === "PENDING") && (
            <form className="ops-form" onSubmit={event => void submitQuotation(event)}>
              <h3>{editingQuotationId ? "Edit itemised quotation draft" : "Prepare itemised quotation"}</h3>
              {quotationLines.map((line, index) => (
                <fieldset className="ops-grid" key={`${editingQuotationId ?? "new"}-${index}`}>
                  <legend>Quotation line {index + 1}</legend>
                  <label>Category
                    <select value={line.category} onChange={event => setQuotationLines(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, category: event.target.value as QuotationDraftLine["category"] } : row))}>
                      <option value="MATERIAL">Material</option><option value="LABOUR">Labour</option>
                      <option value="TRANSPORT">Transport</option><option value="OTHER">Other</option>
                    </select>
                  </label>
                  <label>Description<input value={line.description} maxLength={240} required onChange={event => setQuotationLines(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, description: event.target.value } : row))} /></label>
                  <label>Quantity<input type="number" min="0.001" step="0.001" value={line.quantity} required onChange={event => setQuotationLines(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, quantity: event.target.value } : row))} /></label>
                  <label>Unit<input value={line.unit} maxLength={30} required onChange={event => setQuotationLines(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, unit: event.target.value } : row))} /></label>
                  <label>Unit price (KES cents)<input type="number" min={0} step={1} value={line.unit_price_cents} required onChange={event => setQuotationLines(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, unit_price_cents: event.target.value } : row))} /></label>
                  <p>Calculated line total: {formatMinorAmount(quotationLineMinor(line))}</p>
                  <button type="button" className="ops-button" disabled={busy || quotationLines.length === 1} onClick={() => setQuotationLines(rows => rows.filter((_, rowIndex) => rowIndex !== index))}>Remove line {index + 1}</button>
                </fieldset>
              ))}
              <button type="button" className="ops-button" disabled={busy} onClick={() => setQuotationLines(rows => [...rows, emptyQuotationLine()])}>Add a line</button>
              <div className="ops-note" aria-live="polite">
                <strong>Estimate summary</strong>
                <p>Labour {formatMinorAmount(quotationSubtotals.LABOUR)} · Materials {formatMinorAmount(quotationSubtotals.MATERIAL)} · Other, including transport {formatMinorAmount(quotationSubtotals.OTHER)}</p>
                <p>Overall estimate {formatMinorAmount(quotationSubtotals.LABOUR + quotationSubtotals.MATERIAL + quotationSubtotals.OTHER)}</p>
              </div>
              <label>Scope and assumptions<textarea value={quotationExplanation} required onChange={event => setQuotationExplanation(event.target.value)} /></label>
              <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy}>{busy ? "Saving…" : "Submit quotation"}</button></div>
            </form>
          )}
          {selected.completion && (
            <article className="ops-note">
              <strong>Repair outcome: {humanize(selected.completion.outcome)} · {humanize(selected.completion.status)}</strong>
              {selected.completion.status === "VERIFIED" && <p>Verified by {selected.completion.verified_by_name ?? "authorized property staff"} · {formatWhen(selected.completion.verified_at)}</p>}
              <p>{selected.completion.diagnosis}</p>
              <p>{selected.completion.resolution_summary}</p>
              {selected.completion.follow_up_required && <p>Follow-up: {selected.completion.follow_up_reason}</p>}
              {selected.completion.actual_total_cents != null && <p>Actual cost: {formatMinorAmount(BigInt(Math.trunc(selected.completion.actual_total_cents)))}</p>}
              {canWrite && selected.completion.status === "SUBMITTED" && selected.completion.outcome !== "NEEDS_FOLLOW_UP" && materialPurchases?.cost_overrun_authorization_required && materialPurchases.can_record_purchase && (
                <div className="ops-form">
                  <p>This repair is over the approved estimate. An owner or property manager must authorize the recorded variance.</p>
                  <label>Reason for authorizing the overrun<textarea value={costOverrunReason} onChange={event => setCostOverrunReason(event.target.value)} maxLength={2000} required /></label>
                  <button type="button" className="ops-button ops-button--primary" disabled={busy || !costOverrunReason.trim()} onClick={() => void verifyCompletion(true, costOverrunReason)}>Authorize cost overrun and verify</button>
                  <button type="button" className="ops-button" disabled={busy} onClick={() => void verifyCompletion(false)}>Request further work</button>
                </div>
              )}
              {canWrite && selected.completion.status === "SUBMITTED" && selected.completion.outcome !== "NEEDS_FOLLOW_UP" && materialPurchases?.cost_overrun_authorization_required && !materialPurchases.can_record_purchase && (
                <p className="ops-note">An owner or property manager must authorize the recorded cost overrun before verification.</p>
              )}
              {canWrite && selected.completion.status === "SUBMITTED" && selected.completion.outcome !== "NEEDS_FOLLOW_UP" && !materialPurchases?.cost_overrun_authorization_required && (
                <div className="ops-form-actions">
                  <button type="button" className="ops-button ops-button--primary" disabled={busy} onClick={() => void verifyCompletion(true)}>Verify and close</button>
                  <button type="button" className="ops-button" disabled={busy} onClick={() => void verifyCompletion(false)}>Request further work</button>
                </div>
              )}
              {canWrite && selected.completion.status === "SUBMITTED" && selected.completion.outcome === "NEEDS_FOLLOW_UP" && (
                <p className="ops-note">This repair cannot be verified as resolved. Reject it for further work, then schedule the follow-up.</p>
              )}
              {(canWrite || selected.work_order?.assigned_to_me) && (
                <section className="ops-form" aria-labelledby="completion-evidence-heading">
                  <h3 id="completion-evidence-heading">Completion evidence references</h3>
                  <p>References are private metadata only. HODI has no durable production file store configured, so this form does not upload or preview files.</p>
                  {evidenceLoading && <p className="ops-status">Loading evidence…</p>}
                  {evidenceError && <p className="ops-alert" role="alert">{evidenceError}</p>}
                  {evidenceNotice && <p className="ops-status" role="status">{evidenceNotice}</p>}
                  {completionEvidence.length === 0 && !evidenceLoading && <p className="ops-note">No completion evidence references recorded.</p>}
                  {completionEvidence.map(evidence => (
                    <article className="ops-note" key={evidence.id}>
                      <strong>{humanize(evidence.category)}</strong>
                      {evidence.caption && <p>{evidence.caption}</p>}
                      <p>Private reference: {evidence.evidence_reference}</p>
                      <p>Recorded by {evidence.recorded_by_name} · {formatWhen(evidence.created_at)}</p>
                    </article>
                  ))}
                  {selected.completion.can_add_evidence && (
                    <form className="ops-form" onSubmit={event => void addCompletionEvidence(event)}>
                      <h4>Add an evidence reference</h4>
                      <div className="ops-grid">
                        <label>Evidence type
                          <select name="category" defaultValue="AFTER_PHOTO">
                            <option value="BEFORE_PHOTO">Before-work evidence</option>
                            <option value="AFTER_PHOTO">After-work photograph</option>
                            <option value="WORK_DOCUMENT">Work document</option>
                            <option value="MATERIAL_RECEIPT">Material receipt evidence</option>
                            <option value="OTHER">Other</option>
                          </select>
                        </label>
                        <label>Private evidence reference<input name="evidence_reference" maxLength={500} required /></label>
                      </div>
                      <label>Caption (optional)<input name="caption" maxLength={240} /></label>
                      <button className="ops-button" disabled={busy || evidenceLoading}>{busy ? "Saving…" : "Record reference"}</button>
                    </form>
                  )}
                  <p>Evidence references support review but do not prove the work was done correctly.</p>
                </section>
              )}
            </article>
          )}
          {canWrite && (
            <section className="ops-form" aria-labelledby="turnover-heading">
              <h3 id="turnover-heading">Vacant-unit turnover readiness</h3>
              <p>Turnover is a separate inspection for a vacant unit. A verified repair alone does not establish readiness. This decision never changes the unit status or lease history.</p>
              {turnoverLoading && <p className="ops-status">Loading turnover history…</p>}
              {turnoverError && <p className="ops-alert" role="alert">{turnoverError}</p>}
              {turnoverNotice && <p className="ops-status" role="status">{turnoverNotice}</p>}
              {turnoverState?.assessments.map(assessment => (
                <article className="ops-note" key={assessment.id}>
                  <strong>Inspection {assessment.id} · {humanize(assessment.status)}{assessment.revision_of ? ` · reassessment of ${assessment.revision_of}` : ""}</strong>
                  <p>{assessment.property_name} · {assessment.building_name} · Unit {assessment.unit_name}</p>
                  <p>Requested by {assessment.requested_by_name} · {formatWhen(assessment.requested_at)}</p>
                  {assessment.assessed_at && <p>Assessed by {assessment.assessed_by_name ?? "property staff"} · {formatWhen(assessment.assessed_at)}</p>}
                  {assessment.outstanding_issues && <p className="ops-alert">Outstanding: {assessment.outstanding_issues}</p>}
                  {assessment.checklist_items.map(item => (
                    <p key={item.id}>{item.passed ? "Pass" : "Needs attention"} · {item.label}{item.notes ? ` — ${item.notes}` : ""}</p>
                  ))}
                </article>
              ))}
              {turnoverState?.can_request && turnoverState.assessments[0]?.status !== "REQUESTED" && (
                <button type="button" className="ops-button ops-button--primary" disabled={busy || turnoverLoading} onClick={() => void requestTurnoverInspection()}>
                  {busy ? "Saving…" : turnoverState.assessments.length ? "Request reassessment" : "Start vacant-unit inspection"}
                </button>
              )}
              {turnoverState?.assessments[0]?.status === "REQUESTED" && (
                <form className="ops-form" onSubmit={event => void recordTurnoverAssessment(event, turnoverState.assessments[0])}>
                  <h4>Record inspection checklist</h4>
                  <p>Enter the inspection checks and observations. The associated repair must be verified before an owner or property manager can pass readiness.</p>
                  {turnoverChecklist.map((item, index) => (
                    <fieldset className="ops-grid" key={index}>
                      <legend>Checklist item {index + 1}</legend>
                      <label>Item key<input value={item.item_key} maxLength={50} required onChange={event => setTurnoverChecklist(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, item_key: event.target.value } : row))} /></label>
                      <label>Inspection check<input value={item.label} maxLength={160} required onChange={event => setTurnoverChecklist(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, label: event.target.value } : row))} /></label>
                      <label className="ops-check"><input type="checkbox" checked={item.passed} onChange={event => setTurnoverChecklist(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, passed: event.target.checked } : row))} /> Check passed</label>
                      <label>Observation<input value={item.notes} maxLength={500} onChange={event => setTurnoverChecklist(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, notes: event.target.value } : row))} /></label>
                      <button type="button" className="ops-button" disabled={busy || turnoverChecklist.length === 1} onClick={() => setTurnoverChecklist(rows => rows.filter((_, rowIndex) => rowIndex !== index))}>Remove check</button>
                    </fieldset>
                  ))}
                  <button type="button" className="ops-button" disabled={busy || turnoverChecklist.length >= 30} onClick={() => setTurnoverChecklist(rows => [...rows, { item_key: "", label: "", passed: false, notes: "" }])}>Add checklist item</button>
                  <label>Outstanding issues or reason it is not ready<textarea value={turnoverIssues} maxLength={5000} onChange={event => setTurnoverIssues(event.target.value)} /></label>
                  {turnoverState.can_confirm_ready ? (
                    <label className="ops-check"><input type="checkbox" checked={confirmTurnoverReady} onChange={event => setConfirmTurnoverReady(event.target.checked)} /> Confirm ready for next tenancy</label>
                  ) : <p className="ops-note">Caretakers can record inspection failures. Only an owner or property manager can confirm readiness.</p>}
                  <button className="ops-button ops-button--primary" disabled={busy || turnoverLoading}>{busy ? "Saving…" : confirmTurnoverReady ? "Confirm readiness" : "Record inspection result"}</button>
                </form>
              )}
              {turnoverState?.assessments.length === 0 && <p className="ops-note">No turnover inspection has been requested for this repair job.</p>}
            </section>
          )}
          {canWrite && selected.completion &&
            (selected.completion.outcome === "NEEDS_FOLLOW_UP" || selected.completion.status === "REJECTED") &&
            (selected.status === "COMPLETED" || selected.status === "IN_PROGRESS") && (
              <form className="ops-form" onSubmit={event => void scheduleFollowUp(event)}>
                <h3>Schedule repair follow-up</h3>
                <p>Responsible party: {selected.work_order?.assignee_name ?? "No assigned technician"}</p>
                <label>Date and time<input name="follow_up_at" type="datetime-local" required /></label>
                <label>Reason<input name="reason" maxLength={500} required defaultValue={selected.completion.follow_up_reason ?? ""} /></label>
                <div className="ops-form-actions"><button className="ops-button ops-button--primary" disabled={busy || !selected.work_order?.assignee}>{busy ? "Saving…" : "Schedule follow-up"}</button></div>
              </form>
            )}
          {selected.work_order?.notes && <p className="ops-note">Work order notes: {selected.work_order.notes}</p>}
        </div>
      )}
    </section>
  );
}
