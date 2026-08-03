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
  createdAt: string;
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
  status: "queued" | "running" | "success" | "failed";
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  errorMessage: string | null;
}

export interface TaskRunPage {
  items: TaskRun[];
  total: number;
}

export interface Dashboard {
  unreadCount: number;
  savedCount: number;
  activeSubscriptions: number;
  failedRuns: number;
  topItems: IntelligenceItem[];
  latestBriefing: Briefing | null;
}

