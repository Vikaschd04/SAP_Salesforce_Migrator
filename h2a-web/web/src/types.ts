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

export type StageStatus = 'pending' | 'active' | 'done' | 'error';
