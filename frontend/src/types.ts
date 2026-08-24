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
  topics?: TopicReference[];
  reason: string;
  importance: number;
  personalizedScore?: number | null;
  recommendationReasons?: RecommendationReason[];
  isRead: boolean;
  isSaved: boolean;
  isIgnored: boolean;
  isInvalid: boolean;
  isStale?: boolean;
  sourceUnavailable?: boolean;
  latestChangeType?: ChangeType | null;
  mergedIntoId: number | null;
  tags: string[];
  createdAt: string;
}

export interface ItemRevision {
  id: number;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  createdAt: string;
}

export interface RecommendationReason { code: string; text: string; delta: number; preferenceId?: number | null; }

export type ChangeType = "first_appearance" | "ongoing" | "important_update" | "duplicate_message" | "viewpoint_changed" | "information_invalid";

export interface ItemChange {
  id: number;
  itemId: number;
  relatedItemId: number | null;
  relatedItemTitle: string | null;
  taskRunId: number | null;
  publicationId: number | null;
  changeType: ChangeType;
  basis: string;
  sourceUrls: string[];
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  status: "pending" | "confirmed" | "corrected" | "unlinked";
  detectedAt: string;
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
  changes: ItemChange[];
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
  seriesId?: string | null;
  versionNumber?: number;
  previousVersionId?: number | null;
  generationTaskId?: number | null;
  citationStatus?: "unchecked" | "valid" | "warning";
  citationWarnings?: string[];
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
  sourceUnavailable?: boolean;
  isCited: boolean;
  evidenceStatus: "traceable" | "unreferenced" | "source-unavailable" | "invalid" | "unsafe-link";
  evidenceMessage: string;
}

export type BulkItemAction = "read" | "unread" | "save" | "unsave" | "ignore" | "unignore" | "invalidate" | "restore" | "tag" | "untag";

export interface ItemBulkResult {
  operationId: number;
  requested: number;
  updated: number;
  updatedIds: number[];
  skipped: Array<{ id: number; reason: string }>;
  duplicate: boolean;
}

export interface SavedView {
  id: number;
  name: string;
  query: string;
  createdAt: string;
  updatedAt: string;
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
  versions?: BriefingVersionSummary[];
  versionDiff?: BriefingVersionDiff | null;
}

export interface BriefingVersionSummary {
  id: number;
  title: string;
  versionNumber: number;
  itemCount: number;
  citationStatus: "unchecked" | "valid" | "warning";
  createdAt: string;
}

export interface BriefingVersionDiff {
  previousVersionId: number;
  previousVersionNumber: number;
  titleChanged: boolean;
  instructionChanged: boolean;
  previousInstruction: string;
  currentInstruction: string;
  addedSourceIds: number[];
  removedSourceIds: number[];
  addedSources: Array<{ id: number; title: string }>;
  removedSources: Array<{ id: number; title: string }>;
  addedSegmentCount: number;
  removedSegmentCount: number;
  changes: Array<{ kind: "added" | "removed"; text: string }>;
  condensed: boolean;
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
  retryOfId: number | null;
  hermesRunId: string | null;
  traceId: string | null;
  origin: "weixin-hermes" | "subscription-hermes" | "web-report";
  topic: string | null;
  requestSummary: string | null;
  status: "queued" | "running" | "success" | "failed" | "cancelled";
  stage: "accepted" | "processing" | "understanding" | "searching" | "organizing" | "publishing" | "completed" | "failed" | "cancelled" | "lost";
  resultSummary: string | null;
  startedAt: string;
  heartbeatAt: string | null;
  finishedAt: string | null;
  cancelledAt: string | null;
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
  staleCount: number;
  lowImportanceCount: number;
  sourceUnavailableCount: number;
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

export interface SystemDiagnostics {
  status: "ok" | "degraded" | "unavailable";
  generatedAt: string;
  database: {
    status: "ok" | "unavailable";
    latencyMs: number | null;
    migrationVersion: string | null;
  };
  scheduler: {
    enabled: boolean;
    running: boolean;
    jobCount: number;
    lastQueuePollAt: string | null;
    lastQueuePollFailed: boolean;
    lastSweepAt: string | null;
    lastSweepLostCount: number;
  };
  queue: {
    queued: number;
    running: number;
    oldestActiveSeconds: number | null;
    lastSuccessAt: string | null;
    lastFailureAt: string | null;
  };
  hermes: {
    configured: boolean;
    status: string;
    checkedAt: string | null;
  };
  mcp: {
    status: "verified" | "unverified" | "failed" | "unknown";
    lastWriteAt: string | null;
    lastTaskStatus: string | null;
    lastTaskAt: string | null;
  };
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

export interface TopicReference {
  id: number;
  name: string;
}

export interface TopicSummary extends TopicReference {
  description: string;
  isFollowed: boolean;
  isPinned: boolean;
  isMuted: boolean;
  itemCount7Days: number;
  itemCount30Days: number;
  previous7DaysCount: number;
  trend: "rising" | "steady" | "falling";
  sourceCount: number;
  latestAt: string | null;
}

export interface TopicPage {
  items: TopicSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface TopicDetail extends TopicSummary {
  aliases: string[];
  latestItems: IntelligenceItem[];
  relatedBriefings: Briefing[];
  relatedRuns: TaskRun[];
  recentChanges: ItemChange[];
  changeSummary: string;
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

export interface PersonalizationSettings { autoLearningEnabled: boolean; algorithmVersion: number; updatedAt: string; }
export interface PersonalizationRecalculate { updatedItems: number; algorithmVersion: number; }

export interface DailyAttention {
  date: string;
  settings: { minImportance: number; importantOnly: boolean };
  items: Array<{ item: IntelligenceItem; reasons: string[] }>;
  risingTopics: Array<{ id: number; name: string; currentCount: number; previousCount: number }>;
  importantChangeCount: number;
  sourceUnavailableCount: number;
  pendingChangeCount: number;
  consecutiveFailureCount: number;
  actionableCount: number;
  idempotencyKey: string;
  latestBriefing: Briefing | null;
  activeTask: TaskRun | null;
}

export interface DailyAttentionGenerate {
  created: boolean;
  message: string;
  task: TaskRun | null;
}

export type FeedbackType = "useful" | "irrelevant" | "duplicate" | "summary_wrong" | "source_unreliable" | "follow_up";
export type FeedbackImpactScope = "current" | "topic" | "long_term";

export interface ContentFeedback {
  id: number;
  itemId: number | null;
  briefingId: number | null;
  topicId: number | null;
  preferenceId: number | null;
  feedbackType: FeedbackType;
  impactScope: FeedbackImpactScope;
  note: string;
  active: boolean;
  version: number;
  createdAt: string;
  updatedAt: string;
  revokedAt: string | null;
}

export interface FeedbackPage { items: ContentFeedback[]; }

