import {
  type Dispatch,
  type KeyboardEvent,
  type SetStateAction,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ChevronDown, Edit3, Plus, RefreshCw, Trash2 } from "lucide-react";
import { ApiError, QuantityDTO, api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useMeta } from "@/lib/meta";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Draft = {
  id?: string;
  name: string;
  slug?: string;
  dimensionality: string;
  display_unit: string;
  description: string;
  unit_aliases_text: string;
};

type QuantityUsage = {
  template: string;
  profile_name: string;
  categories: string[];
};

type DraftField = "dimensionality" | "display_unit";

type SuggestionMatch = {
  query: string;
  start: number;
  end: number;
};

type SuggestionItem = {
  value: string;
  detail?: string;
};

type SuppressedSuggestion = {
  field: DraftField;
  query: string;
  start: number;
  end: number;
};

const EMPTY_DRAFT: Draft = {
  name: "",
  dimensionality: "1",
  display_unit: "dimensionless",
  description: "",
  unit_aliases_text: "",
};

const OP_KEYS = ["*", "/", "^", "(", ")", "1", "^(1/2)", "^-1"];

const UNIT_PREFIXES = [
  "Q",
  "R",
  "Y",
  "Z",
  "E",
  "P",
  "T",
  "G",
  "M",
  "k",
  "h",
  "da",
  "d",
  "c",
  "m",
  "u",
  "µ",
  "μ",
  "n",
  "p",
  "f",
  "a",
  "z",
  "y",
  "r",
  "q",
  "Ki",
  "Mi",
  "Gi",
  "Ti",
  "Pi",
  "Ei",
  "Zi",
  "Yi",
  "quetta",
  "ronna",
  "yotta",
  "zetta",
  "exa",
  "peta",
  "tera",
  "giga",
  "mega",
  "kilo",
  "hecto",
  "deca",
  "deka",
  "deci",
  "centi",
  "milli",
  "micro",
  "nano",
  "pico",
  "femto",
  "atto",
  "zepto",
  "yocto",
  "ronto",
  "quecto",
  "kibi",
  "mebi",
  "gibi",
  "tebi",
  "pebi",
  "exbi",
  "zebi",
  "yobi",
];

const normalizeQuantity = (quantity: QuantityDTO): QuantityDTO => ({
  ...quantity,
  description: quantity.description ?? "",
  unit_aliases: quantity.unit_aliases ?? {},
});

const createEmptyDraft = (): Draft => ({ ...EMPTY_DRAFT });

