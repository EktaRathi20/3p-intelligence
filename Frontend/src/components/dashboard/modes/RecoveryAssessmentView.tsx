import {
  Fragment,
  useEffect,
  useMemo,
  useState,
  type FC,
  type ReactNode,
} from "react";
import {
  Calculator,
  CheckCircle2,
  ClipboardList,
  Download,
  FileText,
  FlaskConical,
  History,
  LoaderCircle,
  Pencil,
  Plus,
  Printer,
  RotateCcw,
  ShieldCheck,
  X,
  XCircle,
} from "lucide-react";
import { verifyToken } from "@/services/authApi";
import { ApiError } from "@/services/apiError";
import { httpClient } from "@/services/httpClient";
import { regionApi } from "@/services/regionApi";
import {
  assessmentFeedbackApi,
  assessmentsApi,
  damageAssessmentsApi,
  expensesApi,
  type AnalysisRow,
  type AssessmentDetail,
  type AssessmentFigure,
  type AssessmentStatus,
  type AssessmentSummary,
  type DamageAssessment,
  type DamageAssessmentInput,
  type ExpenseKind,
  type ExpenseRecord,
  type FeedbackItem,
  type ObservedInputs,
} from "@/services/recoveryApi";
import type { AuthUser } from "@/types";
import {
  canSubmitDamage,
  canSubmitExpense,
  displayCount,
  formatFigureValue,
  isRole4Reviewer,
} from "@/utils/recoveryReview";

const inputClass =
  "w-full border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none focus:border-[#18365b] disabled:bg-slate-100 disabled:text-slate-500";
const primaryButtonClass =
  "inline-flex items-center justify-center gap-1.5 bg-[#18365b] px-3 py-2 text-xs font-semibold text-white hover:bg-[#102744] disabled:cursor-not-allowed disabled:opacity-50";
const outlineButtonClass =
  "inline-flex items-center justify-center gap-1.5 border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";
const dangerButtonClass =
  "inline-flex items-center justify-center gap-1.5 bg-[#a12622] px-3 py-2 text-xs font-semibold text-white hover:bg-[#7f1d1a] disabled:cursor-not-allowed disabled:opacity-50";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusBadge({ status }: { status: AssessmentStatus }) {
  if (status === "approved") {
    return (
      <span className="inline-flex items-center gap-1 border border-emerald-700 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-800">
        <CheckCircle2 size={11} /> Government Approved
      </span>
    );
  }
  if (status === "rejected") {
    return (
      <span className="inline-flex items-center gap-1 border border-red-700 bg-red-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-800">
        <XCircle size={11} /> Rejected
      </span>
    );
  }
  return (
    <span className="inline-block border border-amber-600 bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-900">
      Pending Review
    </span>
  );
}

function ConfidenceBadge({ level }: { level: string }) {
  const tone =
    level === "High"
      ? "border-emerald-700 bg-emerald-50 text-emerald-800"
      : level === "Medium"
        ? "border-amber-600 bg-amber-50 text-amber-900"
        : "border-slate-400 bg-slate-100 text-slate-700";
  return (
    <span
      className={`inline-block border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${tone}`}
    >
      {level} confidence
    </span>
  );
}

