/**
 * 五大处方类型定义
 */

export type PrescriptionType =
  | "exercise"
  | "nutrition"
  | "psychology"
  | "medication"
  | "smokingAlcohol"
  | "drug"
  | "rehabilitation";

export interface EvidenceSource {
  title: string;
  url?: string;
  snippet?: string;
  publishedDate?: string;
}

export interface BasicInfo {
  name?: string;
  age?: number;
  gender?: "male" | "female";
  height?: number;
  weight?: number;
  bmi?: number;
  education?: string;
  maritalStatus?: string;
  smoking?: boolean;
  alcohol?: boolean;
}

export interface HealthOverview {
  diseases?: Record<string, boolean | string>;
  mentalPsychology?: Record<string, unknown>;
  adl?: Record<string, unknown>;
  frailty?: Record<string, unknown>;
  sarcopenia?: Record<string, unknown>;
  mobility?: Record<string, unknown>;
  visionHearing?: Record<string, unknown>;
  fallRisk?: Record<string, unknown>;
  nutrition?: Record<string, unknown>;
  pain?: Record<string, unknown>;
  social?: Record<string, unknown>;
}

export interface Medication {
  name: string;
  specification?: string;
  usage?: string;
}

export interface ExamReport {
  [key: string]: unknown;
}

export interface MedicalRecord {
  chiefComplaint?: string;
  presentIllness?: string;
  pastHistory?: string;
  surgeryHistory?: string;
  allergyHistory?: string;
  physicalExam?: string;
  diagnoses?: string[];
  dischargeAdvice?: string;
}

export interface PrescriptionInput {
  basicInfo: BasicInfo;
  healthOverview?: HealthOverview;
  medications?: {
    inpatient?: Medication[];
    discharge?: Medication[];
  };
  examReports?: ExamReport;
  medicalRecords?: MedicalRecord;
  lifestyle?: {
    exercise?: string;
    diet?: string;
    sleep?: string;
  };
  rawText?: string;
}

export interface HealthProfile {
  summary: string;
  mainIssues: string[];
  riskAssessment: string;
}

export interface ExercisePrescription {
  recommendation: string;
  intensity: string;
  frequency: string;
  precautions: string[];
}

export interface NutritionPrescription {
  recommendation: string;
  dietaryPrinciples: string[];
  sampleMeal: string;
  precautions: string[];
}

export interface PsychologyPrescription {
  assessment: string;
  interventions: string[];
  referralSuggestion: string;
}

export interface MedicationPrescription {
  currentMeds: string[];
  interactions: string[];
  highRiskWarnings?: string[];
  suggestions: string[];
  precautions: string[];
}

export interface SmokingAlcoholPrescription {
  smokingStatus: string;
  alcoholStatus: string;
  advice: string[];
}

export interface PrescriptionOutput {
  healthProfile: HealthProfile;
  exercisePrescription: ExercisePrescription;
  nutritionPrescription: NutritionPrescription;
  psychologyPrescription: PsychologyPrescription;
  medicationPrescription: MedicationPrescription;
  smokingAlcoholPrescription: SmokingAlcoholPrescription;
  disclaimer: string;
}

export type PrescriptionStage =
  | "idle"
  | "welcome"
  | "collecting"
  | "health_profile"
  | "generating"
  | "validating"
  | "done"
  | "failed";

export interface CollectionQuestion {
  id: string;
  label: string;
  placeholder?: string;
  type: "text" | "textarea";
  required?: boolean;
}

export interface CollectionCardData {
  round: number;
  maxRounds: number;
  questions: CollectionQuestion[];
  answers: Record<string, string>;
}

export interface PrescriptionState {
  stage: PrescriptionStage;
  collectedInfo: PrescriptionInput;
  collectionRound: number;
  maxCollectionRounds: number;
  currentQuestions: CollectionQuestion[];
  healthProfileMarkdown?: string;
  finalMarkdown?: string;
  jsonOutput?: PrescriptionOutput;
  errorMessage?: string;
}

// 旧版处方组件兼容类型
export interface PatientSummary {
  age?: number;
  gender?: "male" | "female";
  chiefComplaint?: string;
  history?: string | string[];
  currentMedications?: string | string[];
  allergies?: string | string[];
  lifestyle?: string | string[];
  vitals?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PrescriptionItem {
  name: string;
  detail: string;
  dosage?: string;
  frequency?: string;
  duration?: string;
  precautions?: string | string[];
  evidence?: Array<{ title: string; url?: string }>;
  [key: string]: unknown;
}

export interface PrescriptionSection {
  type: string;
  title: string;
  summary: string;
  items: PrescriptionItem[];
  evidence?: Array<{ title: string; url?: string }>;
  [key: string]: unknown;
}

export interface PrescriptionReport {
  id: string;
  sessionId: string;
  createdAt: number;
  patient: PatientSummary;
  diagnosis: {
    summary: string;
    problems: string[];
    suspectedDiagnoses: string[];
    riskFactors: string[];
    [key: string]: unknown;
  };
  sections: PrescriptionSection[];
  citations: Array<{ title: string; url?: string }>;
  disclaimer: string;
  [key: string]: unknown;
}

export type ExportFormat = "markdown" | "png" | "jpg" | "pdf" | "docx";
