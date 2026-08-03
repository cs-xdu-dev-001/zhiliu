import { Link } from "wouter";

import type { Briefing } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

export function BriefingCard({
  briefing,
  detailHref = `/reports/${briefing.id}`,
}: {
  briefing: Briefing;
  detailHref?: string;
}) {
  const summary = briefing.content.replace(/\s+/g, " ").trim() || "暂无摘要";

  return (
    <article className="briefing-card">
      <Link className="briefing-card-link" href={detailHref}>
        <div className="briefing-meta">
          <span className={`kind-tag ${briefing.kind}`}>{kindLabels[briefing.kind]}</span>
          <time dateTime={briefing.createdAt}>{new Date(briefing.createdAt).toLocaleDateString("zh-CN")}</time>
          <span>引用{briefing.itemCount}条情报</span>
        </div>
        <h2>{briefing.title}</h2>
        <p className="briefing-summary">{summary}</p>
        <span className="card-detail-cue">查看报告</span>
      </Link>
    </article>
  );
}
