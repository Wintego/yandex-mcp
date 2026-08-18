"""Markdown formatters for Yandex Direct responses."""

from typing import Dict, List, Optional

# Preview length for long lists such as negative keywords.
_PREVIEW_ITEMS = 15


def _money(value: Optional[int]) -> Optional[str]:
    """Convert a Direct micro-amount into a readable currency string."""
    if value in (None, 0):
        return None
    return f"{value / 1_000_000:.2f}"


def _describe_strategy(strategy: Optional[Dict]) -> Optional[str]:
    """Summarise one side (search or network) of a bidding strategy."""
    if not strategy:
        return None

    name = strategy.get("BiddingStrategyType", "UNKNOWN")
    details = []

    for key, value in strategy.items():
        if key == "BiddingStrategyType" or not isinstance(value, dict):
            continue
        for sub_key, sub_value in value.items():
            if sub_key in ("WeeklySpendLimit", "AverageCpc", "AverageCpa", "BidCeiling"):
                amount = _money(sub_value)
                if amount:
                    details.append(f"{sub_key} {amount}")
            elif sub_key in ("GoalId", "PayForConversion", "ProfitabilityCoefficient"):
                details.append(f"{sub_key} {sub_value}")

    return f"{name}" + (f" ({', '.join(details)})" if details else "")


def _format_negative_keywords(items: List[str]) -> List[str]:
    """Render a negative keyword list, truncating very long ones."""
    if not items:
        return []
    preview = ", ".join(items[:_PREVIEW_ITEMS])
    if len(items) > _PREVIEW_ITEMS:
        preview += f", ... (+{len(items) - _PREVIEW_ITEMS} more)"
    return [f"- **Negative keywords** ({len(items)}): {preview}"]


def format_campaigns_markdown(campaigns: List[Dict]) -> str:
    """Format campaigns list as markdown."""
    if not campaigns:
        return "No campaigns found."

    lines = ["# Campaigns\n"]
    for camp in campaigns:
        lines.append(f"## {camp.get('Name', 'Unnamed')} (ID: {camp.get('Id')})")
        lines.append(f"- **Type**: {camp.get('Type', 'N/A')}")
        lines.append(f"- **State**: {camp.get('State', 'N/A')}")
        lines.append(f"- **Status**: {camp.get('Status', 'N/A')}")

        if camp.get("DailyBudget"):
            budget = camp["DailyBudget"]
            amount = budget.get("Amount", 0) / 1_000_000
            lines.append(f"- **Daily Budget**: {amount:.2f} ({budget.get('Mode', 'N/A')})")

        text_campaign = camp.get("TextCampaign") or camp.get("UnifiedCampaign") or {}
        strategy = text_campaign.get("BiddingStrategy") or {}
        search = _describe_strategy(strategy.get("Search"))
        network = _describe_strategy(strategy.get("Network"))
        if search:
            lines.append(f"- **Strategy (search)**: {search}")
        if network:
            lines.append(f"- **Strategy (network)**: {network}")

        counter_ids = (text_campaign.get("CounterIds") or {}).get("Items") or []
        if counter_ids:
            lines.append(f"- **Metrika counters**: {', '.join(map(str, counter_ids))}")

        goals = text_campaign.get("PriorityGoals", {}).get("Items") or []
        if goals:
            goal_desc = ", ".join(
                f"{g.get('GoalId')}"
                + (f" (value {_money(g.get('Value'))})" if g.get("Value") else "")
                for g in goals
            )
            lines.append(f"- **Priority goals**: {goal_desc}")

        shared_sets = (text_campaign.get("NegativeKeywordSharedSetIds") or {}).get("Items") or []
        if shared_sets:
            lines.append(f"- **Negative keyword sets**: {', '.join(map(str, shared_sets))}")

        lines.extend(_format_negative_keywords((camp.get("NegativeKeywords") or {}).get("Items") or []))

        if camp.get("Statistics"):
            stats = camp["Statistics"]
            lines.append(f"- **Clicks**: {stats.get('Clicks', 0)}")
            lines.append(f"- **Impressions**: {stats.get('Impressions', 0)}")

        lines.append("")

    return "\n".join(lines)


