"""Yandex Direct keyword tools."""

import json
from mcp.server.fastmcp import FastMCP

from ...client import api_client
from ...models.common import ResponseFormat
from ...models.direct import (
    GetKeywordsInput,
    AddKeywordsInput,
    SetKeywordBidsInput,
    ManageKeywordInput,
    UpdateAutotargetingInput,
)
from ...formatters.direct import format_keywords_markdown
from ...utils import handle_api_error
from ._helpers import register_manage_tool


def register(mcp: FastMCP) -> None:
    """Register keyword tools."""

    @mcp.tool(
        name="direct_get_keywords",
        annotations={
            "title": "Get Yandex Direct Keywords",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def direct_get_keywords(params: GetKeywordsInput) -> str:
        """Get list of keywords from Yandex Direct.

        Retrieves keywords with their bids and status.
        """
        try:
            selection_criteria = {}

            if params.campaign_ids:
                selection_criteria["CampaignIds"] = params.campaign_ids
            if params.adgroup_ids:
                selection_criteria["AdGroupIds"] = params.adgroup_ids
            if params.keyword_ids:
                selection_criteria["Ids"] = params.keyword_ids

            request_params = {
                "SelectionCriteria": selection_criteria,
                "FieldNames": [
                    "Id", "Keyword", "AdGroupId", "CampaignId",
                    "State", "Status", "Bid", "ContextBid", "StrategyPriority",
                ],
                "Page": {
                    "Limit": params.limit,
                    "Offset": params.offset
                }
            }

            if params.include_autotargeting_settings:
                request_params["AutotargetingSettingsCategoriesFieldNames"] = [
                    "Exact", "Narrow", "Alternative", "Accessory", "Broader"
                ]
                request_params["AutotargetingSettingsBrandOptionsFieldNames"] = [
                    "WithoutBrands", "WithAdvertiserBrand", "WithCompetitorsBrand"
                ]

            result = await api_client.direct_request("keywords", "get", request_params)

            if "error" in result:
                err = result["error"]
                return (
                    f"API Error: {err.get('error_code')}: {err.get('error_string')} "
                    f"| {err.get('error_detail', '')}"
                )

            keywords = result.get("result", {}).get("Keywords", [])

            if params.response_format == ResponseFormat.JSON:
                return json.dumps({"keywords": keywords, "total": len(keywords)}, indent=2, ensure_ascii=False)

            return format_keywords_markdown(keywords)

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_add_keywords",
        annotations={
            "title": "Add Yandex Direct Keywords",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def direct_add_keywords(params: AddKeywordsInput) -> str:
        """Add keywords to an ad group.

        Creates new keywords with optional bid settings.
        """
        try:
            keywords = []
            for kw in params.keywords:
                keyword_item = {
                    "Keyword": kw,
                    "AdGroupId": params.adgroup_id
                }
                if params.bid:
                    keyword_item["Bid"] = int(params.bid * 1_000_000)
                keywords.append(keyword_item)

            request_params = {
                "Keywords": keywords
            }

            result = await api_client.direct_request("keywords", "add", request_params)
            add_results = result.get("result", {}).get("AddResults", [])

            success = [r["Id"] for r in add_results if r.get("Id") and not r.get("Errors")]
            errors = []
            for r in add_results:
                if r.get("Errors"):
                    errors.extend([e.get("Message", "Unknown error") for e in r["Errors"]])

            response = f"Successfully added {len(success)} keyword(s)."
            if success:
                response += f"\nIDs: {', '.join(map(str, success))}"
            if errors:
                response += f"\n\nErrors:\n" + "\n".join(f"- {e}" for e in errors)

            return response

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_set_keyword_bids",
        annotations={
            "title": "Set Keyword Bids",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def direct_set_keyword_bids(params: SetKeywordBidsInput) -> str:
        """Set bids for keywords and autotargeting criteria.

        Each item targets one of keyword_id, adgroup_id or campaign_id. Bids are
        given in currency units (220 means 220 RUB); 'bid' is an alias of
        'search_bid'. Note that campaigns on an automatic bidding strategy
        ignore manual bids and the API returns an error for them.
        """
        try:
            keyword_bids = []
            for kb in params.keyword_bids:
                bid_item = {}
                if kb.keyword_id:
                    bid_item["KeywordId"] = kb.keyword_id
                if kb.adgroup_id:
                    bid_item["AdGroupId"] = kb.adgroup_id
                if kb.campaign_id:
                    bid_item["CampaignId"] = kb.campaign_id

                if not bid_item:
                    return (
                        "Each item needs one of keyword_id, adgroup_id or campaign_id."
                    )

                search_bid = kb.search_bid if kb.search_bid is not None else kb.bid
                if search_bid is not None:
                    bid_item["SearchBid"] = int(round(search_bid * 1_000_000))
                if kb.network_bid is not None:
                    bid_item["NetworkBid"] = int(round(kb.network_bid * 1_000_000))
                if kb.autotargeting_search_bid_is_auto is not None:
                    bid_item["AutotargetingSearchBidIsAuto"] = (
                        "YES" if kb.autotargeting_search_bid_is_auto else "NO"
                    )
                if kb.strategy_priority:
                    bid_item["StrategyPriority"] = kb.strategy_priority

                if len(bid_item) == 1:
                    return (
                        "Nothing to set: provide bid, search_bid, network_bid, "
                        "strategy_priority or autotargeting_search_bid_is_auto."
                    )

                keyword_bids.append(bid_item)

            request_params = {
                "KeywordBids": keyword_bids
            }

            result = await api_client.direct_request("keywordbids", "set", request_params)

            if "error" in result:
                err = result["error"]
                return (
                    f"API Error: {err.get('error_code')}: {err.get('error_string')} "
                    f"| {err.get('error_detail', '')}"
                )

            set_results = result.get("result", {}).get("SetResults", [])

            success = [
                r.get("KeywordId")
                for r in set_results
                if r.get("KeywordId") and not r.get("Errors")
            ]
            errors = []
            for r in set_results:
                for err in r.get("Errors", []):
                    errors.append(
                        f"ID {r.get('KeywordId', '?')}: {err.get('Message', 'Unknown error')}"
                        + (f" - {err['Details']}" if err.get("Details") else "")
                    )
                for warn in r.get("Warnings", []):
                    errors.append(
                        f"ID {r.get('KeywordId', '?')}: Warning: "
                        f"{warn.get('Message', 'Unknown warning')}"
                    )

            response = f"Successfully updated bids for {len(success)} keyword(s)."
            if errors:
                response += "\n\nErrors:\n" + "\n".join(f"- {e}" for e in errors)
            return response

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_update_autotargeting",
        annotations={
            "title": "Update Yandex Direct Autotargeting Settings",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def direct_update_autotargeting(params: UpdateAutotargetingInput) -> str:
        """Change which query categories an autotargeting criterion may serve on.

        Autotargeting is a criterion in the Keywords service: every text ad group
        owns one ---autotargeting entry whose ID comes from direct_get_keywords.
        Categories are exact, narrow, alternative, accessory and broader; brand
        options are without_brands, with_advertiser_brand and with_competitors_brand.
        Narrowing to exact only is the usual fix for autotargeting that pulls in
        informational traffic.
        """
        try:
            categories = params.categories_payload()
            brand_options = params.brand_options_payload()

            if not categories and not brand_options:
                return (
                    "Nothing to update: pass at least one category "
                    "(exact, narrow, alternative, accessory, broader) or brand option."
                )

            settings = {}
            if categories:
                settings["Categories"] = categories
            if brand_options:
                settings["BrandOptions"] = brand_options

            keywords = [
                {"Id": keyword_id, "AutotargetingSettings": settings}
                for keyword_id in params.keyword_ids
            ]

            result = await api_client.direct_request(
                "keywords", "update", {"Keywords": keywords}
            )

            if "error" in result:
                err = result["error"]
                return (
                    f"API Error: {err.get('error_code')}: {err.get('error_string')} "
                    f"| {err.get('error_detail', '')}"
                )

            update_results = result.get("result", {}).get("UpdateResults", [])

            success = [r["Id"] for r in update_results if r.get("Id") and not r.get("Errors")]
            errors = []
            for r in update_results:
                for err in r.get("Errors", []):
                    errors.append(
                        f"ID {r.get('Id', '?')}: {err.get('Message', 'Unknown error')}"
                        + (f" - {err['Details']}" if err.get("Details") else "")
                    )

            enabled = ", ".join(f"{k}={v}" for k, v in {**categories, **brand_options}.items())
            response = f"Autotargeting updated for {len(success)} criterion(s): {enabled}"
            if errors:
                response += "\n\nErrors:\n" + "\n".join(f"- {e}" for e in errors)
            return response

        except Exception as e:
            return handle_api_error(e)

    for action in ("suspend", "resume", "delete"):
        register_manage_tool(
            mcp,
            service="keywords",
            action=action,
            entity="keyword",
            input_model=ManageKeywordInput,
            ids_field="keyword_ids",
        )
