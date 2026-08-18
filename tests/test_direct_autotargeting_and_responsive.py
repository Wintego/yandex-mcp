"""Tests for autotargeting settings, keyword bids and combinatorial ads.

These cover the request payloads the tools build and the markdown they render,
without touching the network: the Direct client is replaced by a recorder.
"""

import pytest

from yandex_mcp.formatters.direct import (
    format_ads_markdown,
    format_campaigns_markdown,
    format_keywords_markdown,
)
from yandex_mcp.models.direct import (
    SetKeywordBidsInput,
    UpdateAutotargetingInput,
    UpdateResponsiveAdInput,
)


class RecordingClient:
    """Stand-in for the Direct client that records calls and replays answers."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def direct_request(self, service, method, params, use_v501=False, timeout=None):
        self.calls.append({
            "service": service,
            "method": method,
            "params": params,
            "use_v501": use_v501,
        })
        return self.responses.pop(0)


@pytest.fixture
def tools(monkeypatch):
    """Register Direct tools against a recording client and return them by name."""
    from mcp.server.fastmcp import FastMCP

    from yandex_mcp.tools.direct import ads as ads_module
    from yandex_mcp.tools.direct import keywords as keywords_module

    def build(responses):
        client = RecordingClient(responses)
        monkeypatch.setattr(ads_module, "api_client", client)
        monkeypatch.setattr(keywords_module, "api_client", client)

        server = FastMCP("test")
        ads_module.register(server)
        keywords_module.register(server)
        return client, server._tool_manager._tools

    return build


# ---------------------------------------------------------------------------
# Autotargeting
# ---------------------------------------------------------------------------

class TestAutotargetingInput:
    def test_only_supplied_flags_are_sent(self):
        params = UpdateAutotargetingInput(keyword_ids=[1], exact=True, broader=False)
        assert params.categories_payload() == {"Exact": "YES", "Broader": "NO"}
        assert params.brand_options_payload() == {}

    def test_brand_options_are_separate(self):
        params = UpdateAutotargetingInput(keyword_ids=[1], with_competitors_brand=False)
        assert params.categories_payload() == {}
        assert params.brand_options_payload() == {"WithCompetitorsBrand": "NO"}


@pytest.mark.asyncio
class TestUpdateAutotargetingTool:
    async def test_sends_settings_for_every_criterion(self, tools):
        client, registry = tools([
            {"result": {"UpdateResults": [{"Id": 205}, {"Id": 206}]}}
        ])

        result = await registry["direct_update_autotargeting"].fn(
            UpdateAutotargetingInput(
                keyword_ids=[205, 206],
                exact=True,
                narrow=False,
                alternative=False,
                accessory=False,
                broader=False,
            )
        )

        sent = client.calls[0]
        assert sent["service"] == "keywords"
        assert sent["method"] == "update"
        assert sent["params"]["Keywords"] == [
            {
                "Id": 205,
                "AutotargetingSettings": {
                    "Categories": {
                        "Exact": "YES",
                        "Narrow": "NO",
                        "Alternative": "NO",
                        "Accessory": "NO",
                        "Broader": "NO",
                    }
                },
            },
            {
                "Id": 206,
                "AutotargetingSettings": {
                    "Categories": {
                        "Exact": "YES",
                        "Narrow": "NO",
                        "Alternative": "NO",
                        "Accessory": "NO",
                        "Broader": "NO",
                    }
                },
            },
        ]
        assert "2 criterion(s)" in result

    async def test_refuses_empty_update(self, tools):
        client, registry = tools([])
        result = await registry["direct_update_autotargeting"].fn(
            UpdateAutotargetingInput(keyword_ids=[205])
        )
        assert "Nothing to update" in result
        assert client.calls == []

    async def test_reports_api_errors(self, tools):
        _, registry = tools([
            {"result": {"UpdateResults": [
                {"Errors": [{"Code": 5001, "Message": "Bad category", "Details": "why"}]}
            ]}}
        ])
        result = await registry["direct_update_autotargeting"].fn(
            UpdateAutotargetingInput(keyword_ids=[205], exact=True)
        )
        assert "Bad category" in result
        assert "why" in result


# ---------------------------------------------------------------------------
# Keyword bids
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSetKeywordBids:
    async def test_bid_is_an_alias_of_search_bid(self, tools):
        client, registry = tools([{"result": {"SetResults": [{"KeywordId": 1}]}}])

        await registry["direct_set_keyword_bids"].fn(
            SetKeywordBidsInput(keyword_bids=[{"keyword_id": 1, "bid": 220}])
        )

        assert client.calls[0]["params"]["KeywordBids"] == [
            {"KeywordId": 1, "SearchBid": 220_000_000}
        ]

    async def test_group_level_bid(self, tools):
        client, registry = tools([{"result": {"SetResults": [{"KeywordId": 1}]}}])

        await registry["direct_set_keyword_bids"].fn(
            SetKeywordBidsInput(keyword_bids=[{"adgroup_id": 99, "bid": 150.5}])
        )

        assert client.calls[0]["params"]["KeywordBids"] == [
            {"AdGroupId": 99, "SearchBid": 150_500_000}
        ]

    async def test_missing_bid_is_rejected_before_the_call(self, tools):
        client, registry = tools([])
        result = await registry["direct_set_keyword_bids"].fn(
            SetKeywordBidsInput(keyword_bids=[{"keyword_id": 1}])
        )
        assert "Nothing to set" in result
        assert client.calls == []

    async def test_errors_are_surfaced(self, tools):
        _, registry = tools([
            {"result": {"SetResults": [
                {"KeywordId": 1, "Errors": [{"Code": 4001, "Message": "Auto strategy"}]}
            ]}}
        ])
        result = await registry["direct_set_keyword_bids"].fn(
            SetKeywordBidsInput(keyword_bids=[{"keyword_id": 1, "bid": 220}])
        )
        assert "updated bids for 0" in result
        assert "Auto strategy" in result


# ---------------------------------------------------------------------------
# Combinatorial ads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestUpdateResponsiveAd:
    async def test_append_keeps_existing_titles(self, tools):
        client, registry = tools([
            {"result": {"Ads": [{
                "Id": 7,
                "Type": "TEXT_AD",
                "ResponsiveAd": {
                    "Titles": [{"Title": "Original"}],
                    "Texts": [{"Text": "Body"}],
                },
            }]}},
            {"result": {"UpdateResults": [{"Id": 7}]}},
        ])

        result = await registry["direct_update_responsive_ad"].fn(
            UpdateResponsiveAdInput(ad_id=7, titles=["Second", "Third"])
        )

        update_call = client.calls[1]["params"]["Ads"][0]
        assert update_call["ResponsiveAd"]["Titles"] == ["Original", "Second", "Third"]
        assert "Texts" not in update_call["ResponsiveAd"]
        assert "3 title(s)" in result
        # The read may use v5, the write must use v501.
        assert client.calls[1]["use_v501"] is True

    async def test_replace_overwrites(self, tools):
        client, registry = tools([{"result": {"UpdateResults": [{"Id": 7}]}}])

        await registry["direct_update_responsive_ad"].fn(
            UpdateResponsiveAdInput(ad_id=7, titles=["Only"], titles_mode="replace")
        )

        assert client.calls[0]["method"] == "update"
        assert client.calls[0]["params"]["Ads"][0]["ResponsiveAd"]["Titles"] == ["Only"]

    async def test_writes_go_to_the_v501_endpoint(self, tools):
        """Combinatorial ads are rejected by v5 with 'use v501'."""
        client, registry = tools([{"result": {"UpdateResults": [{"Id": 7}]}}])

        await registry["direct_update_responsive_ad"].fn(
            UpdateResponsiveAdInput(ad_id=7, titles=["Only"], titles_mode="replace")
        )

        assert client.calls[0]["use_v501"] is True

    async def test_append_does_not_duplicate(self, tools):
        client, registry = tools([
            {"result": {"Ads": [{
                "Id": 7,
                "ResponsiveAd": {"Titles": [{"Title": "Same"}], "Texts": []},
            }]}},
            {"result": {"UpdateResults": [{"Id": 7}]}},
        ])

        await registry["direct_update_responsive_ad"].fn(
            UpdateResponsiveAdInput(ad_id=7, titles=["Same", "New"])
        )

        assert client.calls[1]["params"]["Ads"][0]["ResponsiveAd"]["Titles"] == ["Same", "New"]

    async def test_title_limit_is_checked_before_sending(self, tools):
        client, registry = tools([
            {"result": {"Ads": [{
                "Id": 7,
                "ResponsiveAd": {
                    "Titles": [{"Title": f"T{i}"} for i in range(6)],
                    "Texts": [],
                },
            }]}},
        ])

        result = await registry["direct_update_responsive_ad"].fn(
            UpdateResponsiveAdInput(ad_id=7, titles=["A", "B"])
        )

        assert "the limit is 7" in result
        assert len(client.calls) == 1  # only the read, no update

    async def test_non_responsive_ad_is_reported(self, tools):
        _, registry = tools([
            {"result": {"Ads": [{"Id": 7, "Type": "TEXT_AD", "TextAd": {"Title": "x"}}]}},
        ])

        result = await registry["direct_update_responsive_ad"].fn(
            UpdateResponsiveAdInput(ad_id=7, titles=["A"])
        )

        assert "not a combinatorial ad" in result

    async def test_callouts_use_the_chosen_operation(self, tools):
        client, registry = tools([{"result": {"UpdateResults": [{"Id": 7}]}}])

        await registry["direct_update_responsive_ad"].fn(
            UpdateResponsiveAdInput(
                ad_id=7,
                callout_ad_extension_ids=[11, 12],
                callout_operation="ADD",
            )
        )

        setting = client.calls[0]["params"]["Ads"][0]["ResponsiveAd"]["CalloutSetting"]
        assert setting == {
            "AdExtensions": [
                {"AdExtensionId": 11, "Operation": "ADD"},
                {"AdExtensionId": 12, "Operation": "ADD"},
            ]
        }


@pytest.mark.asyncio
class TestGetAdsRequestsResponsiveFields:
    async def test_responsive_field_names_are_requested(self, tools):
        from yandex_mcp.models.direct import GetAdsInput

        client, registry = tools([{"result": {"Ads": []}}])
        await registry["direct_get_ads"].fn(GetAdsInput(ad_ids=[7]))

        assert "ResponsiveAdFieldNames" in client.calls[0]["params"]
        assert "Titles" in client.calls[0]["params"]["ResponsiveAdFieldNames"]


@pytest.mark.asyncio
class TestGetKeywordsRequestsAutotargeting:
    async def test_autotargeting_field_names_are_requested(self, tools):
        from yandex_mcp.models.direct import GetKeywordsInput

        client, registry = tools([{"result": {"Keywords": []}}])
        await registry["direct_get_keywords"].fn(GetKeywordsInput(adgroup_ids=[1]))

        params = client.calls[0]["params"]
        assert params["AutotargetingSettingsCategoriesFieldNames"] == [
            "Exact", "Narrow", "Alternative", "Accessory", "Broader"
        ]


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

class TestFormatters:
    def test_campaign_shows_strategy_and_negative_keywords(self):
        output = format_campaigns_markdown([{
            "Id": 1,
            "Name": "Search",
            "Type": "TEXT_CAMPAIGN",
            "NegativeKeywords": {"Items": ["free", "download"]},
            "TextCampaign": {
                "BiddingStrategy": {
                    "Search": {
                        "BiddingStrategyType": "WB_MAXIMUM_CLICKS",
                        "WbMaximumClicks": {"WeeklySpendLimit": 5_600_000_000},
                    },
                    "Network": {"BiddingStrategyType": "SERVING_OFF"},
                },
                "CounterIds": {"Items": [99193222]},
            },
        }])

        assert "WB_MAXIMUM_CLICKS" in output
        assert "WeeklySpendLimit 5600.00" in output
        assert "Negative keywords** (2): free, download" in output
        assert "99193222" in output

    def test_keyword_shows_autotargeting_categories(self):
        output = format_keywords_markdown([{
            "Id": 205,
            "Keyword": "---autotargeting",
            "AdGroupId": 1,
            "State": "ON",
            "Status": "ACCEPTED",
            "Bid": 55_000_000,
            "AutotargetingSettings": {
                "Categories": {"Exact": "YES", "Broader": "NO"},
                "BrandOptions": {"WithoutBrands": "YES", "WithCompetitorsBrand": "NO"},
            },
        }])

        assert "on: Exact | off: Broader" in output
        assert "Brand options**: WithoutBrands" in output
        assert "**Bid**: 55.00" in output

    def test_responsive_ad_lists_all_titles_and_texts(self):
        output = format_ads_markdown([{
            "Id": 7,
            "AdGroupId": 1,
            "CampaignId": 2,
            "State": "ON",
            "Status": "ACCEPTED",
            "Type": "TEXT_AD",
            "ResponsiveAd": {
                "Titles": [{"Title": "First"}, {"Title": "Second"}],
                "Texts": [{"Text": "Body"}],
                "Href": "https://example.com",
            },
        }])

        assert "**Titles** (2/7)" in output
        assert "- First" in output
        assert "- Second" in output
        assert "**Texts** (1/3)" in output
        assert "Sitelink set**: none" in output

    def test_long_negative_keyword_list_is_truncated(self):
        output = format_campaigns_markdown([{
            "Id": 1,
            "Name": "Search",
            "NegativeKeywords": {"Items": [f"word{i}" for i in range(40)]},
        }])

        assert "(40)" in output
        assert "+25 more" in output
