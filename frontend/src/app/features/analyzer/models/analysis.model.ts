export type Category = 'BREAKING' | 'DEPRECATED' | 'NEW_FEATURE' | 'BUGFIX' | 'INTERNAL';
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type Status = 'pending' | 'processing' | 'completed' | 'failed';

export interface AnalyzeRequest {
  package_name: string;
  from_version: string;
  to_version: string;
}

export interface Change {
  id: string;
  category: Category;
  severity: Severity;
  title: string;
  affected_api: string;
  explanation: string;
  migration_action: string | null;
  before_code: string | null;
  after_code: string | null;
  source_version: string;
  reasoning: string;
  doc_reference: string;
}

export interface Analysis {
  id: string;
  package_name: string;
  from_version: string;
  to_version: string;
  status: Status;
  error: string | null;
  summary: string | null;
  total_breaking: number;
  total_deprecated: number;
  total_new_features: number;
  versions_analyzed: number;
  changes: Change[];
  metadata: {
    model: string | null;
    prompt_version: string | null;
    tokens_used: number | null;
    duration_ms: number | null;
  } | null;
}

export interface ProgressEvent {
  step: string;
  message: string;
  progress: number;
}

export type StatusEvent =
  | { type: 'progress'; data: ProgressEvent }
  | { type: 'complete' }
  | { type: 'error'; message: string; step?: string };
