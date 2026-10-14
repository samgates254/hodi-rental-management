export function useRequiresApproval(quotationStatus: string | null | undefined) {
  return quotationStatus !== "APPROVED";
}