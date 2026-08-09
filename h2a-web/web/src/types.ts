// Event + domain types mirroring the backend SSE contract (orchestrator emits these).

export type Ev = Record<string, any> & { type: string; ts?: number };

export interface PlanItem {
  target_name: string; layer: string; domain: string;
  decision: 'Convert' | 'Skip'; native_recommendation?: string; rationale?: string;
  sources?: string[];
  comprehension?: { purpose?: string; business_rules?: string[]; migration_risks?: string[]; complexity?: string };
}

export interface Finding { severity?: string; category?: string; message?: string; suggestion?: string; }

export interface Artifact {
  target_name: string; layer: string; is_lwc?: boolean; apex_pattern?: string; status: string;
  findings?: number; findings_detail?: Finding[]; review_flags?: string[];
  mapping_notes?: string; sobject_refs?: string[]; business_rules?: string[];
  sources?: string[]; lwc_parts?: string[]; has_controller?: boolean; reworked?: boolean;
}

export interface Comprehension {
  cls: string; layer: string; purpose?: string;
  business_rules?: string[]; queries?: string[]; side_effects?: string[];
  dependencies?: string[]; migration_risks?: string[]; complexity?: string;
}

export interface Decision { agent: string; action: string; detail?: string; }

export interface LedgerRow { source: string; layer: string; outcome: string; target: string; note?: string; }

/** One business rule, traced from the source class to the code that implements it. */
export type RuleStatus = 'asserted' | 'implemented' | 'at_risk' | 'dropped';
export interface RuleRow {
  id: string; rule: string; source: string; target: string;
  status: RuleStatus; evidence: string;
}
export interface RuleLedger {
  rules: RuleRow[];
  summary: {
    total: number; asserted: number; implemented: number; at_risk: number;
    dropped: number; preserved: number;
    assured_pct: number | null; preserved_pct: number | null;
  };
}

export type StageStatus = 'pending' | 'active' | 'done' | 'error';

/** One recorded behaviour from the customer's JUnit suite, followed to the Apex. */
export type CharMode = 'direct' | 'adapter' | 'manual';
export interface CharRow {
  id: string; label: string; source_class: string; target_method: string;
  target: string | null; mode: CharMode; reason: string;
  expects_exception?: string | null;
  args?: { java: string }[];
  expected?: { java: string } | null;
  bridge?: { setup: string; result_expr: string; note: string } | null;
}
export interface Characterization {
  summary: {
    total: number; direct: number; adapter: number; manual: number;
    bridged: number; runnable: number; replayable_pct: number | null;
  };
  behaviors: CharRow[];
  classes: string[];
}

/** A past run, from the durable store — survives a server restart. */
export interface RunSummary {
  id: string; status: string; provider: string; engine: string;
  started?: number; elapsed: number; error?: string | null;
  input_dir: string; supervised?: boolean; queue_position?: number;
}
