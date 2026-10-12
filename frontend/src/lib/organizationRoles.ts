export const ORGANIZATION_STAFF_ROLES = [
  { value: "PROPERTY_MANAGER", label: "Property manager", loginKind: "landlord" },
  { value: "CARETAKER", label: "Caretaker", loginKind: "caretaker" },
  { value: "ACCOUNTANT", label: "Accountant", loginKind: "landlord" },
  { value: "TECHNICIAN", label: "Technician", loginKind: "technician" },
] as const;

export type OrganizationStaffRole = (typeof ORGANIZATION_STAFF_ROLES)[number]["value"];
export type StaffLoginKind = (typeof ORGANIZATION_STAFF_ROLES)[number]["loginKind"];

export function staffLoginKindForRole(role: string): StaffLoginKind | null {
  return ORGANIZATION_STAFF_ROLES.find(item => item.value === role)?.loginKind ?? null;
}

export const MAINTENANCE_ASSIGNEE_STAFF_ROLES = ORGANIZATION_STAFF_ROLES
  .filter(item => item.value !== "ACCOUNTANT")
  .map(item => item.value);