export function QuantityLibraryPage() {
  const meta = useMeta();
  const [quantities, setQuantities] = useState<QuantityDTO[]>([]);
  const [path, setPath] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [normalized, setNormalized] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<QuantityDTO | null>(null);
  const [usage, setUsage] = useState<QuantityUsage[]>([]);
  const [defaultOpen, setDefaultOpen] = useState(false);
  const defaultQuantities = quantities.filter((quantity) => quantity.is_default);
  const customQuantities = quantities.filter((quantity) => !quantity.is_default);

  const load = async () => {
    try {
      const response = await api.quantities();
      setQuantities(response.quantities.map(normalizeQuantity));
      setPath(response.path);
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!draft) {
      setNormalized(null);
      return;
    }
    const handle = window.setTimeout(async () => {
      try {
        const result = await api.normalizeDimension(draft.dimensionality);
        setNormalized(result.normalized);
      } catch {
        setNormalized(null);
      }
    }, 150);
    return () => window.clearTimeout(handle);
  }, [draft?.dimensionality]);

  const save = async () => {
    if (!draft) return;
    try {
      const payload = {
        id: draft.id,
        name: draft.name,
        slug: draft.slug,
        dimensionality: draft.dimensionality,
        display_unit: draft.display_unit,
        description: draft.description,
        unit_aliases: parseAliases(draft.unit_aliases_text),
      };
      const result = draft.id
        ? await api.updateQuantity(draft.id, payload)
        : await api.createQuantity(payload);
      setQuantities(result.quantities.map(normalizeQuantity));
      setDraft(null);
      toast.success("Quantity library updated.");
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  const confirmDelete = async (quantity: QuantityDTO) => {
    setDeleteTarget(quantity);
    try {
      const result = await api.quantityUsage(quantity.id);
      setUsage(result.usage);
    } catch {
      setUsage([]);
    }
  };

  const deleteConfirmed = async () => {
    if (!deleteTarget) return;
    try {
      const result = await api.deleteQuantity(deleteTarget.id);
      setQuantities(result.quantities.map(normalizeQuantity));
      setDeleteTarget(null);
      setUsage([]);
      toast.success("Quantity deleted from library and templates.");
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  return (
    <>
      <PageHeader
        title="Quantities"
        description="Define reusable telemetry quantities for OCR calibration."
        actions={
          <>
            <Button variant="outline" onClick={load}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
            <Button onClick={() => setDraft(createEmptyDraft())}>
              <Plus className="h-4 w-4" /> New quantity
            </Button>
          </>
        }
      />

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-6">
        <div className="font-mono text-xs text-muted-foreground">{path}</div>

        <Card className={cn(defaultOpen && "border-primary/30")}>
          <button
            type="button"
            onClick={() => setDefaultOpen((open) => !open)}
            className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-muted/30"
          >
            <div className="flex-1">
              <div className="flex items-center gap-2 text-sm font-semibold">
                Default quantities
                <Badge variant="outline" className="text-[10px]">
                  {defaultQuantities.length}
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground">
                Time, stage velocity, and stage altitude slots. Defaults can be edited but not deleted.
              </div>
            </div>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-muted-foreground transition-transform",
                defaultOpen && "rotate-180",
              )}
            />
          </button>
          {defaultOpen && (
            <div className="border-t border-border/60">
              <div className="space-y-3 p-5">
                <QuantityRows
                  quantities={defaultQuantities}
                  onEdit={(quantity) => setDraft(toDraft(quantity))}
                  onDelete={confirmDelete}
                />
              </div>
              <div className="flex justify-end border-t border-border/40 px-5 py-3">
                <Button variant="ghost" size="sm" onClick={() => setDefaultOpen(false)}>
                  Collapse defaults
                </Button>
              </div>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Custom telemetry quantities</CardTitle>
            <CardDescription>
              Profile-specific fields copied into templates when enabled from calibration.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {customQuantities.length === 0 && (
              <div className="rounded-md border border-dashed border-border/70 p-5 text-center text-sm text-muted-foreground">
                No custom quantities defined.
              </div>
            )}
            <QuantityRows
              quantities={customQuantities}
              onEdit={(quantity) => setDraft(toDraft(quantity))}
              onDelete={confirmDelete}
            />
          </CardContent>
        </Card>
      </div>

      <Dialog open={draft !== null} onOpenChange={(open) => !open && setDraft(null)}>
        <DialogContent className="flex max-h-[calc(100vh-3rem)] max-w-3xl flex-col gap-0 overflow-hidden p-0">
          <DialogHeader className="px-6 pb-4 pt-6">
            <DialogTitle>
              {draft?.id
                ? quantities.find((quantity) => quantity.id === draft.id)?.is_default
                  ? "Edit default quantity"
                  : "Edit quantity"
                : "New quantity"}
            </DialogTitle>
            <DialogDescription>
              Values are normalized into the display unit before CSV and plot output.
            </DialogDescription>
          </DialogHeader>
          {draft && (
            <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-4">
              <QuantityForm
                key={draft.id ?? "new"}
                draft={draft}
                setDraft={setDraft}
                normalized={normalized}
                presets={meta?.dimensions.presets ?? {}}
                presetUnits={meta?.dimensions.preset_units ?? {}}
                bases={meta?.dimensions.bases ?? []}
                knownUnits={meta?.units ?? []}
              />
            </div>
          )}
          <Separator />
          <DialogFooter className="bg-card/95 px-6 py-4 backdrop-blur supports-[backdrop-filter]:bg-card/90">
            <Button variant="ghost" onClick={() => setDraft(null)}>
              Cancel
            </Button>
            <Button onClick={save}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete quantity</DialogTitle>
            <DialogDescription>
              This will remove the quantity from the library and all affected templates.
            </DialogDescription>
          </DialogHeader>
          {deleteTarget && (
            <div className="space-y-3">
              <div className="rounded-md border border-border/70 bg-muted/20 p-3">
                <div className="font-medium">{deleteTarget.name}</div>
                <div className="font-mono text-xs text-muted-foreground">{deleteTarget.id}</div>
              </div>
              <div className="space-y-2">
                <div className="text-sm font-medium">Usage</div>
                {usage.length === 0 ? (
                  <div className="text-sm text-muted-foreground">No template usage found.</div>
                ) : (
                  usage.map((item) => (
                    <div
                      key={item.template}
                      className="rounded-md border border-border/60 p-2 text-sm"
                    >
                      <div className="font-mono text-xs">{item.template}</div>
                      <div className="text-muted-foreground">{item.categories.join(", ")}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={deleteConfirmed}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function QuantityRows({
  quantities,
  onEdit,
  onDelete,
}: {
  quantities: QuantityDTO[];
  onEdit: (quantity: QuantityDTO) => void;
  onDelete: (quantity: QuantityDTO) => void;
}) {
  return (
    <>
      {quantities.map((quantity) => (
        <div
          key={quantity.id}
          role="button"
          tabIndex={0}
          onClick={() => onEdit(quantity)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onEdit(quantity);
            }
          }}
          className="group grid gap-3 rounded-lg border border-border/70 bg-muted/15 p-3 text-left transition-colors hover:border-primary/55 hover:bg-muted/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background md:grid-cols-[1fr_auto]"
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="font-medium">{quantity.name}</div>
              {quantity.is_default && (
                <Badge variant="outline" className="text-[10px]">
                  default
                </Badge>
              )}
              <Badge variant="outline" className="font-mono normal-case tracking-normal">
                {quantity.dimensionality}
              </Badge>
              <Badge variant="secondary" className="font-mono normal-case tracking-normal">
                {quantity.display_unit}
              </Badge>
              <span className="font-mono text-[11px] text-muted-foreground">
                {displayQuantityFieldName(quantity)}
              </span>
            </div>
            {quantity.description && (
              <p className="mt-1 text-sm text-muted-foreground">{quantity.description}</p>
            )}
            {Object.keys(quantity.unit_aliases).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {Object.entries(quantity.unit_aliases).map(([alias, unit]) => (
                  <span
                    key={alias}
                    className="rounded-md border border-border px-2 py-1 font-mono text-[11px] text-muted-foreground"
                  >
                    {alias}={unit}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="hover-reveal-actions">
            <Button
              variant="outline"
              size="sm"
              onClick={(event) => {
                event.stopPropagation();
                onEdit(quantity);
              }}
            >
              <Edit3 className="h-4 w-4" /> Edit
            </Button>
            {!quantity.is_default && (
              <Button
                variant="ghost"
                size="icon"
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(quantity);
                }}
                title="Delete quantity"
              >
                <Trash2 className="h-4 w-4 text-destructive/80" />
              </Button>
            )}
          </div>
        </div>
      ))}
    </>
  );
}

function QuantityForm({
  draft,
  setDraft,
  normalized,
  presets,
  presetUnits,
  bases,
  knownUnits,
}: {
  draft: Draft;
  setDraft: (next: Draft) => void;
  normalized: string | null;
  presets: Record<string, string>;
  presetUnits: Record<string, string>;
  bases: { symbol: string; label: string }[];
  knownUnits: string[];
}) {
  const [activeField, setActiveField] = useState<DraftField | null>(null);
  const [suppressedSuggestion, setSuppressedSuggestion] = useState<SuppressedSuggestion | null>(null);
  const [dimensionalityActiveIndex, setDimensionalityActiveIndex] = useState(0);
  const [displayUnitActiveIndex, setDisplayUnitActiveIndex] = useState(0);
  const [dimensionalityCursor, setDimensionalityCursor] = useState<number>(draft.dimensionality.length);
  const [displayUnitCursor, setDisplayUnitCursor] = useState<number>(draft.display_unit.length);
  const dimensionalitySuggestionsId = useId();
  const displayUnitSuggestionsId = useId();
  const dimensionalityInputRef = useRef<HTMLInputElement>(null);
  const displayUnitInputRef = useRef<HTMLInputElement>(null);
  const pendingSelectionRef = useRef<{ field: DraftField; start: number; end: number } | null>(null);
  const selectionRef = useRef<Record<DraftField, { start: number; end: number }>>({
    dimensionality: {
      start: draft.dimensionality.length,
      end: draft.dimensionality.length,
    },
    display_unit: {
      start: draft.display_unit.length,
      end: draft.display_unit.length,
    },
  });

  const chips = useMemo(() => tokenizeDimension(draft.dimensionality), [draft.dimensionality]);
  const unitChips = useMemo(() => tokenizeUnit(draft.display_unit), [draft.display_unit]);
  const presetEntries = useMemo(() => Object.entries(presets), [presets]);
  const knownUnitLookup = useMemo(() => new Set(knownUnits), [knownUnits]);
  const dimensionalityMatch = useMemo(
    () => getDimensionSuggestionMatch(draft.dimensionality, dimensionalityCursor),
    [draft.dimensionality, dimensionalityCursor],
  );
  const dimensionalitySuggestions = useMemo(
    () => filterDimensionSuggestions(dimensionalityMatch?.query ?? "", bases),
    [bases, dimensionalityMatch?.query],
  );
  const displayUnitMatch = useMemo(
    () => getUnitSuggestionMatch(draft.display_unit, displayUnitCursor),
    [draft.display_unit, displayUnitCursor],
  );
  const unitSuggestions = useMemo(
    () => filterUnitSuggestions(displayUnitMatch?.query ?? "", knownUnits),
    [displayUnitMatch?.query, knownUnits],
  );
  const dimensionalitySuggestionItems = useMemo<SuggestionItem[]>(
    () =>
      dimensionalitySuggestions.map((base) => ({
        value: base.symbol,
        detail: base.label,
      })),
    [dimensionalitySuggestions],
  );
  const displayUnitSuggestionItems = useMemo<SuggestionItem[]>(
    () => unitSuggestions.map((unit) => ({ value: unit })),
    [unitSuggestions],
  );
  const dimensionalitySuggestionsVisible =
    activeField === "dimensionality" &&
    Boolean(dimensionalityMatch?.query) &&
    dimensionalitySuggestionItems.length > 0 &&
    !isSuppressedSuggestion(suppressedSuggestion, "dimensionality", dimensionalityMatch);
  const displayUnitSuggestionsVisible =
    activeField === "display_unit" &&
    Boolean(displayUnitMatch?.query) &&
    displayUnitSuggestionItems.length > 0 &&
    !isSuppressedSuggestion(suppressedSuggestion, "display_unit", displayUnitMatch);
  const patch = (next: Partial<Draft>) => setDraft({ ...draft, ...next });

  useEffect(() => {
    setDimensionalityActiveIndex(0);
  }, [dimensionalityMatch?.query, dimensionalitySuggestionItems.length, dimensionalitySuggestionsVisible]);

  useEffect(() => {
    setDisplayUnitActiveIndex(0);
  }, [displayUnitMatch?.query, displayUnitSuggestionItems.length, displayUnitSuggestionsVisible]);

  useLayoutEffect(() => {
    const pending = pendingSelectionRef.current;
    if (!pending) return;
    const input =
      pending.field === "dimensionality" ? dimensionalityInputRef.current : displayUnitInputRef.current;
    if (!input) return;
    input.focus();
    input.setSelectionRange(pending.start, pending.end);
    if (pending.field === "dimensionality") {
      setDimensionalityCursor(pending.end);
    } else {
      setDisplayUnitCursor(pending.end);
    }
    pendingSelectionRef.current = null;
  }, [draft.dimensionality, draft.display_unit]);

  const updateCursor = (field: DraftField, input: HTMLInputElement) => {
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    selectionRef.current[field] = { start, end };
    if (
      suppressedSuggestion?.field === field &&
      (start < suppressedSuggestion.start || end > suppressedSuggestion.end)
    ) {
      setSuppressedSuggestion(null);
    }
    if (field === "dimensionality") {
      setDimensionalityCursor(end);
    } else {
      setDisplayUnitCursor(end);
    }
  };

  const queueSelection = (field: DraftField, start: number, end = start) => {
    pendingSelectionRef.current = { field, start, end };
    selectionRef.current[field] = { start, end };
  };

  const replaceRange = (
    field: DraftField,
    start: number,
    end: number,
    text: string,
    options: { hideSuggestions?: boolean } = {},
  ) => {
    const current = draft[field];
    const nextValue = `${current.slice(0, start)}${text}${current.slice(end)}`;
    setDraft({ ...draft, [field]: nextValue } as Draft);
    queueSelection(field, start + text.length);
    if (options.hideSuggestions) {
      setActiveField(null);
      setSuppressedSuggestion({ field, query: text, start, end: start + text.length });
    } else {
      setActiveField(field);
      setSuppressedSuggestion(null);
    }
  };

  const insertAtCursor = (field: DraftField, text: string) => {
    const current = draft[field];
    const start = selectionRef.current[field].start ?? current.length;
    const end = selectionRef.current[field].end ?? start;
    replaceRange(field, start, end, text);
  };

  const preserveSelection = (field: DraftField) => (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const input = field === "dimensionality" ? dimensionalityInputRef.current : displayUnitInputRef.current;
    if (!input) return;
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    selectionRef.current[field] = { start, end };
  };

  const applyPreset = (expression: string) => {
    insertAtCursor("dimensionality", expression);
  };

  const applyDimensionSuggestion = (symbol: string) => {
    if (!dimensionalityMatch) return;
    replaceRange("dimensionality", dimensionalityMatch.start, dimensionalityMatch.end, symbol, {
      hideSuggestions: true,
    });
  };

  const applyUnitSuggestion = (unit: string) => {
    if (!displayUnitMatch) return;
    replaceRange("display_unit", displayUnitMatch.start, displayUnitMatch.end, unit, {
      hideSuggestions: true,
    });
  };

  const dismissSuggestions = (field: DraftField, match: SuggestionMatch | null) => {
    setActiveField(null);
    if (match) {
      setSuppressedSuggestion({ field, query: match.query, start: match.start, end: match.end });
    }
  };

  const handleSuggestionKeyDown = (
    event: KeyboardEvent<HTMLInputElement>,
    {
      field,
      visible,
      suggestions,
      activeIndex,
      setActiveIndex,
      onSelect,
      match,
    }: {
      field: DraftField;
      visible: boolean;
      suggestions: SuggestionItem[];
      activeIndex: number;
      setActiveIndex: Dispatch<SetStateAction<number>>;
      onSelect: (value: string) => void;
      match: SuggestionMatch | null;
    },
  ) => {
    if (!visible) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => (current - 1 + suggestions.length) % suggestions.length);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const selected = suggestions[Math.min(activeIndex, suggestions.length - 1)] ?? suggestions[0];
      if (selected) onSelect(selected.value);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      dismissSuggestions(field, match);
    }
  };

  const applySiUnit = async () => {
    try {
      const result = await api.siUnit(draft.dimensionality);
      patch({ dimensionality: result.dimensionality, display_unit: result.unit });
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  return (
    <div className="space-y-4 pb-2">
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Name">
          <Input value={draft.name} onChange={(event) => patch({ name: event.target.value })} />
        </Field>
        <Field label="Display unit">
          <div className="relative">
            <Input
              ref={displayUnitInputRef}
              value={draft.display_unit}
              onChange={(event) => {
                setSuppressedSuggestion(null);
                patch({ display_unit: event.target.value });
                updateCursor("display_unit", event.target);
              }}
              onClick={(event) => updateCursor("display_unit", event.currentTarget)}
              onFocus={(event) => {
                setActiveField("display_unit");
                updateCursor("display_unit", event.currentTarget);
              }}
              onKeyDown={(event) =>
                handleSuggestionKeyDown(event, {
                  field: "display_unit",
                  visible: displayUnitSuggestionsVisible,
                  suggestions: displayUnitSuggestionItems,
                  activeIndex: displayUnitActiveIndex,
                  setActiveIndex: setDisplayUnitActiveIndex,
                  onSelect: applyUnitSuggestion,
                  match: displayUnitMatch,
                })
              }
              onKeyUp={(event) => updateCursor("display_unit", event.currentTarget)}
              onSelect={(event) => updateCursor("display_unit", event.currentTarget)}
              onBlur={() => {
                window.setTimeout(() => {
                  setActiveField((current) => (current === "display_unit" ? null : current));
                }, 0);
              }}
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={displayUnitSuggestionsVisible}
              aria-controls={displayUnitSuggestionsVisible ? displayUnitSuggestionsId : undefined}
              aria-activedescendant={
                displayUnitSuggestionsVisible
                  ? `${displayUnitSuggestionsId}-${displayUnitActiveIndex}`
                  : undefined
              }
              spellCheck={false}
              className="pr-20 font-mono"
            />
            <button
              type="button"
              onClick={applySiUnit}
              title="Insert the typical SI unit for this dimensionality"
              className="absolute right-1 top-1 inline-flex h-8 items-center gap-1 rounded-md border border-border bg-muted/50 px-2 font-mono text-[11px] text-muted-foreground hover:border-primary/60 hover:text-foreground"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              SI
            </button>
            {displayUnitSuggestionsVisible && (
              <SuggestionDropdown
                id={displayUnitSuggestionsId}
                suggestions={displayUnitSuggestionItems}
                activeIndex={displayUnitActiveIndex}
                onActiveIndexChange={setDisplayUnitActiveIndex}
                onSelect={applyUnitSuggestion}
                className="top-[calc(100%+0.5rem)]"
              />
            )}
          </div>
          <div className="mt-2 flex min-h-8 flex-wrap items-center gap-1 rounded-md border border-border/70 bg-background/40 p-2">
            {unitChips.map((chip, index) => (
              <span
                key={`${chip}-${index}`}
                className={
                  isKnownUnitToken(chip, knownUnitLookup)
                    ? "rounded-md border border-primary/60 px-2 py-0.5 font-mono text-xs text-primary"
                    : "font-mono text-xs text-muted-foreground"
                }
              >
                {chip}
              </span>
            ))}
          </div>
        </Field>
      </div>
      <Field label="Dimensionality">
        <div className="relative">
          <Input
            ref={dimensionalityInputRef}
            value={draft.dimensionality}
            onChange={(event) => {
              setSuppressedSuggestion(null);
              patch({ dimensionality: event.target.value });
              updateCursor("dimensionality", event.target);
            }}
            onClick={(event) => updateCursor("dimensionality", event.currentTarget)}
            onFocus={(event) => {
              setActiveField("dimensionality");
              updateCursor("dimensionality", event.currentTarget);
            }}
            onKeyDown={(event) =>
              handleSuggestionKeyDown(event, {
                field: "dimensionality",
                visible: dimensionalitySuggestionsVisible,
                suggestions: dimensionalitySuggestionItems,
                activeIndex: dimensionalityActiveIndex,
                setActiveIndex: setDimensionalityActiveIndex,
                onSelect: applyDimensionSuggestion,
                match: dimensionalityMatch,
              })
            }
            onKeyUp={(event) => updateCursor("dimensionality", event.currentTarget)}
            onSelect={(event) => updateCursor("dimensionality", event.currentTarget)}
            onBlur={() => {
              window.setTimeout(() => {
                setActiveField((current) => (current === "dimensionality" ? null : current));
              }, 0);
            }}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={dimensionalitySuggestionsVisible}
            aria-controls={dimensionalitySuggestionsVisible ? dimensionalitySuggestionsId : undefined}
            aria-activedescendant={
              dimensionalitySuggestionsVisible
                ? `${dimensionalitySuggestionsId}-${dimensionalityActiveIndex}`
                : undefined
            }
            spellCheck={false}
            className="font-mono"
          />
          {dimensionalitySuggestionsVisible && (
            <SuggestionDropdown
              id={dimensionalitySuggestionsId}
              suggestions={dimensionalitySuggestionItems}
              activeIndex={dimensionalityActiveIndex}
              onActiveIndexChange={setDimensionalityActiveIndex}
              onSelect={applyDimensionSuggestion}
              className="top-[calc(100%+0.5rem)]"
            />
          )}
        </div>
        <div className="mt-2 flex min-h-8 flex-wrap items-center gap-1 rounded-md border border-border/70 bg-background/40 p-2">
          {chips.map((chip, index) => (
            <span
              key={`${chip}-${index}`}
              className={
                bases.some((base) => base.symbol === chip)
                  ? "rounded-md border border-primary/60 px-2 py-0.5 font-mono text-xs text-primary"
                  : "font-mono text-xs text-muted-foreground"
              }
            >
              {chip}
            </span>
          ))}
        </div>
        <div className="mt-2 text-xs text-muted-foreground">
          Normalized: <span className="font-mono text-foreground">{normalized ?? "invalid"}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {bases.map((base) => (
            <button
              type="button"
              key={base.symbol}
              onMouseDown={preserveSelection("dimensionality")}
              onClick={() => insertAtCursor("dimensionality", base.symbol)}
              title={base.label}
              className="rounded-md border border-border px-2 py-1 font-mono text-xs hover:border-primary/60"
            >
              {base.symbol}
            </button>
          ))}
          {OP_KEYS.map((key) => (
            <button
              type="button"
              key={key}
              onMouseDown={preserveSelection("dimensionality")}
              onClick={() => insertAtCursor("dimensionality", key)}
              className="rounded-md border border-border px-2 py-1 font-mono text-xs hover:border-primary/60"
            >
              {key}
            </button>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {presetEntries.map(([name, expression]) => (
            <button
              type="button"
              key={name}
              onMouseDown={preserveSelection("dimensionality")}
              onClick={() => applyPreset(expression)}
              className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/60 hover:text-foreground"
            >
              {name}
              {presetUnits[name] && (
                <span className="ml-1 font-mono text-primary/80">{presetUnits[name]}</span>
              )}
            </button>
          ))}
        </div>
      </Field>
      <Field label="Description">
        <Input
          value={draft.description}
          onChange={(event) => patch({ description: event.target.value })}
        />
      </Field>
      <Field
        label="Unit aliases"
        hint="One ALIAS=unit expression per line. Used for OCR variants that Pint does not parse."
      >
        <Textarea
          value={draft.unit_aliases_text}
          onChange={(event) => patch({ unit_aliases_text: event.target.value })}
          className="min-h-24 font-mono text-xs"
          spellCheck={false}
        />
      </Field>
    </div>
  );
}

function SuggestionDropdown({
  id,
  suggestions,
  activeIndex,
  onActiveIndexChange,
  onSelect,
  className,
}: {
  id: string;
  suggestions: SuggestionItem[];
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
  onSelect: (value: string) => void;
  className?: string;
}) {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, suggestions.length]);

  return (
    <div
      className={`absolute left-0 right-0 z-30 max-h-56 overflow-y-auto rounded-lg border border-border/70 bg-popover shadow-lg ${className ?? ""}`}
    >
      <ul id={id} ref={listRef} role="listbox" className="divide-y divide-border/60">
        {suggestions.map((suggestion, index) => {
          const active = index === activeIndex;
          return (
            <li key={suggestion.value}>
              <button
                id={`${id}-${index}`}
                type="button"
                role="option"
                aria-selected={active}
                tabIndex={-1}
                data-index={index}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => onActiveIndexChange(index)}
                onClick={() => onSelect(suggestion.value)}
                className={cn(
                  "flex w-full items-start justify-between gap-3 px-3 py-2 text-left",
                  active ? "bg-accent/20 text-foreground" : "hover:bg-accent/15",
                )}
              >
                <span className="font-mono text-sm text-foreground">{suggestion.value}</span>
                {suggestion.detail && (
                  <span className="text-xs text-muted-foreground">{suggestion.detail}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function toDraft(quantity: QuantityDTO): Draft {
  return {
    id: quantity.id,
    name: quantity.name,
    slug: quantity.slug,
    dimensionality: quantity.dimensionality,
    display_unit: quantity.display_unit,
    description: quantity.description,
    unit_aliases_text: Object.entries(quantity.unit_aliases ?? {})
      .map(([alias, unit]) => `${alias}=${unit}`)
      .join("\n"),
  };
}

function displayQuantityFieldName(quantity: QuantityDTO): string {
  const fieldName = quantity.field_name ?? `custom_${quantity.slug}`;
  return fieldName === "met" ? "time" : fieldName;
}

function parseAliases(text: string): Record<string, string> {
  const aliases: Record<string, string> = {};
  text
    .split(/\n|,/)
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const [alias, ...rest] = line.split("=");
      const unit = rest.join("=").trim();
      if (alias.trim() && unit) aliases[alias.trim()] = unit;
    });
  return aliases;
}

function tokenizeDimension(value: string): string[] {
  return value.match(/[A-Za-z]+|\d+\/\d+|\d+(?:\.\d+)?|[*/^()]/g) ?? [];
}

function tokenizeUnit(value: string): string[] {
  return value.match(/[A-Za-z_%µμ]+(?:_[A-Za-z_%µμ]+)*|\d+\/\d+|\d+(?:\.\d+)?|[*/^()]/g) ?? [];
}

function filterDimensionSuggestions(
  query: string,
  bases: { symbol: string; label: string }[],
): { symbol: string; label: string }[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  const scored = bases
    .map((base) => ({
      base,
      rank: rankDimensionSuggestion(normalized, base),
    }))
    .filter(
      (
        entry,
      ): entry is {
        base: { symbol: string; label: string };
        rank: number;
      } => entry.rank !== null,
    )
    .sort((left, right) => {
      if (left.rank !== right.rank) return left.rank - right.rank;
      return left.base.symbol.localeCompare(right.base.symbol);
    });
  return scored.map((entry) => entry.base).slice(0, 8);
}

function filterUnitSuggestions(query: string, knownUnits: string[]): string[] {
  const cleanQuery = query.trim();
  const normalized = cleanQuery.toLowerCase();
  if (!normalized) return [];
  const exact = knownUnits
    .filter((unit) => unit.toLowerCase() === normalized)
    .sort((left, right) => compareUnitSuggestions(left, right, cleanQuery));
  const prefixed = prefixedUnitSuggestions(cleanQuery, normalized, knownUnits);
  const prefixedExact = prefixed.filter((unit) => unit.toLowerCase() === normalized);
  const prefixedStartsWith = prefixed.filter((unit) => unit.toLowerCase() !== normalized);
  const exactMatches = uniqueUnits([...exact, ...prefixedExact]).sort((left, right) =>
    compareUnitSuggestions(left, right, cleanQuery),
  );
  const startsWith = knownUnits.filter(
    (unit) => unit.toLowerCase().startsWith(normalized) && unit.toLowerCase() !== normalized,
  );
  const contains = knownUnits.filter(
    (unit) =>
      unit.toLowerCase().includes(normalized) && !unit.toLowerCase().startsWith(normalized),
  );
  return uniqueUnits([...exactMatches, ...startsWith, ...prefixedStartsWith, ...contains]).slice(0, 12);
}

function getDimensionSuggestionMatch(value: string, cursor: number): SuggestionMatch | null {
  const range = findTokenRange(value, cursor, isDimensionCharacter);
  if (!range) return null;
  const previous = previousNonSpaceCharacter(value, range.start);
  if (previous !== "*" && previous !== "/") return null;
  return range;
}

function getUnitSuggestionMatch(value: string, cursor: number): SuggestionMatch | null {
  return findTokenRange(value, cursor, isUnitSuggestionCharacter);
}

function findTokenRange(
  value: string,
  cursor: number,
  isCharacter: (char: string) => boolean,
): SuggestionMatch | null {
  let start = Math.max(0, Math.min(cursor, value.length));
  let end = start;
  while (start > 0 && isCharacter(value[start - 1] ?? "")) {
    start -= 1;
  }
  while (end < value.length && isCharacter(value[end] ?? "")) {
    end += 1;
  }
  if (start === end) return null;
  return {
    query: value.slice(start, end),
    start,
    end,
  };
}

function previousNonSpaceCharacter(value: string, end: number): string | null {
  for (let index = end - 1; index >= 0; index -= 1) {
    if (!/\s/.test(value[index] ?? "")) return value[index] ?? null;
  }
  return null;
}

function rankDimensionSuggestion(
  query: string,
  base: { symbol: string; label: string },
): number | null {
  const symbol = base.symbol.toLowerCase();
  const label = base.label.toLowerCase();
  if (symbol === query) return 0;
  if (symbol.startsWith(query)) return 1;
  if (label.startsWith(query)) return 2;
  if (symbol.includes(query)) return 3;
  return null;
}

function isDimensionCharacter(value: string): boolean {
  return /[A-Za-z]/.test(value);
}

function isUnitSuggestionCharacter(value: string): boolean {
  return /[A-Za-z_%µμ]/.test(value);
}

function isSuppressedSuggestion(
  suppressed: SuppressedSuggestion | null,
  field: DraftField,
  match: SuggestionMatch | null,
): boolean {
  if (!suppressed || !match) return false;
  return (
    suppressed.field === field &&
    suppressed.query === match.query &&
    suppressed.start === match.start &&
    suppressed.end === match.end
  );
}

function isKnownUnitToken(token: string, knownUnitLookup: Set<string>): boolean {
  return knownUnitLookup.has(token) || isPrefixedUnitToken(token, knownUnitLookup);
}

function isPrefixedUnitToken(token: string, knownUnitLookup: Set<string>): boolean {
  return UNIT_PREFIXES.some((prefix) => {
    if (!token.startsWith(prefix) || token.length === prefix.length) return false;
    return knownUnitLookup.has(token.slice(prefix.length));
  });
}

function prefixedUnitSuggestions(cleanQuery: string, normalizedQuery: string, knownUnits: string[]): string[] {
  const prefixableUnits = knownUnits.filter(isPrefixableUnitIdentifier);
  const suggestions: string[] = [];
  const seen = new Set<string>();
  for (const prefix of UNIT_PREFIXES) {
    const prefixLower = prefix.toLowerCase();
    let baseQuery: string | null = null;
    if (normalizedQuery.startsWith(prefixLower)) {
      baseQuery = normalizedQuery.slice(prefixLower.length);
    } else if (prefixLower.startsWith(normalizedQuery)) {
      baseQuery = "";
    }
    if (baseQuery === null) continue;
    for (const unit of prefixableUnits) {
      if (baseQuery && !unit.toLowerCase().startsWith(baseQuery)) continue;
      const suggestion = `${prefix}${unit}`;
      if (seen.has(suggestion)) continue;
      seen.add(suggestion);
      suggestions.push(suggestion);
      if (suggestions.length >= 36) return sortUnits(suggestions, cleanQuery);
    }
  }
  return sortUnits(suggestions, cleanQuery);
}

function isPrefixableUnitIdentifier(unit: string): boolean {
  return /^[A-Za-z_%µμ]+$/.test(unit);
}

function uniqueUnits(units: string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const unit of units) {
    if (seen.has(unit)) continue;
    seen.add(unit);
    unique.push(unit);
  }
  return unique;
}

function sortUnits(units: string[], query: string): string[] {
  return [...units].sort((left, right) => {
    return compareUnitSuggestions(left, right, query);
  });
}

function compareUnitSuggestions(left: string, right: string, query: string): number {
  const leftRank = unitSuggestionRank(left, query);
  const rightRank = unitSuggestionRank(right, query);
  if (leftRank !== rightRank) return leftRank - rightRank;
  if (left.length !== right.length) return left.length - right.length;
  const leftLower = left.toLowerCase();
  const rightLower = right.toLowerCase();
  if (leftLower !== rightLower) return leftLower.localeCompare(rightLower);
  return left.localeCompare(right);
}

function unitSuggestionRank(candidate: string, query: string): number {
  const normalizedQuery = query.toLowerCase();
  const normalizedCandidate = candidate.toLowerCase();
  if (candidate === query) return 0;
  if (normalizedCandidate === normalizedQuery) return 1;
  if (candidate.startsWith(query)) return 2;
  if (normalizedCandidate.startsWith(normalizedQuery)) return 3;
  return 4;
}
