import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Download, FileJson2, FileText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type { IntelligenceKind, TopicPage } from "../types";

const sectionOptions = [
  ["items", "情报"], ["reports", "报告"], ["sources", "来源"], ["tags", "标签"],
  ["topics", "主题"], ["preferences", "偏好"], ["tasks", "任务链路"],
] as const;
type ExportSection = typeof sectionOptions[number][0];

export function DataExport() {
  const [format, setFormat] = useState<"json" | "markdown">("json");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [topicId, setTopicId] = useState("");
  const [topicSearch, setTopicSearch] = useState("");
  const [debouncedTopicSearch, setDebouncedTopicSearch] = useState("");
  const [selectedTopic, setSelectedTopic] = useState<{ id: number; name: string } | null>(null);
  const [kind, setKind] = useState<IntelligenceKind | "">("");
  const [sections, setSections] = useState<Set<ExportSection>>(() => new Set(sectionOptions.map(([value]) => value)));
  const topics = useQuery({
    queryKey: ["topics", "export", debouncedTopicSearch],
    queryFn: () => api.get<TopicPage>(`/api/topics?${new URLSearchParams({ limit: "100", sort: "name", includeEmpty: "true", ...(debouncedTopicSearch ? { q: debouncedTopicSearch } : {}) }).toString()}`),
  });
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedTopicSearch(topicSearch.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [topicSearch]);
  const topicOptions = useMemo(() => {
    const options = topics.data?.items ?? [];
    return selectedTopic && !options.some((topic) => topic.id === selectedTopic.id) ? [selectedTopic, ...options] : options;
  }, [selectedTopic, topics.data?.items]);
  const validation = useMemo(() => {
    if (sections.size === 0) return "至少选择一类数据";
    if (fromDate && toDate && fromDate > toDate) return "开始日期不能晚于结束日期";
    return null;
  }, [fromDate, sections, toDate]);
  const exportData = useMutation({
    mutationFn: async () => {
      const params = new URLSearchParams({ format });
      if (fromDate) params.set("fromDate", fromDate);
      if (toDate) params.set("toDate", toDate);
      if (topicId) params.set("topicId", topicId);
      if (kind) params.set("kind", kind);
      sections.forEach((section) => params.append("include", section));
      return api.download(`/api/export?${params.toString()}`);
    },
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    },
  });

  function toggleSection(section: ExportSection) {
    setSections((current) => {
      const next = new Set(current);
      if (next.has(section)) next.delete(section); else next.add(section);
      return next;
    });
    exportData.reset();
  }

  return <section className="data-export" aria-labelledby="data-export-title">
    <div className="data-export-head">
      <h2 id="data-export-title">数据导出</h2>
      <span>不包含密钥、完整微信消息和内部地址</span>
    </div>
    <div className="export-block">
      <strong>文件格式</strong>
      <div className="export-format" role="group" aria-label="文件格式">
        <button className={format === "json" ? "active" : ""} aria-pressed={format === "json"} onClick={() => setFormat("json")}><FileJson2 size={18} />JSON<span>可迁移</span></button>
        <button className={format === "markdown" ? "active" : ""} aria-pressed={format === "markdown"} onClick={() => setFormat("markdown")}><FileText size={18} />Markdown<span>可阅读</span></button>
      </div>
    </div>
    <div className="export-block">
      <strong>导出范围</strong>
      <div className="export-filters">
        <label>开始日期<input type="date" aria-label="开始日期" value={fromDate} onChange={(event) => setFromDate(event.target.value)} /></label>
        <label>结束日期<input type="date" aria-label="结束日期" value={toDate} onChange={(event) => setToDate(event.target.value)} /></label>
        <label>搜索主题<input type="search" aria-label="搜索导出主题" value={topicSearch} onChange={(event) => setTopicSearch(event.target.value)} placeholder="输入名称或别名" /></label>
        <label>主题<select aria-label="导出主题" value={topicId} onChange={(event) => { const value = event.target.value; setTopicId(value); setSelectedTopic(topics.data?.items.find((topic) => topic.id === Number(value)) ?? null); }}><option value="">全部主题</option>{topicOptions.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label>
        <label>内容类型<select aria-label="导出内容类型" value={kind} onChange={(event) => setKind(event.target.value as IntelligenceKind | "")}><option value="">全部类型</option><option value="news">热点</option><option value="paper">论文</option><option value="job">招聘</option></select></label>
      </div>
      {topics.isError && <p className="form-error" role="alert">主题未能加载，仍可导出全部主题。</p>}
    </div>
    <div className="export-block">
      <div className="export-block-title"><strong>包含数据</strong><button className="text-button" type="button" onClick={() => setSections(new Set(sectionOptions.map(([value]) => value)))}>全选</button></div>
      <div className="export-sections">{sectionOptions.map(([value, label]) => <label key={value} className={sections.has(value) ? "selected" : ""}><input type="checkbox" checked={sections.has(value)} onChange={() => toggleSection(value)} /><Check size={15} />{label}</label>)}</div>
    </div>
    <div className="export-actions">
      <span className={validation || exportData.isError ? "form-error" : "export-status"} role={validation || exportData.isError ? "alert" : "status"}>{validation ?? (exportData.isError ? exportData.error.message : exportData.isSuccess ? "导出文件已生成" : `${sections.size}类数据`)}</span>
      <button className="primary-button" disabled={Boolean(validation) || exportData.isPending} onClick={() => exportData.mutate()}><Download size={18} />{exportData.isPending ? "正在生成" : "生成导出文件"}</button>
    </div>
  </section>;
}
