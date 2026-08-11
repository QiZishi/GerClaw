export interface PrescriptionCompletionField {
  id: string;
  label: string;
  max_length: number;
}

export function prescriptionTurnProgress(turns: number, maxTurns: number) {
  const completed = Math.max(0, Math.min(Math.trunc(turns), maxTurns));
  return {
    completed,
    remaining: Math.max(0, maxTurns - completed),
    limitReached: completed >= maxTurns,
  };
}

export function prescriptionMissingFields(
  fields: readonly PrescriptionCompletionField[],
  missingFieldIds: readonly string[],
): PrescriptionCompletionField[] {
  const missing = new Set(missingFieldIds);
  return fields.filter((field) => missing.has(field.id));
}

export function prepareManualPrescriptionAnswers(
  fields: readonly PrescriptionCompletionField[],
  values: Readonly<Record<string, string>>,
): { answers: Record<string, string>; firstMissingFieldId: string | null } {
  const answers: Record<string, string> = {};
  let firstMissingFieldId: string | null = null;
  for (const field of fields) {
    const value = (values[field.id] ?? "").trim();
    if (!value) {
      firstMissingFieldId ??= field.id;
      continue;
    }
    answers[field.id] = value.slice(0, field.max_length);
  }
  return { answers, firstMissingFieldId };
}
