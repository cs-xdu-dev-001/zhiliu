export type IntelligenceKind = "news" | "paper" | "job";
export type HermesConnectionStatus = "connected" | "unreachable" | "unauthorized" | "unconfigured" | "error";
export interface HermesConnection {
  baseUrl: string;
  apiKeyConfigured: boolean;
  apiKeyHint: string | null;
  status: HermesConnectionStatus;
  message: string;
  checkedAt: string | null;
  version: string | null;
}

export interface IntelligenceItem {
  id: number;
  subscriptionId: number;
  kind: IntelligenceKind;
  title: string;
  summary: string;
  url: string;
  source: string;
  publishedAt: string | null;
  keywords: string[];
  reason: string;
  importance: number;
  isRead: boolean;
  isSaved: boolean;
  isIgnored: boolean;
  isInvalid: boolean;
  mergedIntoId: number | null;
  createdAt: string;
}

export interface ItemRevision {
  id: number;
  action: "edited" | "invalidated" | "restored" | "merged" | "merge_target";
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  createdAt: string;
}

export interface MergedItem {
  id: number;
  title: string;
}

export interface MergeCandidate {
  id: number;
  title: string;
  summary: string;
  source: string;
  url: string;
  similarity: number;
}

export interface PublicationRecord {
  id: number;
  traceId: string | null;
  origin: string;
  requestSummary: string;
  createdAt: string;
  hermesRunId: string | null;
  taskRunId: number | null;
  wasInserted: boolean;
  ordinal: number;
  briefingId: number | null;
  briefingTitle: string | null;
}

export interface IntelligenceItemDetail extends IntelligenceItem {
  publications: PublicationRecord[];
  traceAvailable: boolean;
  revisions: ItemRevision[];
  mergedInto: MergedItem | null;
}

export interface ItemPage {
  items: IntelligenceItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface Briefing {
  id: number;
  subscriptionId: number;
  title: string;
  kind: IntelligenceKind;
  content: string;
  itemCount: number;
  periodStart: string | null;
  periodEnd: string | null;
  createdAt: string;
}

export interface SourceItem {
  id: number;
  title: string;
  summary: string;
  source: string;
  url: string;
  ordinal: number;
  wasInserted: boolean;
  isInvalid: boolean;
}

export type BulkItemAction = "read" | "unread" | "save" | "unsave" | "ignore" | "unignore" | "invalidate" | "restore";

export interface ItemBulkResult {
  requested: number;
  updated: number;
  skipped: Array<{ id: number; reason: string }>;
}

export interface PublicationSummary {
  id: number;
  traceId: string | null;
  origin: string;
  requestSummary: string;
  createdAt: string;
  hermesRunId: string | null;
  taskRunId: number | null;
}

export interface BriefingDetail extends Briefing {
  sourceItems: SourceItem[];
  publication: PublicationSummary | null;
  traceAvailable: boolean;
}

export interface PublicationTrace {
  publicationId: number;
  traceId: string | null;
  origin: string;
  requestSummary: string;
  hermesRunId: string | null;
  createdAt: string;
  itemCount: number;
  skippedCount: number;
  subscription: { id: number; name: string };
  taskRun: Pick<TaskRun, "id" | "status" | "startedAt" | "finishedAt"> | null;
  items: SourceItem[];
  briefing: Pick<Briefing, "id" | "title" | "kind"> | null;
}

export interface BriefingPage {
  items: Briefing[];
  total: number;
  limit: number;
  offset: number;
}

export interface Subscription {
  id: number;
  name: string;
  kind: IntelligenceKind;
  keywords: string[];
  schedule: string;
  prompt: string;
  enabled: boolean;
  lastRunAt: string | null;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export type SubscriptionInput = Omit<Subscription, "id" | "lastRunAt" | "nextRunAt" | "createdAt" | "updatedAt">;

export interface TaskRun {
  id: number;
  subscriptionId: number;
  hermesRunId: string | null;
  traceId: string | null;
  origin: "weixin-hermes" | "subscription-hermes";
  topic: string | null;
  requestSummary: string | null;
  status: "queued" | "running" | "success" | "failed";
  stage: "accepted" | "processing" | "publishing" | "completed" | "failed";
  resultSummary: string | null;
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  errorMessage: string | null;
  subscriptionName: string | null;
  publicationId: number | null;
  briefingId: number | null;
  retryCount: number;
}

export interface TaskRunPage {
  items: TaskRun[];
  total: number;
  limit: number;
  offset: number;
}

export type QualityAction = "accepted" | "inserted" | "duplicate" | "filtered";
export type QualityFilter = "filtered" | "duplicate" | "restored";
export interface QualityDecision {
  id: number;
  publicationId: number;
  itemId: number | null;
  action: QualityAction;
  reasonCode: string;
  reason: string;
  kind: IntelligenceKind;
  title: string;
  summary: string;
  source: string;
  url: string;
  importance: number;
  restoredAt: string | null;
  createdAt: string;
  traceId: string | null;
  briefingId: number | null;
}

export interface QualityPage {
  items: QualityDecision[];
  total: number;
  filteredCount: number;
  duplicateCount: number;
  restoredCount: number;
}

export interface SubscriptionHealth {
  subscriptionId: number;
  name: string;
  kind: IntelligenceKind;
  enabled: boolean;
  nextRunAt: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  runCount: number;
  successCount: number;
  failedCount: number;
  successRate: number | null;
  consecutiveFailures: number;
  averageDurationMs: number | null;
  producedItemCount: number;
}

export interface SubscriptionHealthPage {
  items: SubscriptionHealth[];
  generatedAt: string;
}

export interface Dashboard {
  unreadCount: number;
  savedCount: number;
  activeSubscriptions: number;
  failedRuns: number;
  topItems: IntelligenceItem[];
  latestBriefing: Briefing | null;
  recentRuns: TaskRun[];
}

export interface SearchItemResult {
  id: number;
  kind: IntelligenceKind;
  title: string;
  summary: string;
  source: string;
  url: string;
  createdAt: string;
}

export interface SearchBriefingResult {
  id: number;
  kind: IntelligenceKind;
  title: string;
  summary: string;
  itemCount: number;
  createdAt: string;
}

export interface SearchResponse {
  query: string;
  items: SearchItemResult[];
  briefings: SearchBriefingResult[];
  itemTotal: number;
  briefingTotal: number;
}

export type PreferenceScope = "source" | "topic" | "output";
export type PreferenceEffect = "prefer" | "avoid" | "instruct";
export type PreferenceKind = "all" | IntelligenceKind;

export interface HermesPreference {
  id: number;
  scope: PreferenceScope;
  effect: PreferenceEffect;
  value: string;
  kind: PreferenceKind;
  note: string;
  active: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PreferencePage {
  items: HermesPreference[];
}

