"""Yandex Direct ad tools."""

import json
from mcp.server.fastmcp import FastMCP

from ...client import api_client
from ...models.common import ResponseFormat
from ...models.direct import (
    GetAdsInput,
    CreateTextAdInput,
    CreateImageAdInput,
    CreateDynamicTextAdInput,
    CreateShoppingAdInput,
    CreateResponsiveAdInput,
    UpdateResponsiveAdInput,
    UpdateTextAdInput,
    ManageAdInput,
)
from ...formatters.direct import format_ads_markdown
from ...utils import handle_api_error
from ._helpers import register_manage_tool


def register(mcp: FastMCP) -> None:
    """Register ad tools."""

    @mcp.tool(
        name="direct_get_ads",
        annotations={
            "title": "Get Yandex Direct Ads",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def direct_get_ads(params: GetAdsInput) -> str:
        """Get list of ads from Yandex Direct.

        Retrieves ads with their content and moderation status.
        """
        try:
            selection_criteria = {}

            if params.campaign_ids:
                selection_criteria["CampaignIds"] = params.campaign_ids
            if params.adgroup_ids:
                selection_criteria["AdGroupIds"] = params.adgroup_ids
            if params.ad_ids:
                selection_criteria["Ids"] = params.ad_ids
            if params.states:
                selection_criteria["States"] = [s.value for s in params.states]
            if params.statuses:
                selection_criteria["Statuses"] = [s.value for s in params.statuses]

            request_params = {
                "SelectionCriteria": selection_criteria,
                "FieldNames": ["Id", "AdGroupId", "CampaignId", "Type", "State", "Status", "StatusClarification"],
                "TextAdFieldNames": ["Title", "Title2", "Text", "Href", "Mobile", "DisplayDomain", "AdImageHash", "SitelinkSetId"],
                "TextImageAdFieldNames": ["AdImageHash", "Href"],
                "Page": {
                    "Limit": params.limit,
                    "Offset": params.offset
                }
            }

            if params.include_responsive:
                request_params["ResponsiveAdFieldNames"] = [
                    "Titles", "Texts", "Href", "DisplayDomain", "DisplayUrlPath",
                    "SitelinkSetId", "AdImages", "AdExtensions", "VideoExtensions",
                    "BusinessId",
                ]

            result = await api_client.direct_request("ads", "get", request_params)

            # Check for API error
            if "error" in result:
                err = result["error"]
                return f"API Error: {err.get('error_code')}: {err.get('error_string')} | {err.get('error_detail', '')}"

            ads = result.get("result", {}).get("Ads", [])

            if params.response_format == ResponseFormat.JSON:
                return json.dumps({"ads": ads, "total": len(ads)}, indent=2, ensure_ascii=False)

            return format_ads_markdown(ads)

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_create_text_ad",
        annotations={
            "title": "Create Yandex Direct Text Ad",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def direct_create_text_ad(params: CreateTextAdInput) -> str:
        """Create a new text ad in an ad group.

        Creates a text ad with title, text, and landing page URL.
        The ad will be sent for moderation automatically.
        """
        try:
            text_ad = {
                "Title": params.title,
                "Text": params.text,
                "Href": params.href,
                "Mobile": "YES" if params.mobile else "NO"
            }

            if params.title2:
                text_ad["Title2"] = params.title2
            if params.ad_image_hash:
                text_ad["AdImageHash"] = params.ad_image_hash

            ad = {
                "AdGroupId": params.adgroup_id,
                "TextAd": text_ad
            }

            request_params = {
                "Ads": [ad]
            }

            result = await api_client.direct_request("ads", "add", request_params)
            add_results = result.get("result", {}).get("AddResults", [])

            if add_results and add_results[0].get("Id"):
                return f"Text ad created successfully. ID: {add_results[0]['Id']}\nAd will be sent for moderation."

            errors = []
            for r in add_results:
                if r.get("Errors"):
                    errors.extend([e.get("Message", "Unknown error") for e in r["Errors"]])

            return f"Failed to create ad:\n" + "\n".join(f"- {e}" for e in errors)

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_create_image_ad",
        annotations={
            "title": "Create Yandex Direct Image Ad",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def direct_create_image_ad(params: CreateImageAdInput) -> str:
        """Create a new image ad (banner) in an ad group.

        Creates an IMAGE_AD with the given image hash and landing page.
        Use image hashes from existing ads or upload via web interface.
        """
        try:
            ad = {
                "AdGroupId": params.adgroup_id,
                "TextImageAd": {
                    "AdImageHash": params.ad_image_hash,
                    "Href": params.href
                }
            }

            request_params = {"Ads": [ad]}

            result = await api_client.direct_request("ads", "add", request_params)

            if "error" in result:
                err = result["error"]
                return f"API Error: {err.get('error_code')}: {err.get('error_string')} | {err.get('error_detail', '')}"

            add_results = result.get("result", {}).get("AddResults", [])

            if add_results and add_results[0].get("Id"):
                return f"Image ad created successfully. ID: {add_results[0]['Id']}\nAd will be sent for moderation."

            errors = []
            for r in add_results:
                if r.get("Errors"):
                    errors.extend([f"{e.get('Code')}: {e.get('Message')} | {e.get('Details', '')}" for e in r["Errors"]])

            return f"Failed to create image ad:\n" + "\n".join(f"- {e}" for e in errors)

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_create_dynamic_ad",
        annotations={
            "title": "Create Dynamic Text Ad",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def direct_create_dynamic_ad(params: CreateDynamicTextAdInput) -> str:
        """Create a dynamic text ad in a dynamic ad group.

        Title is auto-generated from feed data.
        Only text needs to be specified.
        Used in DYNAMIC_TEXT_CAMPAIGN with feed.
        """
        try:
            dynamic_ad = {
                "Text": params.text,
            }

            if params.ad_image_hash:
                dynamic_ad["AdImageHash"] = params.ad_image_hash
            if params.sitelink_set_id:
                dynamic_ad["SitelinkSetId"] = params.sitelink_set_id

            ad = {
                "AdGroupId": params.adgroup_id,
                "DynamicTextAd": dynamic_ad
            }

            request_params = {"Ads": [ad]}

            result = await api_client.direct_request("ads", "add", request_params)

            if "error" in result:
                err = result["error"]
                return f"API Error: {err.get('error_code')}: {err.get('error_string')} | {err.get('error_detail', '')}"

            add_results = result.get("result", {}).get("AddResults", [])

            if add_results and add_results[0].get("Id"):
                return f"Dynamic text ad created successfully. ID: {add_results[0]['Id']}\nAd will be sent for moderation."

            errors = []
            for r in add_results:
                if r.get("Errors"):
                    errors.extend([f"{e.get('Code')}: {e.get('Message')} | {e.get('Details', '')}" for e in r["Errors"]])

            return f"Failed to create dynamic ad:\n" + "\n".join(f"- {e}" for e in errors)

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_create_shopping_ad",
        annotations={
            "title": "Create Shopping Ad (ЕПК)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def direct_create_shopping_ad(params: CreateShoppingAdInput) -> str:
        """Create a shopping ad (товарное объявление) in a UnifiedCampaign group.

        Shopping ads use product feed data to auto-generate ads.
        Replaces SmartAd and DynamicAd in the new ЕПК (Unified Performance Campaign) format.
        Requires v501 API endpoint.
        """
        try:
            shopping_ad = {
                "FeedId": params.feed_id,
            }

            if params.feed_filter_conditions:
                shopping_ad["FeedFilterConditions"] = {
                    "Items": [
                        {
                            "Operand": c.operand,
                            "Operator": c.operator,
                            "Arguments": c.arguments
                        }
                        for c in params.feed_filter_conditions
                    ]
                }

            if params.default_texts:
                shopping_ad["DefaultTexts"] = params.default_texts

            if params.business_id:
                shopping_ad["BusinessId"] = params.business_id

            if params.sitelink_set_id:
                shopping_ad["SitelinkSetId"] = params.sitelink_set_id

            ad = {
                "AdGroupId": params.adgroup_id,
                "ShoppingAd": shopping_ad
            }

            request_params = {"Ads": [ad]}

            # ShoppingAd requires v501 API
            result = await api_client.direct_request("ads", "add", request_params, use_v501=True)

            if "error" in result:
                err = result["error"]
                return f"API Error: {err.get('error_code')}: {err.get('error_string')} | {err.get('error_detail', '')}"

            add_results = result.get("result", {}).get("AddResults", [])

            if add_results and add_results[0].get("Id"):
                return f"Shopping ad created successfully. ID: {add_results[0]['Id']}\nFeed: {params.feed_id}\nGroup: {params.adgroup_id}"

            errors = []
            for r in add_results:
                if r.get("Errors"):
                    errors.extend([f"{e.get('Code')}: {e.get('Message')} | {e.get('Details', '')}" for e in r["Errors"]])

            import json as _json
            req_dump = _json.dumps(request_params, ensure_ascii=False, indent=2)
            return f"Failed to create shopping ad:\n" + "\n".join(f"- {e}" for e in errors) + f"\n\nRequest:\n```json\n{req_dump}\n```"

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_update_ad",
        annotations={
            "title": "Update Yandex Direct Ad",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def direct_update_ad(params: UpdateTextAdInput) -> str:
        """Update a text ad.

        Allows updating ad title, text, and landing page URL.
        Only specified fields will be updated.
        Note: Updated ad will need to be re-moderated.
        """
        try:
            text_ad_update = {}

            if params.title:
                text_ad_update["Title"] = params.title
            if params.title2:
                text_ad_update["Title2"] = params.title2
            if params.text:
                text_ad_update["Text"] = params.text
            if params.href:
                text_ad_update["Href"] = params.href
            if params.ad_image_hash:
                text_ad_update["AdImageHash"] = params.ad_image_hash
            if params.video_extension_creative_id:
                text_ad_update["VideoExtension"] = {
                    "CreativeId": params.video_extension_creative_id
                }
            if params.sitelink_set_id:
                text_ad_update["SitelinkSetId"] = params.sitelink_set_id

            if not text_ad_update:
                return "No fields specified for update."

            ad_update = {
                "Id": params.ad_id,
                "TextAd": text_ad_update
            }

            request_params = {
                "Ads": [ad_update]
            }

            result = await api_client.direct_request("ads", "update", request_params)
            update_results = result.get("result", {}).get("UpdateResults", [])

            errors = []
            for r in update_results:
                if r.get("Errors"):
                    errors.extend([e.get("Message", "Unknown error") for e in r["Errors"]])
                if r.get("Warnings"):
                    errors.extend([f"Warning: {w.get('Message', 'Unknown warning')}" for w in r["Warnings"]])

            if errors:
                return f"Update completed with issues:\n" + "\n".join(f"- {e}" for e in errors)

            return f"Ad {params.ad_id} updated successfully. Note: Submit for moderation using direct_moderate_ads."

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_create_responsive_ad",
        annotations={
            "title": "Create Yandex Direct Combinatorial Ad",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    async def direct_create_responsive_ad(params: CreateResponsiveAdInput) -> str:
        """Create a combinatorial (responsive) ad in an ad group.

        Combinatorial ads replaced plain text ads in unified performance
        campaigns: you supply up to 7 titles and up to 3 texts and Direct picks
        the best combination per impression. Use this instead of
        direct_create_text_ad for new ads.
        """
        try:
            responsive_ad = {
                "Titles": params.titles,
                "Texts": params.texts,
            }

            if params.href:
                responsive_ad["Href"] = params.href
            if params.display_url_path:
                responsive_ad["DisplayUrlPath"] = params.display_url_path
            if params.ad_image_hashes:
                responsive_ad["AdImageHashes"] = params.ad_image_hashes
            if params.sitelink_set_id:
                responsive_ad["SitelinkSetId"] = params.sitelink_set_id
            if params.ad_extension_ids:
                responsive_ad["AdExtensionIds"] = params.ad_extension_ids
            if params.video_extension_ids:
                responsive_ad["VideoExtensionIds"] = params.video_extension_ids
            if params.business_id:
                responsive_ad["BusinessId"] = params.business_id

            if not params.href and not params.business_id:
                return "Provide href or business_id: a combinatorial ad needs a destination."

            request_params = {
                "Ads": [{
                    "AdGroupId": params.adgroup_id,
                    "ResponsiveAd": responsive_ad,
                }]
            }

            result = await api_client.direct_request("ads", "add", request_params)

            if "error" in result:
                err = result["error"]
                return (
                    f"API Error: {err.get('error_code')}: {err.get('error_string')} "
                    f"| {err.get('error_detail', '')}"
                )

            add_results = result.get("result", {}).get("AddResults", [])

            if add_results and add_results[0].get("Id"):
                return (
                    f"Combinatorial ad created successfully. ID: {add_results[0]['Id']}\n"
                    f"{len(params.titles)} title(s), {len(params.texts)} text(s). "
                    "The ad goes to moderation automatically."
                )

            errors = []
            for r in add_results:
                for err in r.get("Errors", []):
                    errors.append(
                        err.get("Message", "Unknown error")
                        + (f" - {err['Details']}" if err.get("Details") else "")
                    )

            return "Failed to create ad:\n" + "\n".join(f"- {e}" for e in errors)

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_update_responsive_ad",
        annotations={
            "title": "Update Yandex Direct Combinatorial Ad",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def direct_update_responsive_ad(params: UpdateResponsiveAdInput) -> str:
        """Update a combinatorial (responsive) ad.

        With titles_mode/texts_mode set to 'append' (the default) the supplied
        titles and texts are added to the ones already on the ad, which is how
        you widen a one-title ad without retyping it. Use 'replace' to overwrite.
        Editing an ad sends it back to moderation.
        """
        try:
            needs_current = (
                (params.titles and params.titles_mode == "append")
                or (params.texts and params.texts_mode == "append")
            )

            current_titles: list = []
            current_texts: list = []

            if needs_current:
                current = await api_client.direct_request("ads", "get", {
                    "SelectionCriteria": {"Ids": [params.ad_id]},
                    "FieldNames": ["Id", "Type"],
                    "ResponsiveAdFieldNames": ["Titles", "Texts"],
                })

                if "error" in current:
                    err = current["error"]
                    return (
                        f"API Error while reading the ad: {err.get('error_code')}: "
                        f"{err.get('error_string')} | {err.get('error_detail', '')}"
                    )

                ads = current.get("result", {}).get("Ads", [])
                if not ads:
                    return f"Ad {params.ad_id} not found."

                responsive = ads[0].get("ResponsiveAd") or {}
                if not responsive:
                    return (
                        f"Ad {params.ad_id} is not a combinatorial ad "
                        f"(type {ads[0].get('Type', 'unknown')}). Use direct_update_ad instead."
                    )

                current_titles = [
                    t.get("Title") for t in responsive.get("Titles", []) if t.get("Title")
                ]
                current_texts = [
                    t.get("Text") for t in responsive.get("Texts", []) if t.get("Text")
                ]

            responsive_update = {}

            if params.titles:
                titles = (
                    current_titles + [t for t in params.titles if t not in current_titles]
                    if params.titles_mode == "append"
                    else list(params.titles)
                )
                if len(titles) > 7:
                    return (
                        f"Too many titles: {len(titles)} after merging, the limit is 7. "
                        "Use titles_mode='replace' or send fewer titles."
                    )
                responsive_update["Titles"] = titles

            if params.texts:
                texts = (
                    current_texts + [t for t in params.texts if t not in current_texts]
                    if params.texts_mode == "append"
                    else list(params.texts)
                )
                if len(texts) > 3:
                    return (
                        f"Too many texts: {len(texts)} after merging, the limit is 3. "
                        "Use texts_mode='replace' or send fewer texts."
                    )
                responsive_update["Texts"] = texts

            if params.href:
                responsive_update["Href"] = params.href
            if params.display_url_path:
                responsive_update["DisplayUrlPath"] = params.display_url_path
            if params.ad_image_hashes:
                responsive_update["AdImageHashes"] = {"Items": params.ad_image_hashes}
            if params.sitelink_set_id:
                responsive_update["SitelinkSetId"] = params.sitelink_set_id
            if params.video_extension_ids:
                responsive_update["VideoExtensionIds"] = {"Items": params.video_extension_ids}
            if params.business_id:
                responsive_update["BusinessId"] = params.business_id
            if params.callout_ad_extension_ids:
                responsive_update["CalloutSetting"] = {
                    "AdExtensions": [
                        {"AdExtensionId": ext_id, "Operation": params.callout_operation}
                        for ext_id in params.callout_ad_extension_ids
                    ]
                }

            if not responsive_update:
                return "No fields specified for update."

            result = await api_client.direct_request("ads", "update", {
                "Ads": [{"Id": params.ad_id, "ResponsiveAd": responsive_update}]
            })

            if "error" in result:
                err = result["error"]
                return (
                    f"API Error: {err.get('error_code')}: {err.get('error_string')} "
                    f"| {err.get('error_detail', '')}"
                )

            update_results = result.get("result", {}).get("UpdateResults", [])

            errors = []
            warnings = []
            for r in update_results:
                for err in r.get("Errors", []):
                    errors.append(
                        err.get("Message", "Unknown error")
                        + (f" - {err['Details']}" if err.get("Details") else "")
                    )
                for warn in r.get("Warnings", []):
                    warnings.append(warn.get("Message", "Unknown warning"))

            if errors:
                return "Update failed:\n" + "\n".join(f"- {e}" for e in errors)

            summary = []
            if "Titles" in responsive_update:
                summary.append(f"{len(responsive_update['Titles'])} title(s)")
            if "Texts" in responsive_update:
                summary.append(f"{len(responsive_update['Texts'])} text(s)")

            response = f"Ad {params.ad_id} updated"
            if summary:
                response += f": now has {', '.join(summary)}"
            response += ". It has been sent back to moderation."
            if warnings:
                response += "\n\nWarnings:\n" + "\n".join(f"- {w}" for w in warnings)
            return response

        except Exception as e:
            return handle_api_error(e)

    @mcp.tool(
        name="direct_moderate_ads",
        annotations={
            "title": "Submit Yandex Direct Ads for Moderation",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    )
    async def direct_moderate_ads(params: ManageAdInput) -> str:
        """Submit ads for moderation.

        Sends ads to be reviewed by Yandex moderators.
        Required after creating or updating ads.
        Can use campaign_id to moderate all draft ads (workaround for large ad IDs in v501).
        """
        try:
            ad_ids = params.ad_ids

            # If campaign_id provided, look up all DRAFT ads in that campaign
            if params.campaign_id and not ad_ids:
                lookup_params = {
                    "SelectionCriteria": {
                        "CampaignIds": [params.campaign_id],
                        "Statuses": ["DRAFT"]
                    },
                    "FieldNames": ["Id", "Status"]
                }
                lookup_result = await api_client.direct_request("ads", "get", lookup_params, use_v501=True)
                found_ads = lookup_result.get("result", {}).get("Ads", [])
                if not found_ads:
                    return f"No draft ads found in campaign {params.campaign_id}."
                ad_ids = [a["Id"] for a in found_ads]

            if not ad_ids:
                return "No ad IDs specified and no campaign_id provided."

            request_params = {
                "SelectionCriteria": {"Ids": ad_ids}
            }

            result = await api_client.direct_request("ads", "moderate", request_params, use_v501=True)
            moderate_results = result.get("result", {}).get("ModerateResults", [])

            success = [r["Id"] for r in moderate_results if r.get("Id") and not r.get("Errors")]
            errors = []
            for r in moderate_results:
                if r.get("Errors"):
                    errors.extend([f"ID {r.get('Id', '?')}: {e.get('Message', 'Unknown error')}" for e in r["Errors"]])

            response = f"Successfully submitted {len(success)} ad(s) for moderation."
            if errors:
                response += f"\n\nErrors:\n" + "\n".join(f"- {e}" for e in errors)

            return response

        except Exception as e:
            return handle_api_error(e)

    for action in ("suspend", "resume", "archive", "unarchive", "delete"):
        register_manage_tool(
            mcp,
            service="ads",
            action=action,
            entity="ad",
            input_model=ManageAdInput,
            ids_field="ad_ids",
        )
