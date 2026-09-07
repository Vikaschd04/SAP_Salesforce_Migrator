import { createContext, useContext } from 'react';

/**
 * What this run's screens should call things. [1.61]
 *
 * The cockpit named Salesforce everywhere — "On Salesforce:" above a hazard, "Generated
 * Salesforce Apex" above a diff, "Salesforce objects" beside a reference list — in a run
 * emitting Java for SAP Hybris. Not a wording bug: `RunState.pipeline` existed from the
 * start and the engine never filled it, so no screen *could* know which migration it was
 * showing. The reports were fixed for exactly this in 1.39; this is the same fix, four
 * years of screens later.
 *
 * A context rather than props because the readers are leaves — Radar sits inside
 * Discovery inside Gate inside App — and threading a prop through three components that
 * do not otherwise care is how it stops being threaded.
 *
 * The default is Salesforce, which is what a run with no pipeline is: the v1 path.
 */
export interface Vocabulary {
  /** `SAP Hybris` — where the code is coming from. */
  source: string;
  /** `Salesforce` — where it is going. */
  target: string;
  /** `Apex`, `Java` — what the generated code is called. */
  language: string;
}

export const DEFAULT_VOCAB: Vocabulary = {
  source: 'SAP Hybris', target: 'Salesforce', language: 'Apex',
};

export const VocabularyContext = createContext<Vocabulary>(DEFAULT_VOCAB);

export function useVocab(): Vocabulary {
  return useContext(VocabularyContext);
}

/** Build one from whatever the engine sent, falling back field by field. */
export function vocabFrom(p: { source?: string; target?: string; language?: string } | null): Vocabulary {
  return {
    source: p?.source || DEFAULT_VOCAB.source,
    target: p?.target || DEFAULT_VOCAB.target,
    language: p?.language || DEFAULT_VOCAB.language,
  };
}