def format_adgroups_markdown(groups: List[Dict]) -> str:
    """Format ad groups list as markdown."""
    if not groups:
        return "No ad groups found."

    lines = ["# Ad Groups\n"]
    for group in groups:
        lines.append(f"## {group.get('Name', 'Unnamed')} (ID: {group.get('Id')})")
        lines.append(f"- **Campaign ID**: {group.get('CampaignId')}")
        lines.append(f"- **Type**: {group.get('Type', 'N/A')}")
        lines.append(f"- **Status**: {group.get('Status', 'N/A')}")

        region_ids = group.get("RegionIds", [])
        if region_ids:
            lines.append(f"- **Regions**: {', '.join(map(str, region_ids))}")

        lines.extend(_format_negative_keywords((group.get("NegativeKeywords") or {}).get("Items") or []))

        if group.get("TrackingParams"):
            lines.append(f"- **Tracking params**: {group['TrackingParams']}")

        lines.append("")

    return "\n".join(lines)


def format_ads_markdown(ads: List[Dict]) -> str:
    """Format ads list as markdown."""
    if not ads:
        return "No ads found."

    lines = ["# Ads\n"]
    for ad in ads:
        ad_id = ad.get("Id")
        lines.append(f"## Ad ID: {ad_id}")
        lines.append(f"- **AdGroup ID**: {ad.get('AdGroupId')}")
        lines.append(f"- **Campaign ID**: {ad.get('CampaignId')}")
        lines.append(f"- **State**: {ad.get('State', 'N/A')}")
        lines.append(f"- **Status**: {ad.get('Status', 'N/A')}")

        if ad.get("Type"):
            lines.append(f"- **Type**: {ad['Type']}")

        if ad.get("TextAd"):
            text_ad = ad["TextAd"]
            lines.append(f"- **Title**: {text_ad.get('Title', 'N/A')}")
            lines.append(f"- **Title2**: {text_ad.get('Title2', 'N/A')}")
            lines.append(f"- **Text**: {text_ad.get('Text', 'N/A')}")
            lines.append(f"- **Href**: {text_ad.get('Href', 'N/A')}")

        if ad.get("ResponsiveAd"):
            responsive = ad["ResponsiveAd"]

            titles = [t.get("Title") for t in responsive.get("Titles", []) if t.get("Title")]
            texts = [t.get("Text") for t in responsive.get("Texts", []) if t.get("Text")]

            lines.append(f"- **Titles** ({len(titles)}/7):")
            for title in titles:
                lines.append(f"  - {title}")
            lines.append(f"- **Texts** ({len(texts)}/3):")
            for text in texts:
                lines.append(f"  - {text}")

            lines.append(f"- **Href**: {responsive.get('Href', 'N/A')}")
            if responsive.get("DisplayUrlPath"):
                lines.append(f"- **Display URL path**: {responsive['DisplayUrlPath']}")

            images = (responsive.get("AdImages") or {}).get("Items") or []
            if images:
                lines.append(f"- **Images**: {len(images)}")
            if responsive.get("SitelinkSetId"):
                lines.append(f"- **Sitelink set**: {responsive['SitelinkSetId']}")
            else:
                lines.append("- **Sitelink set**: none")

            extensions = (responsive.get("AdExtensions") or {}).get("Items") or []
            lines.append(f"- **Callouts**: {len(extensions) or 'none'}")

        if ad.get("StatusClarification"):
            lines.append(f"- **Status detail**: {ad['StatusClarification']}")

        lines.append("")

    return "\n".join(lines)


def format_keywords_markdown(keywords: List[Dict]) -> str:
    """Format keywords list as markdown."""
    if not keywords:
        return "No keywords found."

    lines = ["# Keywords\n"]
    for kw in keywords:
        lines.append(f"## {kw.get('Keyword', 'N/A')} (ID: {kw.get('Id')})")
        lines.append(f"- **AdGroup ID**: {kw.get('AdGroupId')}")
        lines.append(f"- **State**: {kw.get('State', 'N/A')}")
        lines.append(f"- **Status**: {kw.get('Status', 'N/A')}")

        bid = _money(kw.get("Bid"))
        if bid:
            lines.append(f"- **Bid**: {bid}")

        context_bid = _money(kw.get("ContextBid"))
        if context_bid:
            lines.append(f"- **Network bid**: {context_bid}")

        settings = kw.get("AutotargetingSettings") or {}
        categories = settings.get("Categories") or {}
        brand_options = settings.get("BrandOptions") or {}

        if categories:
            enabled = [name for name, value in categories.items() if value == "YES"]
            disabled = [name for name, value in categories.items() if value == "NO"]
            lines.append(
                f"- **Autotargeting categories**: on: {', '.join(enabled) or 'none'}"
                + (f" | off: {', '.join(disabled)}" if disabled else "")
            )

        if brand_options:
            enabled = [name for name, value in brand_options.items() if value == "YES"]
            lines.append(f"- **Brand options**: {', '.join(enabled) or 'none'}")

        lines.append("")

    return "\n".join(lines)