function StatCell({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="border border-slate-300 bg-white px-4 py-3 shadow-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold tracking-tight text-[#18365b]">
        {value}
      </p>
      <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold text-slate-700">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="mt-1 block text-[11px] font-normal leading-4 text-slate-500">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

interface ManagedRegion {
  id: string;
  name: string;
  code?: string | null;
}

interface HazardType {
  id: string;
  name: string;
}

const OBSERVED_FIELDS: {
  key: keyof ObservedInputs;
  label: string;
  hint: string;
}[] = [
  {
    key: "householdsAffected",
    label: "Households affected",
    hint: "Observed households",
  },
  {
    key: "housesDamaged",
    label: "Houses damaged (repair)",
    hint: "Partial damage count",
  },
  {
    key: "housesDestroyed",
    label: "Houses destroyed (rebuild)",
    hint: "Full damage count",
  },
  {
    key: "cropHectares",
    label: "Crop area (hectares)",
    hint: "Affected hectares",
  },
  {
    key: "livestockLost",
    label: "Livestock lost (head)",
    hint: "Verified head count",
  },
  { key: "infraSites", label: "Infrastructure sites", hint: "Damaged sites" },
  { key: "roadsKm", label: "Roads damaged (km)", hint: "Kilometres" },
  {
    key: "preparationCostInr",
    label: "Preparation spend (Rs.)",
    hint: "Observed, if known",
  },
  {
    key: "recoveryCostInr",
    label: "Recovery spend (Rs.)",
    hint: "Observed, if known",
  },
];

const DAMAGE_COUNT_FIELDS: { key: string; label: string }[] = [
  { key: "householdsAffected", label: "Households affected" },
  { key: "housesDamaged", label: "Houses damaged" },
  { key: "housesDestroyed", label: "Houses destroyed" },
  { key: "cropHectares", label: "Crop area (ha)" },
  { key: "livestockLost", label: "Livestock lost" },
  { key: "infraSites", label: "Infra sites" },
  { key: "roadsKm", label: "Roads (km)" },
];

function damageCountsSummary(item: DamageAssessment): string {
  const parts: string[] = [];
  for (const field of DAMAGE_COUNT_FIELDS) {
    const value = (item as unknown as Record<string, number | null>)[field.key];
    if (value !== null && value !== undefined)
      parts.push(`${field.label}: ${value}`);
  }
  return parts.join(" · ") || "—";
}

/** Parse an optional numeric input: null when blank, undefined when invalid. */
function formatSignedPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function parseOptionalNumber(raw: string): number | null | undefined {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0) return undefined;
  return parsed;
}

export const RecoveryAssessmentView: FC = () => {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [userLoading, setUserLoading] = useState(true);

  const [regions, setRegions] = useState<ManagedRegion[]>([]);
  const [hazards, setHazards] = useState<HazardType[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [assessments, setAssessments] = useState<AssessmentSummary[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [listErrorStatus, setListErrorStatus] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | AssessmentStatus>(
    "all",
  );
  const [refreshKey, setRefreshKey] = useState(0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AssessmentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [formRegion, setFormRegion] = useState("");
  const [formHazard, setFormHazard] = useState("");
  const [formObserved, setFormObserved] = useState<Record<string, string>>({});
  const [formNotes, setFormNotes] = useState("");
  const [formSaving, setFormSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [expandedFigures, setExpandedFigures] = useState<Set<string>>(
    new Set(),
  );
  const [editDrafts, setEditDrafts] = useState<
    Record<
      string,
      { value: string; reason: string; saving: boolean; error: string | null }
    >
  >({});

  const [decisionAction, setDecisionAction] = useState<"accept" | "reject">(
    "accept",
  );
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const [regenReason, setRegenReason] = useState("");
  const [regenSaving, setRegenSaving] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [busyReport, setBusyReport] = useState<string | null>(null);

  const [analysis, setAnalysis] = useState<AnalysisRow[]>([]);
  const [analysisEngine, setAnalysisEngine] = useState("");
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [learningLoading, setLearningLoading] = useState(true);
  const [learningError, setLearningError] = useState<string | null>(null);

  const [damageItems, setDamageItems] = useState<DamageAssessment[]>([]);
  const [expenseItems, setExpenseItems] = useState<ExpenseRecord[]>([]);
  const [expenseTotal, setExpenseTotal] = useState(0);
  const [pipelineLoading, setPipelineLoading] = useState(true);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const [showDamageForm, setShowDamageForm] = useState(false);
  const [damageRegion, setDamageRegion] = useState("");
  const [damageHazard, setDamageHazard] = useState("");
  const [damageCounts, setDamageCounts] = useState<Record<string, string>>({});
  const [damageLocation, setDamageLocation] = useState("");
  const [damageNotes, setDamageNotes] = useState("");
  const [damageSaving, setDamageSaving] = useState(false);
  const [damageError, setDamageError] = useState<string | null>(null);

  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const [expenseRegion, setExpenseRegion] = useState("");
  const [expenseHazard, setExpenseHazard] = useState("");
  const [expenseKind, setExpenseKind] = useState<ExpenseKind>("preparedness");
  const [expenseCategory, setExpenseCategory] = useState("");
  const [expenseAmount, setExpenseAmount] = useState("");
  const [expenseReceipt, setExpenseReceipt] = useState("");
  const [expenseVendor, setExpenseVendor] = useState("");
  const [expenseSaving, setExpenseSaving] = useState(false);
  const [expenseError, setExpenseError] = useState<string | null>(null);

  const [notice, setNotice] = useState<string | null>(null);
  const canWrite = isRole4Reviewer(currentUser);
  const canDamage = canSubmitDamage(currentUser);
  const canExpense = canSubmitExpense(currentUser);

  useEffect(() => {
    let cancelled = false;
    verifyToken()
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .catch(() => {
        if (!cancelled) setCurrentUser(null);
      })
      .finally(() => {
        if (!cancelled) setUserLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      regionApi
        .getRegions()
        .then((result) => result.items as ManagedRegion[])
        .catch(() => [] as ManagedRegion[]),
      httpClient
        .get<{ hazards?: HazardType[] }>("/hazard-types")
        .then((r) => r.hazards ?? [])
        .catch(() => [] as HazardType[]),
    ]).then(([regionItems, hazardItems]) => {
      if (cancelled) return;
      setRegions(regionItems);
      setHazards(hazardItems);
      if (regionItems.length === 0 || hazardItems.length === 0) {
        setCatalogError(
          "Region or hazard catalogues are unavailable; assessment generation may be limited.",
        );
      } else {
        setCatalogError(null);
      }
      setFormRegion(
        (current) =>
          current || regionItems[0]?.code || regionItems[0]?.id || "",
      );
      setFormHazard((current) => current || hazardItems[0]?.id || "");
      setDamageRegion(
        (current) =>
          current || regionItems[0]?.code || regionItems[0]?.id || "",
      );
      setDamageHazard((current) => current || hazardItems[0]?.id || "");
      setExpenseRegion(
        (current) =>
          current || regionItems[0]?.code || regionItems[0]?.id || "",
      );
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    setListError(null);
    setListErrorStatus(null);
    assessmentsApi
      .list(statusFilter === "all" ? undefined : { status: statusFilter })
      .then((items) => {
        if (cancelled) return;
        setAssessments(items);
        setSelectedId((current) => {
          if (current && items.some((item) => item.id === current))
            return current;
          return items[0]?.id ?? null;
        });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setAssessments([]);
          setListError(
            error instanceof Error
              ? error.message
              : "Unable to load assessments.",
          );
          setListErrorStatus(
            error instanceof ApiError ? (error.status ?? null) : null,
          );
        }
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [statusFilter, refreshKey]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    assessmentsApi
      .get(selectedId)
      .then((result) => {
        if (!cancelled) setDetail(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(
            error instanceof Error
              ? error.message
              : "Unable to load the assessment.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    setLearningLoading(true);
    setLearningError(null);
    Promise.all([
      assessmentFeedbackApi
        .analysis()
        .catch(() => ({ engineVersion: "", rows: [] as AnalysisRow[] })),
      assessmentFeedbackApi.list().catch(() => [] as FeedbackItem[]),
    ])
      .then(([analysisResult, feedbackItems]) => {
        if (cancelled) return;
        setAnalysis(analysisResult.rows);
        setAnalysisEngine(analysisResult.engineVersion);
        setFeedback(feedbackItems);
      })
      .catch((error: unknown) => {
        if (!cancelled)
          setLearningError(
            error instanceof Error
              ? error.message
              : "Learning data is unavailable.",
          );
      })
      .finally(() => {
        if (!cancelled) setLearningLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  useEffect(() => {
    let cancelled = false;
    setPipelineLoading(true);
    setPipelineError(null);
    (async () => {
      try {
        const [damages, expenses] = await Promise.all([
          damageAssessmentsApi.list(),
          expensesApi.list(),
        ]);
        if (cancelled) return;
        setDamageItems(damages);
        setExpenseItems(expenses.expenses);
        setExpenseTotal(expenses.totalInr);
      } catch (error: unknown) {
        if (!cancelled) {
          setDamageItems([]);
          setExpenseItems([]);
          setExpenseTotal(0);
          setPipelineError(
            error instanceof Error
              ? error.message
              : "Unable to load field evidence.",
          );
        }
      } finally {
        if (!cancelled) setPipelineLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const counts = useMemo(
    () => ({
      total: assessments.length,
      pending: assessments.filter((a) => a.status === "pending_review").length,
      approved: assessments.filter((a) => a.status === "approved").length,
      rejected: assessments.filter((a) => a.status === "rejected").length,
    }),
    [assessments],
  );

  const toggleFigure = (key: string) => {
    setExpandedFigures((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const startEdit = (figure: AssessmentFigure) => {
    setEditDrafts((current) => ({
      ...current,
      [figure.key]: {
        value:
          figure.currentValue === null || figure.currentValue === undefined
            ? ""
            : String(figure.currentValue),
        reason: "",
        saving: false,
        error: null,
      },
    }));
  };

  const saveEdit = async (figure: AssessmentFigure) => {
    const draft = editDrafts[figure.key];
    if (!draft || !detail) return;
    if (!draft.reason.trim()) {
      setEditDrafts((current) => ({
        ...current,
        [figure.key]: {
          ...draft,
          error: "A reason is required for every correction.",
        },
      }));
      return;
    }
    const parsed = parseOptionalNumber(draft.value);
    if (parsed === undefined) {
      setEditDrafts((current) => ({
        ...current,
        [figure.key]: {
          ...draft,
          error: "Enter a non-negative number, or leave blank for Unknown.",
        },
      }));
      return;
    }
    setEditDrafts((current) => ({
      ...current,
      [figure.key]: { ...draft, saving: true, error: null },
    }));
    try {
      const updated = await assessmentsApi.edit(detail.id, [
        {
          path: `figures.${figure.key}`,
          newValue: parsed,
          reason: draft.reason.trim(),
        },
      ]);
      setDetail(updated);
      setEditDrafts((current) => {
        const next = { ...current };
        delete next[figure.key];
        return next;
      });
      setRefreshKey((value) => value + 1);
      setNotice(
        `Correction recorded for ${figure.label} (now v${updated.version}). The AI original is preserved.`,
      );
    } catch (error) {
      setEditDrafts((current) => ({
        ...current,
        [figure.key]: {
          ...draft,
          saving: false,
          error:
            error instanceof Error
              ? error.message
              : "Unable to save the correction.",
        },
      }));
    }
  };

  const submitDecision = async () => {
    if (!detail) return;
    if (!decisionReason.trim()) {
      setDecisionError("A decision reason is required.");
      return;
    }
    setDecisionSaving(true);
    setDecisionError(null);
    try {
      const updated = await assessmentsApi.decide(detail.id, {
        action: decisionAction,
        reason: decisionReason.trim(),
      });
      setDetail(updated);
      setDecisionReason("");
      setRefreshKey((value) => value + 1);
      setNotice(
        decisionAction === "accept"
          ? `Assessment ${updated.publicId} approved. Figures frozen; corrections stored as verified feedback.`
          : `Assessment ${updated.publicId} rejected. Corrections kept as unverified feedback only.`,
      );
    } catch (error) {
      setDecisionError(
        error instanceof Error
          ? error.message
          : "Unable to record the decision.",
      );
    } finally {
      setDecisionSaving(false);
    }
  };

  const submitDamage = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!damageRegion || !damageHazard) {
      setDamageError("Select a region and a hazard type.");
      return;
    }
    const input: DamageAssessmentInput = {
      regionKey: damageRegion,
      hazardId: damageHazard,
      locationNote: damageLocation.trim() || null,
      notes: damageNotes.trim(),
    };
    let filled = 0;
    for (const field of DAMAGE_COUNT_FIELDS) {
      const raw = (damageCounts[field.key] ?? "").trim();
      if (raw === "") continue;
      const parsed = Number(raw);
      if (!Number.isFinite(parsed) || parsed < 0) {
        setDamageError(`"${field.label}" must be a non-negative number.`);
        return;
      }
      (input as unknown as Record<string, number>)[field.key] = parsed;
      filled += 1;
    }
    if (filled === 0) {
      setDamageError("Enter at least one observed damage count.");
      return;
    }
    setDamageSaving(true);
    setDamageError(null);
    try {
      await damageAssessmentsApi.create(input);
      setDamageCounts({});
      setDamageLocation("");
      setDamageNotes("");
      setShowDamageForm(false);
      setRefreshKey((value) => value + 1);
      setNotice(
        "Damage submission recorded. New assessments for this region and hazard will use it.",
      );
    } catch (error) {
      setDamageError(
        error instanceof Error
          ? error.message
          : "Unable to save the damage submission.",
      );
    } finally {
      setDamageSaving(false);
    }
  };

  const submitExpense = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!expenseRegion) {
      setExpenseError("Select a region.");
      return;
    }
    if (!expenseCategory.trim()) {
      setExpenseError(
        "Enter a spend category (e.g. fuel, shelter material, transport).",
      );
      return;
    }
    const amount = Number(expenseAmount.trim());
    if (!Number.isFinite(amount) || amount <= 0) {
      setExpenseError("Enter an amount greater than zero.");
      return;
    }
    setExpenseSaving(true);
    setExpenseError(null);
    try {
      await expensesApi.create({
        regionKey: expenseRegion,
        hazardId: expenseHazard || null,
        kind: expenseKind,
        category: expenseCategory.trim(),
        amountInr: amount,
        receiptRef: expenseReceipt.trim() || null,
        vendor: expenseVendor.trim() || null,
      });
      setExpenseCategory("");
      setExpenseAmount("");
      setExpenseReceipt("");
      setExpenseVendor("");
      setShowExpenseForm(false);
      setRefreshKey((value) => value + 1);
      setNotice(
        "Expense record saved. New assessments will use it as observed spend before modelled proxies.",
      );
    } catch (error) {
      setExpenseError(
        error instanceof Error
          ? error.message
          : "Unable to save the expense record.",
      );
    } finally {
      setExpenseSaving(false);
    }
  };

  const submitGenerate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!formRegion || !formHazard) {
      setFormError("Select a region and a hazard type.");
      return;
    }
    const observed: ObservedInputs = {};
    for (const field of OBSERVED_FIELDS) {
      const raw = (formObserved[field.key] ?? "").trim();
      if (raw === "") continue;
      const parsed = Number(raw);
      if (!Number.isFinite(parsed) || parsed < 0) {
        setFormError(`"${field.label}" must be a non-negative number.`);
        return;
      }
      (observed as Record<string, number>)[field.key] = parsed;
    }
    setFormSaving(true);
    setFormError(null);
    try {
      const created = await assessmentsApi.create({
        regionKey: formRegion,
        hazardId: formHazard,
        observed,
        notes: formNotes.trim(),
      });
      setShowForm(false);
      setFormObserved({});
      setFormNotes("");
      setSelectedId(created.id);
      setRefreshKey((value) => value + 1);
      setNotice(
        `Assessment ${created.publicId} generated and awaiting officer review.`,
      );
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "Unable to generate the assessment.",
      );
    } finally {
      setFormSaving(false);
    }
  };

  const downloadPdf = async (version?: number) => {
    if (!detail) return;
    const key = version === undefined ? "latest" : `v${version}`;
    setBusyReport(key);
    try {
      const { blob, filename } = await assessmentsApi.downloadReport(
        detail.id,
        version,
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "Unable to download the report.",
      );
    } finally {
      setBusyReport(null);
    }
  };

  const printPdf = async () => {
    if (!detail) return;
    setBusyReport("print");
    try {
      const { blob } = await assessmentsApi.downloadReport(detail.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "Unable to open the report for printing.",
      );
    } finally {
      setBusyReport(null);
    }
  };

  const submitRegenerate = async () => {
    if (!detail) return;
    if (!regenReason.trim()) {
      setRegenError("A reason is required to issue a new report version.");
      return;
    }
    setRegenSaving(true);
    setRegenError(null);
    try {
      const reports = await assessmentsApi.regenerateReport(
        detail.id,
        regenReason.trim(),
      );
      setDetail({ ...detail, reportVersions: reports });
      setRegenReason("");
      setNotice(
        `Report v${reports.length} issued. Previous versions are preserved below.`,
      );
    } catch (error) {
      setRegenError(
        error instanceof Error
          ? error.message
          : "Unable to regenerate the report.",
      );
    } finally {
      setRegenSaving(false);
    }
  };

  const ai = detail?.aiAssessment ?? null;
  const figures = detail?.current.figures ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-col justify-end gap-2 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          className="inline-flex items-center justify-center gap-1.5 border border-dark bg-dark px-4 py-2 text-xs font-bold text-dark hover:bg-white/20"
        >
          <RotateCcw size={15} /> Refresh
        </button>
        <button
          type="button"
          onClick={() => setShowForm((open) => !open)}
          disabled={!canWrite}
          title={
            canWrite
              ? undefined
              : "Requires the Insurance Recovery Officer (Role 4) role"
          }
          className="inline-flex items-center justify-center gap-1.5 bg-white px-4 py-2 text-xs font-bold text-[#18365b] hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Plus size={15} /> {showForm ? "Close generator" : "New Assessment"}
        </button>
      </div>


      {notice && (
        <div
          role="status"
          className="flex items-start justify-between gap-3 border border-blue-800 bg-blue-50 px-3 py-2 text-xs text-blue-900 shadow-sm"
        >
          <span className="leading-5">{notice}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            aria-label="Dismiss message"
            className="shrink-0 p-0.5 hover:opacity-70"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCell
          label="Assessments"
          value={displayCount({
            loading: listLoading,
            error: listError,
            count: counts.total,
          })}
          hint="All records in scope"
        />
        <StatCell
          label="Pending review"
          value={displayCount({
            loading: listLoading,
            error: listError,
            count: counts.pending,
          })}
          hint="Awaiting Role 4 decision"
        />
        <StatCell
          label="Government approved"
          value={displayCount({
            loading: listLoading,
            error: listError,
            count: counts.approved,
          })}
          hint="Frozen official records"
        />
        <StatCell
          label="Rejected"
          value={displayCount({
            loading: listLoading,
            error: listError,
            count: counts.rejected,
          })}
          hint="Not approved for action"
        />
      </div>

      {showForm && (
        <section
          className="border border-slate-300 bg-white shadow-sm"
          aria-label="Generate assessment"
        >
          <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
            <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
              <Calculator size={15} /> Generate AI Assessment
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              The engine analyses stored region, task, field-report,
              damage-submission, and expense data plus your observed inputs.
              Every figure will show its calculation, assumptions, sources, and
              confidence.
            </p>
          </div>
          <form onSubmit={submitGenerate} className="space-y-4 p-4">
            {catalogError && (
              <p
                role="note"
                className="border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
              >
                {catalogError}
              </p>
            )}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Region">
                <select
                  value={formRegion}
                  onChange={(e) => setFormRegion(e.target.value)}
                  disabled={!canWrite}
                  className={inputClass}
                >
                  {regions.map((region) => (
                    <option key={region.id} value={region.code || region.id}>
                      {region.name}
                      {region.code ? ` (${region.code})` : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Hazard type">
                <select
                  value={formHazard}
                  onChange={(e) => setFormHazard(e.target.value)}
                  disabled={!canWrite}
                  className={inputClass}
                >
                  {hazards.map((hazard) => (
                    <option key={hazard.id} value={hazard.id}>
                      {hazard.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold text-slate-700">
                Observed inputs (optional — leave blank when unknown)
              </p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {OBSERVED_FIELDS.map((field) => (
                  <Field key={field.key} label={field.label} hint={field.hint}>
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={formObserved[field.key] ?? ""}
                      onChange={(e) =>
                        setFormObserved((current) => ({
                          ...current,
                          [field.key]: e.target.value,
                        }))
                      }
                      disabled={!canWrite}
                      className={inputClass}
                    />
                  </Field>
                ))}
              </div>
            </div>
            <Field
              label="Officer notes"
              hint="Context for the reviewing officer (stored with the assessment)."
            >
              <textarea
                value={formNotes}
                onChange={(e) => setFormNotes(e.target.value)}
                rows={2}
                disabled={!canWrite}
                className={`${inputClass} resize-y`}
              />
            </Field>
            {formError && (
              <p
                role="alert"
                className="border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900"
              >
                {formError}
              </p>
            )}
            <button
              type="submit"
              disabled={formSaving || !canWrite}
              className={primaryButtonClass}
            >
              {formSaving ? "Generating…" : "Generate assessment"}
            </button>
          </form>
        </section>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <section
          className="border border-slate-300 bg-white shadow-sm"
          aria-label="Assessments"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
            <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
              <ClipboardList size={15} /> Assessments
            </h3>
            <select
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as typeof statusFilter)
              }
              className="border border-slate-300 bg-white px-2 py-1.5 text-xs outline-none focus:border-[#18365b]"
              aria-label="Filter by status"
            >
              <option value="all">All states</option>
              <option value="pending_review">Pending review</option>
              <option value="approved">Government approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          {listLoading ? (
            <p
              role="status"
              className="flex items-center gap-2 px-4 py-6 text-sm text-slate-600"
            >
              <LoaderCircle size={15} className="animate-spin" /> Loading
              assessments…
            </p>
          ) : listError ? (
            <div
              role="alert"
              className="m-4 border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
            >
              <p className="font-semibold">
                Assessment records could not be loaded — the counters above are
                unknown, not zero.
              </p>
              <p className="mt-1">{listError}</p>
              {listErrorStatus === 404 ? (
                <p className="mt-1">
                  The server does not recognise the assessment endpoints.
                  Restart the backend server so it loads the Recovery update,
                  then retry.
                </p>
              ) : (
                <p className="mt-1">
                  If this keeps failing after the Recovery update, restart the
                  backend server so it loads the latest endpoints, then retry.
                </p>
              )}
              <button
                type="button"
                onClick={() => setRefreshKey((v) => v + 1)}
                className="mt-1 font-semibold underline underline-offset-2"
              >
                Retry
              </button>
            </div>
          ) : assessments.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-600">
              No assessments yet. Generate the first one above.
            </p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {assessments.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(item.id);
                      setNotice(null);
                    }}
                    className={`block w-full p-4 text-left hover:bg-slate-50 ${selectedId === item.id ? "border-l-4 border-l-[#d88b2b] bg-blue-50/50" : "border-l-4 border-l-transparent"}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-bold text-[#18365b]">
                        {item.publicId}
                      </span>
                      <span className="ml-auto">
                        <StatusBadge status={item.status} />
                      </span>
                    </div>
                    <p className="mt-1 text-sm font-semibold text-slate-900">
                      {item.regionName} · {item.hazardName}
                    </p>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      v{item.version} · {item.overallConfidence} confidence ·{" "}
                      {item.editCount} correction(s) · grand total{" "}
                      {formatFigureValue(item.totals.grandTotalInr, "INR")}
                    </p>
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      {formatDateTime(item.updatedAt)} · by {item.createdByName}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section
          className="border border-slate-300 bg-white shadow-sm"
          aria-label="Assessment detail"
        >
          {detailLoading ? (
            <p
              role="status"
              className="flex items-center gap-2 px-4 py-6 text-sm text-slate-600"
            >
              <LoaderCircle size={15} className="animate-spin" /> Loading
              assessment…
            </p>
          ) : detailError ? (
            <p
              role="alert"
              className="m-4 border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
            >
              {detailError}
            </p>
          ) : !detail || !ai ? (
            <p className="px-4 py-6 text-sm text-slate-600">
              Select an assessment to review its AI reasoning, figures, and
              history.
            </p>
          ) : (
            <div>
              <div
                className={`border-b px-4 py-3 ${detail.status === "approved" ? "border-emerald-700 bg-emerald-50" : detail.status === "rejected" ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50"}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-bold text-[#18365b]">
                    {detail.publicId}
                  </span>
                  <StatusBadge status={detail.status} />
                  <ConfidenceBadge level={ai.overallConfidence} />
                  <span className="ml-auto text-[10px] text-slate-500">
                    assessment v{detail.version} · engine {ai.engineVersion}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  {ai.regionName} · {ai.hazardName} · created{" "}
                  {formatDateTime(detail.createdAt)} by {detail.createdByName} ·
                  narrative: {ai.narrativeSource}
                </p>
              </div>

              <div className="space-y-5 p-4">
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
                    What happened — AI analysis
                  </h4>
                  <p className="mt-1 text-sm leading-6 text-slate-800">
                    {ai.narrative}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Affected areas: {(ai.affectedAreas || []).join("; ") || "—"}
                  </p>
                  <details className="mt-2 border border-slate-200 px-3 py-2 text-xs text-slate-700">
                    <summary className="cursor-pointer font-semibold text-[#18365b]">
                      Why the system reached this conclusion (
                      {ai.reasoning.length} reasoning steps)
                    </summary>
                    <ol className="mt-1.5 list-decimal space-y-1 pl-5 leading-5">
                      {ai.reasoning.map((line, index) => (
                        <li key={index}>{line}</li>
                      ))}
                    </ol>
                  </details>
                  <p className="mt-2 border border-slate-200 bg-slate-50 px-2.5 py-2 text-[11px] leading-5 text-slate-600">
                    {ai.disclaimer}
                  </p>
                </div>

                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
                    Damage, costs &amp; relief figures
                  </h4>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full min-w-[640px] text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
                          <th className="px-2 py-2 font-semibold">Item</th>
                          <th className="px-2 py-2 font-semibold">
                            AI estimate
                          </th>
                          <th className="px-2 py-2 font-semibold">
                            {detail.status === "approved"
                              ? "Approved"
                              : "Current"}
                          </th>
                          <th className="px-2 py-2 font-semibold">
                            Confidence
                          </th>
                          <th className="px-2 py-2 font-semibold">Workings</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {figures.map((figure) => {
                          const draft = editDrafts[figure.key];
                          const expanded = expandedFigures.has(figure.key);
                          return (
                            <Fragment key={figure.key}>
                              <tr className="align-top hover:bg-slate-50">
                                <td className="px-2 py-2 font-medium text-slate-900">
                                  {figure.label}
                                  {figure.edited && (
                                    <span className="ml-1 border border-blue-800 bg-blue-50 px-1 py-0.5 text-[9px] font-bold uppercase text-blue-900">
                                      corrected
                                    </span>
                                  )}
                                  {figure.calibratedFrom && (
                                    <span className="ml-1 border border-emerald-700 bg-emerald-50 px-1 py-0.5 text-[9px] font-bold uppercase text-emerald-800">
                                      calibrated
                                    </span>
                                  )}
                                </td>
                                <td className="whitespace-nowrap px-2 py-2 text-slate-700">
                                  {formatFigureValue(figure.value, figure.unit)}
                                </td>
                                <td className="whitespace-nowrap px-2 py-2 font-semibold text-slate-900">
                                  {formatFigureValue(
                                    figure.currentValue,
                                    figure.unit,
                                  )}
                                </td>
                                <td className="px-2 py-2">
                                  <ConfidenceBadge level={figure.confidence} />
                                </td>
                                <td className="px-2 py-2">
                                  <div className="flex flex-wrap gap-1.5">
                                    <button
                                      type="button"
                                      onClick={() => toggleFigure(figure.key)}
                                      className={outlineButtonClass}
                                    >
                                      {expanded ? "Hide" : "Why?"}
                                    </button>
                                    {detail.status === "pending_review" &&
                                      canWrite &&
                                      !draft && (
                                        <button
                                          type="button"
                                          onClick={() => startEdit(figure)}
                                          className={outlineButtonClass}
                                          aria-label={`Correct ${figure.label}`}
                                        >
                                          <Pencil size={12} /> Correct
                                        </button>
                                      )}
                                  </div>
                                </td>
                              </tr>
                              {expanded && (
                                <tr
                                  key={`${figure.key}-why`}
                                  className="bg-slate-50/60"
                                >
                                  <td
                                    colSpan={5}
                                    className="px-3 py-3 text-xs leading-5 text-slate-700"
                                  >
                                    <p>
                                      <strong>Calculation:</strong>{" "}
                                      {figure.calculation}
                                    </p>
                                    <p className="mt-1">
                                      <strong>Explanation:</strong>{" "}
                                      {figure.explanation}
                                    </p>
                                    <p className="mt-1">
                                      <strong>Assumptions:</strong>{" "}
                                      {figure.assumptions.length > 0
                                        ? figure.assumptions.join(" ")
                                        : "—"}
                                    </p>
                                    <p className="mt-1">
                                      <strong>Sources:</strong>{" "}
                                      {figure.sources.length > 0
                                        ? figure.sources
                                            .map(
                                              (s) =>
                                                `${s.name} (${s.detail}; at ${s.fetchedAt})`,
                                            )
                                            .join("; ")
                                        : "—"}
                                    </p>
                                    {figure.calibratedFrom && (
                                      <p className="mt-1">
                                        <strong>Learning calibration:</strong>{" "}
                                        {formatSignedPct(
                                          figure.calibratedFrom.appliedDeltaPct,
                                        )}{" "}
                                        applied from{" "}
                                        {figure.calibratedFrom.feedbackCount}{" "}
                                        verified corrections (median{" "}
                                        {formatSignedPct(
                                          figure.calibratedFrom.medianDeltaPct,
                                        )}
                                        ).
                                      </p>
                                    )}
                                  </td>
                                </tr>
                              )}
                              {draft && (
                                <tr
                                  key={`${figure.key}-edit`}
                                  className="bg-blue-50/50"
                                >
                                  <td colSpan={5} className="px-3 py-3">
                                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                      <Field
                                        label={`Corrected value (${figure.unit})`}
                                        hint="Blank means Unknown."
                                      >
                                        <input
                                          type="number"
                                          min="0"
                                          step="any"
                                          value={draft.value}
                                          onChange={(e) =>
                                            setEditDrafts((current) => ({
                                              ...current,
                                              [figure.key]: {
                                                ...draft,
                                                value: e.target.value,
                                              },
                                            }))
                                          }
                                          disabled={draft.saving}
                                          className={inputClass}
                                        />
                                      </Field>
                                      <Field
                                        label="Reason (required)"
                                        hint="Recorded permanently with your name and timestamp."
                                      >
                                        <input
                                          value={draft.reason}
                                          onChange={(e) =>
                                            setEditDrafts((current) => ({
                                              ...current,
                                              [figure.key]: {
                                                ...draft,
                                                reason: e.target.value,
                                              },
                                            }))
                                          }
                                          disabled={draft.saving}
                                          placeholder="e.g. Block survey revised the count to…"
                                          className={inputClass}
                                        />
                                      </Field>
                                    </div>
                                    {draft.error && (
                                      <p
                                        role="alert"
                                        className="mt-2 text-xs text-red-700"
                                      >
                                        {draft.error}
                                      </p>
                                    )}
                                    <div className="mt-2 flex gap-2">
                                      <button
                                        type="button"
                                        onClick={() => saveEdit(figure)}
                                        disabled={draft.saving}
                                        className={primaryButtonClass}
                                      >
                                        {draft.saving
                                          ? "Saving…"
                                          : "Save correction"}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() =>
                                          setEditDrafts((current) => {
                                            const next = { ...current };
                                            delete next[figure.key];
                                            return next;
                                          })
                                        }
                                        disabled={draft.saving}
                                        className={outlineButtonClass}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-xs text-slate-600">
                    <strong>Totals:</strong> damage{" "}
                    {formatFigureValue(
                      detail.current.totals.damageTotalInr,
                      "INR",
                    )}
                    {detail.current.totals.damageTotalOverride
                      ? " (officer override)"
                      : " (derived)"}{" "}
                    · preparation{" "}
                    {formatFigureValue(
                      detail.current.totals.preparationInr,
                      "INR",
                    )}{" "}
                    · recovery{" "}
                    {formatFigureValue(
                      detail.current.totals.recoveryInr,
                      "INR",
                    )}{" "}
                    · grand total{" "}
                    {formatFigureValue(
                      detail.current.totals.grandTotalInr,
                      "INR",
                    )}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {ai.insuranceNotes}
                  </p>
                </div>

                {detail.status === "pending_review" && (
                  <div className="border border-slate-300 p-3">
                    <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
                      Officer decision
                    </h4>
                    <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <Field label="Action">
                        <select
                          value={decisionAction}
                          onChange={(e) =>
                            setDecisionAction(
                              e.target.value as typeof decisionAction,
                            )
                          }
                          disabled={!canWrite || decisionSaving}
                          className={inputClass}
                        >
                          <option value="accept">
                            Accept — approve as government record
                          </option>
                          <option value="reject">
                            Reject — inputs unreliable
                          </option>
                        </select>
                      </Field>
                      <Field label="Reason (required)">
                        <input
                          value={decisionReason}
                          onChange={(e) => setDecisionReason(e.target.value)}
                          disabled={!canWrite || decisionSaving}
                          placeholder="Justification for the decision…"
                          className={inputClass}
                        />
                      </Field>
                    </div>
                    {decisionError && (
                      <p role="alert" className="mt-2 text-xs text-red-700">
                        {decisionError}
                      </p>
                    )}
                    <div className="mt-2">
                      {decisionAction === "accept" ? (
                        <button
                          type="button"
                          onClick={submitDecision}
                          disabled={!canWrite || decisionSaving}
                          className={primaryButtonClass}
                        >
                          <CheckCircle2 size={13} />{" "}
                          {decisionSaving
                            ? "Recording…"
                            : "Accept & freeze figures"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={submitDecision}
                          disabled={!canWrite || decisionSaving}
                          className={dangerButtonClass}
                        >
                          <XCircle size={13} />{" "}
                          {decisionSaving ? "Recording…" : "Reject assessment"}
                        </button>
                      )}
                    </div>
                    <p className="mt-2 text-[11px] text-slate-500">
                      Accepting freezes the figures permanently and stores
                      corrections as verified feedback. Rejecting keeps
                      corrections as unverified only. Decided records cannot be
                      edited.
                    </p>
                  </div>
                )}

                {detail.decision && (
                  <div
                    className={`border p-3 text-xs ${detail.decision.action === "accepted" ? "border-emerald-700 bg-emerald-50 text-emerald-900" : "border-red-700 bg-red-50 text-red-900"}`}
                  >
                    <strong>Decision: {detail.decision.action}</strong> by{" "}
                    {detail.decision.byName} ·{" "}
                    {formatDateTime(detail.decision.at)} · v
                    {detail.decision.version}
                    <p className="mt-1">Reason: {detail.decision.reason}</p>
                  </div>
                )}

                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
                    Official corrections ({detail.officialEdits.length})
                  </h4>
                  {detail.officialEdits.length === 0 ? (
                    <p className="mt-1 text-xs text-slate-600">
                      No corrections — AI figures reviewed as generated.
                    </p>
                  ) : (
                    <ul className="mt-2 divide-y divide-slate-200 border border-slate-200">
                      {detail.officialEdits.map((edit, index) => (
                        <li
                          key={`${edit.at}-${index}`}
                          className="px-3 py-2 text-xs"
                        >
                          <p className="font-semibold text-slate-900">
                            {edit.label}: {edit.oldValue ?? "Unknown"} →{" "}
                            {edit.newValue ?? "Unknown"}
                          </p>
                          <p className="mt-0.5 text-slate-700">
                            Reason: {edit.reason}
                          </p>
                          <p className="mt-0.5 text-[10px] text-slate-500">
                            {edit.byName} · {formatDateTime(edit.at)} · AI
                            original was {edit.aiValue ?? "Unknown"}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-600">
                    <FileText size={13} /> Official reports{" "}
                    {detail.status === "approved"
                      ? ""
                      : "(available after approval)"}
                  </h4>
                  {detail.status !== "approved" ? (
                    <p className="mt-1 text-xs text-slate-600">
                      Only government-approved assessments have final official
                      reports.
                    </p>
                  ) : (
                    <div className="mt-2 space-y-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => downloadPdf()}
                          disabled={busyReport !== null}
                          className={primaryButtonClass}
                        >
                          <Download size={13} />{" "}
                          {busyReport === "latest"
                            ? "Preparing…"
                            : "Download PDF"}
                        </button>
                        <button
                          type="button"
                          onClick={printPdf}
                          disabled={busyReport !== null}
                          className={outlineButtonClass}
                        >
                          <Printer size={13} />{" "}
                          {busyReport === "print" ? "Opening…" : "Print"}
                        </button>
                      </div>
                      {detail.reportVersions.length > 0 && (
                        <ul className="divide-y divide-slate-200 border border-slate-200">
                          {[...detail.reportVersions]
                            .sort((a, b) => b.version - a.version)
                            .map((report) => (
                              <li
                                key={report.version}
                                className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs"
                              >
                                <span className="font-mono font-bold text-[#18365b]">
                                  v{report.version}
                                </span>
                                <span className="text-slate-600">
                                  {report.filename} ·{" "}
                                  {(report.byteSize / 1024).toFixed(1)} KB
                                </span>
                                <span className="text-[10px] text-slate-500">
                                  {formatDateTime(report.generatedAt)} · by{" "}
                                  {report.generatedByName} · {report.reason}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => downloadPdf(report.version)}
                                  disabled={busyReport !== null}
                                  className="ml-auto text-[11px] font-semibold text-[#18365b] underline underline-offset-2 disabled:opacity-50"
                                >
                                  {busyReport === `v${report.version}`
                                    ? "Preparing…"
                                    : "Download"}
                                </button>
                              </li>
                            ))}
                        </ul>
                      )}
                      {canWrite && (
                        <div className="border border-slate-200 bg-slate-50 p-3">
                          <Field
                            label="Issue a new report version"
                            hint="Previous versions stay preserved. Reason is required."
                          >
                            <div className="flex flex-col gap-2 sm:flex-row">
                              <input
                                value={regenReason}
                                onChange={(e) => setRegenReason(e.target.value)}
                                disabled={regenSaving}
                                placeholder="Why is a new report version needed?"
                                className={inputClass}
                              />
                              <button
                                type="button"
                                onClick={submitRegenerate}
                                disabled={regenSaving}
                                className={outlineButtonClass}
                              >
                                {regenSaving
                                  ? "Issuing…"
                                  : "Issue v" +
                                    (detail.reportVersions.length + 1)}
                              </button>
                            </div>
                          </Field>
                          {regenError && (
                            <p
                              role="alert"
                              className="mt-1 text-xs text-red-700"
                            >
                              {regenError}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-600">
                      <History size={13} /> Approval history
                    </h4>
                    <ul className="mt-2 divide-y divide-slate-200 border border-slate-200">
                      {detail.approvalHistory.map((entry, index) => (
                        <li
                          key={`${entry.at}-${index}`}
                          className="px-3 py-2 text-xs"
                        >
                          <p className="font-semibold text-slate-900">
                            {entry.action} · v{entry.version}
                          </p>
                          <p className="text-slate-700">{entry.reason}</p>
                          <p className="text-[10px] text-slate-500">
                            {entry.byName} · {formatDateTime(entry.at)}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
                      Evidence
                    </h4>
                    <div className="mt-2 border border-slate-200 px-3 py-2 text-xs text-slate-700">
                      <p>
                        {ai.evidenceSummary.taskCount} task(s) ·{" "}
                        {ai.evidenceSummary.submittedTaskCount} submitted ·{" "}
                        {ai.evidenceSummary.reportCount} field report(s) ·{" "}
                        {ai.evidenceSummary.peopleAssistedSum} assisted ·{" "}
                        {ai.evidenceSummary.verifiedFeedbackCount} verified
                        correction(s)
                      </p>
                      <p className="mt-1">
                        {ai.evidenceSummary.damageAssessmentCount ?? 0} damage
                        submission(s) · {ai.evidenceSummary.expenseCount ?? 0}{" "}
                        expense record(s) ·{" "}
                        {ai.evidenceSummary.evidenceAttachmentCount ?? 0}{" "}
                        evidence attachment(s) ·{" "}
                        {ai.evidenceSummary.photoCount ?? 0} photo(s)
                      </p>
                      {ai.evidenceSummary.observedPreparednessInr ||
                      ai.evidenceSummary.observedRecoveryInr ? (
                        <p className="mt-1">
                          Observed spend: preparation{" "}
                          {formatFigureValue(
                            ai.evidenceSummary.observedPreparednessInr ?? 0,
                            "INR",
                          )}{" "}
                          · recovery{" "}
                          {formatFigureValue(
                            ai.evidenceSummary.observedRecoveryInr ?? 0,
                            "INR",
                          )}
                        </p>
                      ) : null}
                      {ai.evidenceSummary.regionalPopulationNote && (
                        <p className="mt-1 text-[11px] leading-4 text-slate-500">
                          Population context:{" "}
                          {ai.evidenceSummary.regionalPopulationNote}
                        </p>
                      )}
                      {ai.evidenceSummary.gaps.length > 0 && (
                        <p className="mt-1 text-amber-900">
                          Gaps: {ai.evidenceSummary.gaps.join(" ")}
                        </p>
                      )}
                      {(ai.evidenceExcerpts || []).length > 0 && (
                        <ul className="mt-2 space-y-1.5">
                          {ai.evidenceExcerpts.map((excerpt, index) => (
                            <li
                              key={index}
                              className="border-l-2 border-[#18365b] bg-slate-50 px-2 py-1 text-[11px] leading-4"
                            >
                              {excerpt.text}
                              <span className="block text-[10px] text-slate-500">
                                {excerpt.byName} · {formatDateTime(excerpt.at)}
                                {excerpt.locationNote
                                  ? ` · ${excerpt.locationNote}`
                                  : ""}
                                {excerpt.photoCount
                                  ? ` · ${excerpt.photoCount} photo(s)`
                                  : ""}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                      {ai.officerNotes && (
                        <p className="mt-2">
                          <strong>Requesting notes:</strong> {ai.officerNotes}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      <section
        className="border border-slate-300 bg-white shadow-sm"
        aria-label="Field evidence and spend"
      >
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
            <ClipboardList size={15} /> Field evidence &amp; spend
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Officer damage counts and expense records feed new assessments
            directly: counts are summed per damage field, and observed spend is
            used before modelled proxies. Past assessments never change.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
                Damage submissions (
                {displayCount({
                  loading: pipelineLoading,
                  error: pipelineError,
                  count: damageItems.length,
                })}
                )
              </h4>
              {canDamage && (
                <button
                  type="button"
                  onClick={() => setShowDamageForm((open) => !open)}
                  className="ml-auto inline-flex items-center gap-1 border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                >
                  <Plus size={12} />{" "}
                  {showDamageForm ? "Close" : "Submit damage"}
                </button>
              )}
            </div>
            {showDamageForm && canDamage && (
              <form
                onSubmit={submitDamage}
                className="mb-3 space-y-3 border border-slate-200 bg-slate-50 p-3"
              >
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Field label="Region">
                    <select
                      value={damageRegion}
                      onChange={(e) => setDamageRegion(e.target.value)}
                      disabled={damageSaving}
                      className={inputClass}
                    >
                      {regions.map((region) => (
                        <option
                          key={region.id}
                          value={region.code || region.id}
                        >
                          {region.name}
                          {region.code ? ` (${region.code})` : ""}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Hazard type">
                    <select
                      value={damageHazard}
                      onChange={(e) => setDamageHazard(e.target.value)}
                      disabled={damageSaving}
                      className={inputClass}
                    >
                      {hazards.map((hazard) => (
                        <option key={hazard.id} value={hazard.id}>
                          {hazard.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {DAMAGE_COUNT_FIELDS.map((field) => (
                    <Field key={field.key} label={field.label}>
                      <input
                        type="number"
                        min="0"
                        step="any"
                        value={damageCounts[field.key] ?? ""}
                        onChange={(e) =>
                          setDamageCounts((current) => ({
                            ...current,
                            [field.key]: e.target.value,
                          }))
                        }
                        disabled={damageSaving}
                        className={inputClass}
                      />
                    </Field>
                  ))}
                </div>
                <Field
                  label="Location note"
                  hint="Free text, up to 300 characters."
                >
                  <input
                    value={damageLocation}
                    onChange={(e) => setDamageLocation(e.target.value)}
                    disabled={damageSaving}
                    placeholder="e.g. Canal Road, Ward 08"
                    className={inputClass}
                  />
                </Field>
                <Field label="Notes">
                  <textarea
                    value={damageNotes}
                    onChange={(e) => setDamageNotes(e.target.value)}
                    rows={2}
                    disabled={damageSaving}
                    className={`${inputClass} resize-y`}
                  />
                </Field>
                {damageError && (
                  <p role="alert" className="text-xs text-red-700">
                    {damageError}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={damageSaving}
                  className={primaryButtonClass}
                >
                  {damageSaving ? "Saving…" : "Save damage submission"}
                </button>
              </form>
            )}
            {pipelineLoading ? (
              <p
                role="status"
                className="flex items-center gap-2 border border-slate-200 px-3 py-4 text-xs text-slate-600"
              >
                <LoaderCircle size={14} className="animate-spin" /> Loading
                damage submissions…
              </p>
            ) : pipelineError ? (
              <p
                role="alert"
                className="border border-amber-300 bg-amber-50 px-3 py-3 text-xs text-amber-900"
              >
                {pipelineError}
              </p>
            ) : damageItems.length === 0 ? (
              <p className="border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-600">
                No damage submissions yet.
              </p>
            ) : (
              <ul className="max-h-96 divide-y divide-slate-200 overflow-y-auto border border-slate-200">
                {damageItems.map((item) => (
                  <li key={item.id} className="px-3 py-2 text-xs">
                    <p className="font-semibold text-slate-900">
                      {item.regionKey} · {item.hazardId}
                    </p>
                    <p className="mt-0.5 text-slate-700">
                      {damageCountsSummary(item)}
                    </p>
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      {item.createdByName} · {formatDateTime(item.createdAt)}
                      {item.locationNote ? ` · ${item.locationNote}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h4 className="text-xs font-bold uppercase tracking-wide text-slate-600">
                Expense records (
                {displayCount({
                  loading: pipelineLoading,
                  error: pipelineError,
                  count: expenseItems.length,
                })}
                )
              </h4>
              {canExpense && (
                <button
                  type="button"
                  onClick={() => setShowExpenseForm((open) => !open)}
                  className="ml-auto inline-flex items-center gap-1 border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                >
                  <Plus size={12} />{" "}
                  {showExpenseForm ? "Close" : "Record spend"}
                </button>
              )}
            </div>
            {showExpenseForm && canExpense && (
              <form
                onSubmit={submitExpense}
                className="mb-3 space-y-3 border border-slate-200 bg-slate-50 p-3"
              >
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Field label="Region">
                    <select
                      value={expenseRegion}
                      onChange={(e) => setExpenseRegion(e.target.value)}
                      disabled={expenseSaving}
                      className={inputClass}
                    >
                      {regions.map((region) => (
                        <option
                          key={region.id}
                          value={region.code || region.id}
                        >
                          {region.name}
                          {region.code ? ` (${region.code})` : ""}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    label="Hazard (optional)"
                    hint="Leave blank for pre-hazard preparedness spend."
                  >
                    <select
                      value={expenseHazard}
                      onChange={(e) => setExpenseHazard(e.target.value)}
                      disabled={expenseSaving}
                      className={inputClass}
                    >
                      <option value="">No specific hazard</option>
                      {hazards.map((hazard) => (
                        <option key={hazard.id} value={hazard.id}>
                          {hazard.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Field label="Spend type">
                    <select
                      value={expenseKind}
                      onChange={(e) =>
                        setExpenseKind(e.target.value as ExpenseKind)
                      }
                      disabled={expenseSaving}
                      className={inputClass}
                    >
                      <option value="preparedness">Preparedness</option>
                      <option value="recovery">Recovery</option>
                    </select>
                  </Field>
                  <Field
                    label="Category"
                    hint="e.g. fuel, shelter material, transport."
                  >
                    <input
                      value={expenseCategory}
                      onChange={(e) => setExpenseCategory(e.target.value)}
                      disabled={expenseSaving}
                      className={inputClass}
                    />
                  </Field>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <Field label="Amount (Rs.)">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={expenseAmount}
                      onChange={(e) => setExpenseAmount(e.target.value)}
                      disabled={expenseSaving}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Receipt ref" hint="Optional.">
                    <input
                      value={expenseReceipt}
                      onChange={(e) => setExpenseReceipt(e.target.value)}
                      disabled={expenseSaving}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Vendor" hint="Optional.">
                    <input
                      value={expenseVendor}
                      onChange={(e) => setExpenseVendor(e.target.value)}
                      disabled={expenseSaving}
                      className={inputClass}
                    />
                  </Field>
                </div>
                {expenseError && (
                  <p role="alert" className="text-xs text-red-700">
                    {expenseError}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={expenseSaving}
                  className={primaryButtonClass}
                >
                  {expenseSaving ? "Saving…" : "Save expense record"}
                </button>
              </form>
            )}
            {pipelineLoading ? (
              <p
                role="status"
                className="flex items-center gap-2 border border-slate-200 px-3 py-4 text-xs text-slate-600"
              >
                <LoaderCircle size={14} className="animate-spin" /> Loading
                expense records…
              </p>
            ) : pipelineError ? (
              <p
                role="alert"
                className="border border-amber-300 bg-amber-50 px-3 py-3 text-xs text-amber-900"
              >
                {pipelineError}
              </p>
            ) : expenseItems.length === 0 ? (
              <p className="border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-600">
                No expense records yet.
              </p>
            ) : (
              <div>
                <p className="mb-1 text-[11px] text-slate-500">
                  Total in scope: {formatFigureValue(expenseTotal, "INR")}
                </p>
                <ul className="max-h-96 divide-y divide-slate-200 overflow-y-auto border border-slate-200">
                  {expenseItems.map((item) => (
                    <li key={item.id} className="px-3 py-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                            item.kind === "preparedness"
                              ? "border-blue-800 bg-blue-50 text-blue-900"
                              : "border-amber-600 bg-amber-50 text-amber-900"
                          }`}
                        >
                          {item.kind}
                        </span>
                        <strong className="text-slate-900">
                          {item.category}
                        </strong>
                        <span className="ml-auto font-semibold text-slate-900">
                          {formatFigureValue(item.amountInr, "INR")}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[10px] text-slate-500">
                        {item.regionKey}
                        {item.hazardId ? ` · ${item.hazardId}` : ""} ·{" "}
                        {item.createdByName} · {formatDateTime(item.createdAt)}
                        {item.receiptRef
                          ? ` · receipt ${item.receiptRef}`
                          : " · no receipt ref"}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </section>

      <section
        className="border border-slate-300 bg-white shadow-sm"
        aria-label="Learning from verified corrections"
      >
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#18365b]">
            <FlaskConical size={15} /> Learning from verified corrections
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Recurring differences between AI estimates and approved government
            figures (engine {analysisEngine || "—"}). Only verified corrections
            influence future estimates; unverified edits never become ground
            truth.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
          <div>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-600">
              Recurring differences (
              {displayCount({
                loading: learningLoading,
                error: learningError,
                count: analysis.length,
              })}
              )
            </h4>
            {learningLoading ? (
              <p
                role="status"
                className="flex items-center gap-2 border border-slate-200 px-3 py-4 text-xs text-slate-600"
              >
                <LoaderCircle size={14} className="animate-spin" /> Loading
                learning data…
              </p>
            ) : learningError ? (
              <p
                role="alert"
                className="border border-amber-300 bg-amber-50 px-3 py-3 text-xs text-amber-900"
              >
                {learningError}
              </p>
            ) : analysis.length === 0 ? (
              <p className="border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-600">
                No verified corrections yet. Approve assessments with
                corrections to build learning signal.
              </p>
            ) : (
              <ul className="divide-y divide-slate-200 border border-slate-200">
                {analysis.map((row) => (
                  <li
                    key={`${row.hazardId}-${row.path}`}
                    className="px-3 py-2.5 text-xs"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="text-slate-900">{row.label}</strong>
                      <span className="text-[10px] text-slate-500">
                        {row.hazardId} · {row.count} verified
                      </span>
                      <span
                        className={`ml-auto border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                          row.direction === "aligned"
                            ? "border-emerald-700 bg-emerald-50 text-emerald-800"
                            : "border-amber-600 bg-amber-50 text-amber-900"
                        }`}
                      >
                        {row.direction} · median{" "}
                        {formatSignedPct(row.medianDeltaPct)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-500">
                      Mean {formatSignedPct(row.meanDeltaPct)} · last{" "}
                      {formatDateTime(row.lastAt)} · assessments{" "}
                      {row.assessmentIds.join(", ") || "—"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-600">
              Structured feedback (
              {displayCount({
                loading: learningLoading,
                error: learningError,
                count: feedback.length,
              })}
              )
            </h4>
            {learningLoading ? (
              <p
                role="status"
                className="flex items-center gap-2 border border-slate-200 px-3 py-4 text-xs text-slate-600"
              >
                <LoaderCircle size={14} className="animate-spin" /> Loading
                feedback…
              </p>
            ) : feedback.length === 0 ? (
              <p className="border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-600">
                No corrections recorded yet.
              </p>
            ) : (
              <ul className="max-h-96 divide-y divide-slate-200 overflow-y-auto border border-slate-200">
                {feedback.slice(0, 30).map((item) => (
                  <li key={item.id} className="px-3 py-2 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="text-slate-900">{item.label}</strong>
                      <span
                        className={`border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                          item.status === "verified"
                            ? "border-emerald-700 bg-emerald-50 text-emerald-800"
                            : "border-slate-400 bg-slate-100 text-slate-600"
                        }`}
                      >
                        {item.status}
                      </span>
                      <span className="ml-auto font-mono text-[11px] text-slate-600">
                        {item.aiValue ?? "?"} → {item.correctedValue ?? "?"}
                        {item.deltaPct !== null && item.deltaPct !== undefined
                          ? ` (${formatSignedPct(item.deltaPct)})`
                          : ""}
                      </span>
                    </div>
                    <p className="mt-0.5 text-slate-700">{item.reason}</p>
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      {item.assessmentPublicId} · {item.officerName} ·{" "}
                      {formatDateTime(item.at)} · {item.engineVersion}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      <p className="border border-slate-300 bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-600">
        Scope honesty: figures are planning estimates from stored region, task,
        field-report, damage-submission, and expense data plus officer-observed
        inputs —{" "}
        {listLoading
          ? "loading"
          : listError
            ? "unknown (records failed to load)"
            : `${assessments.length} assessment(s) in scope`}
        ; field evidence is{" "}
        {pipelineLoading
          ? "loading"
          : pipelineError
            ? "unknown (records failed to load)"
            : `${damageItems.length} damage submission(s) and ${expenseItems.length} expense record(s) in scope`}
        . Records pending review are not official. No mock approvals,
        eligibility, insurance decisions, or payments exist in this console.
      </p>
    </div>
  );
};
