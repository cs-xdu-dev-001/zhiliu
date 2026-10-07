from dataclasses import dataclass

from app.schemas import IntelligenceKind


@dataclass(frozen=True)
class SubscriptionPreset:
    id: str
    name: str
    kind: IntelligenceKind
    keywords: tuple[str, ...]
    schedule: str
    description: str
    sources: tuple[str, ...]
    prompt: str


SUBSCRIPTION_PRESETS: tuple[SubscriptionPreset, ...] = (
    SubscriptionPreset(
        id="research-radar",
        name="研究前沿雷达",
        kind="paper",
        keywords=("LLM Agent", "科研智能", "RAG", "多模态"),
        schedule="0 8 * * *",
        description="论文、预印本和实验代码",
        sources=("arXiv", "Hugging Face Papers", "OpenReview", "官方研究博客"),
        prompt=(
            "检索过去24小时内与大模型、Agent、科研智能、RAG和多模态相关的重要研究。"
            "优先查看arXiv、Hugging Face Papers、OpenReview以及Google DeepMind、OpenAI、"
            "Anthropic、Meta AI、Microsoft Research、NVIDIA Research等官方研究博客。"
            "只保留有明确方法、实验结果或公开代码的内容；预印本必须明确标注尚未同行评审。"
            "每条输出标题、核心问题、方法、实验结论、局限、代码链接、原始论文链接、"
            "关键词、重要程度和推荐理由。必须使用原始来源链接，重复论文只保留一条。"
        ),
    ),
    SubscriptionPreset(
        id="engineering-radar",
        name="工程进展雷达",
        kind="news",
        keywords=("AI工程", "开源模型", "推理", "Agent框架"),
        schedule="0 */6 * * *",
        description="开源项目、版本发布和工程实践",
        sources=("GitHub Releases", "Hacker News", "InfoQ", "IEEE Spectrum", "官方工程博客"),
        prompt=(
            "检索过去24小时内AI工程、开源模型、推理服务、Agent框架和开发者工具的重要进展。"
            "优先查看GitHub官方Release或仓库公告、Hacker News、InfoQ、IEEE Spectrum以及厂商工程博客。"
            "只保留能核验的版本发布、性能变化、公开代码、部署方式或工程实践；不要把营销口号当作技术结论。"
            "每条输出标题、变化内容、适用场景、性能或限制、代码/文档链接、原始来源、关键词、"
            "重要程度和推荐理由。相同项目的重复报道合并，必须保留最接近一手来源的链接。"
        ),
    ),
    SubscriptionPreset(
        id="people-insights",
        name="大佬分享雷达",
        kind="news",
        keywords=("AI研究者", "技术访谈", "技术演讲", "产业判断"),
        schedule="0 9 * * sat",
        description="访谈、演讲和一手观点",
        sources=("Lex Fridman", "Dwarkesh Podcast", "Latent Space", "Import AI", "官方演讲"),
        prompt=(
            "整理过去7天AI、计算机科学和技术产业中值得长期关注的访谈、演讲、播客或长文分享。"
            "优先查看Lex Fridman、Dwarkesh Podcast、Latent Space、Import AI以及研究机构或公司的官方演讲。"
            "每条输出分享者、主题、核心观点、支持该观点的事实或原话出处、可能影响、局限、"
            "原始视频/文章链接、发布时间、关键词、重要程度和推荐理由。区分事实、分享者观点和你的推断，"
            "不要把二手评论当作分享者原意。相同单集或文章只保留一条。"
        ),
    ),
)

_PRESETS_BY_ID = {preset.id: preset for preset in SUBSCRIPTION_PRESETS}


def get_subscription_preset(preset_id: str) -> SubscriptionPreset | None:
    return _PRESETS_BY_ID.get(preset_id)
