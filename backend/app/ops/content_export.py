import argparse
import json
from pathlib import Path


def validate_export(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("导出文件不存在或为空")
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("data"), dict):
        raise ValueError("不支持的知流导出结构")
    data = payload["data"]
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("导出文件缺少计数信息")
    if set(counts) != set(data):
        raise ValueError("导出数据与计数项目不一致")
    for name, records in data.items():
        if not isinstance(records, list) or counts.get(name) != len(records):
            raise ValueError(f"{name}的数据结构或计数不一致")

    item_ids = {record.get("id") for record in data.get("items", [])}
    report_ids = {record.get("id") for record in data.get("reports", [])}
    topic_ids = {record.get("id") for record in data.get("topics", [])}
    if "items" in data:
        for relation in data.get("itemTopics", []):
            if relation.get("itemId") not in item_ids:
                raise ValueError("主题关系引用了导出范围外的情报")
    if "reports" in data and any(relation.get("reportId") not in report_ids for relation in data.get("reportSources", [])):
        raise ValueError("报告来源引用了不存在的报告")
    if "topics" in data and any(relation.get("topicId") not in topic_ids for relation in data.get("itemTopics", [])):
        raise ValueError("情报主题关系引用了不存在的主题")
    return {"status": "ok", "schemaVersion": 1, "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description="验证知流JSON内容导出的结构与引用")
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(validate_export(arguments.path), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
