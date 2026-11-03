"""The motion graphics spec (what a project stores and the storyboard edits)
and the template catalog (typed slots with limits, scene types, defaults).

Spec
  template_id, style_id, title, seed
  scenes: [{id, type, slots: {key: value}, duration: seconds or null (auto),
            voiceover: text or null}]
  data: {columns, rows} or null (CSV or table editor), data_options:
        {top_n, period_seconds, chart, highlight, prefix, suffix, decimals,
         compact, units_label}
  source, disclaimer, cta: {text, url}
  options: {loop, captions, safe_zone, intensity, sfx, beat_sync, logo_bug,
            paid_partnership: {enabled, brand}, ai_label}

Shared scene types available to every template: logo_sting, end_card,
source_card (auto-added and required for data templates) and disclaimer
(auto-added and required for the market recap).
"""

from __future__ import annotations

import math
import random
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .design import ASPECTS, DEFAULT_STYLE, SAFE_ZONE_PRESETS, STYLE_IDS


# ---------------------------------------------------------------------------
# Template catalog
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Slot:
    key: str
    kind: str  # text | longtext | number | image | items | bool | choice
    label: str
    required: bool = False
    max_chars: int = 0
    max_words: int = 0
    min: Optional[float] = None
    max: Optional[float] = None
    choices: tuple = ()
    help: str = ""
    item_fields: tuple = ()  # for items: tuple of Slot
    max_items: int = 0
    ai_image: bool = False  # an image slot that can be AI generated from a prompt

    def view(self) -> dict:
        d = {"key": self.key, "kind": self.kind, "label": self.label, "required": self.required}
        for k in ("max_chars", "max_words", "max_items"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.choices:
            d["choices"] = list(self.choices)
        if self.help:
            d["help"] = self.help
        if self.item_fields:
            d["item_fields"] = [f.view() for f in self.item_fields]
        if self.ai_image:
            d["ai_image"] = True
        return d


@dataclass(frozen=True)
class SceneType:
    type: str
    label: str
    slots: tuple
    min_count: int = 1
    max_count: int = 1
    default_seconds: float = 3.0
    min_seconds: float = 1.5
    voiceover: bool = True
    removable: bool = True

    def view(self) -> dict:
        return {"type": self.type, "label": self.label, "slots": [s.view() for s in self.slots],
                "min_count": self.min_count, "max_count": self.max_count,
                "default_seconds": self.default_seconds, "min_seconds": self.min_seconds,
                "voiceover": self.voiceover, "removable": self.removable}


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    category: str
    aspects: tuple
    default_aspect: str
    length: tuple  # (min, max) seconds
    scene_types: tuple
    default_scenes: tuple  # tuple of dicts {type, slots, voiceover}
    data_kind: Optional[str] = None  # race | series | tickers | versus
    requires_source: bool = False
    requires_disclaimer: bool = False
    sample_data: Optional[str] = None
    default_style: str = DEFAULT_STYLE
    music_mood: str = "uplifting"
    captions_default: bool = True
    long_form: bool = False  # 16:9 may run longer

    def scene_type(self, t: str) -> Optional[SceneType]:
        for st in self.scene_types + SHARED_SCENES:
            if st.type == t:
                return st
        return None

    def view(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description, "category": self.category,
            "aspects": list(self.aspects), "default_aspect": self.default_aspect,
            "length": {"min_seconds": self.length[0], "max_seconds": self.length[1]},
            "scene_types": [s.view() for s in self.scene_types],
            "shared_scene_types": [s.view() for s in SHARED_SCENES],
            "data_kind": self.data_kind, "requires_source": self.requires_source,
            "requires_disclaimer": self.requires_disclaimer, "default_style": self.default_style,
            "music_mood": self.music_mood, "sample_data": self.sample_data,
        }


T = Slot  # brevity in the tables below

SHARED_SCENES = (
    SceneType("logo_sting", "Logo sting", (T("tagline", "text", "Tagline", max_chars=40),),
              min_count=0, max_count=2, default_seconds=2.5, min_seconds=2.0, voiceover=False),
    SceneType("end_card", "End card (CTA)", (
        T("headline", "text", "Headline", required=True, max_chars=48, max_words=8),
        T("cta", "text", "Button text", max_chars=24),
        T("url", "text", "URL or handle", max_chars=60)),
        min_count=0, max_count=1, default_seconds=3.0, min_seconds=2.0),
    SceneType("source_card", "Source card", (T("note", "text", "Note", max_chars=90),),
              min_count=0, max_count=1, default_seconds=2.2, min_seconds=2.0, voiceover=False),
    SceneType("disclaimer", "Disclaimer card", (),
              min_count=0, max_count=1, default_seconds=3.0, min_seconds=2.0, voiceover=False),
    # Reel series pieces: a poll the viewer answers in the comments, and an
    # end card pointing at the next part.
    SceneType("poll", "Poll (comment to answer)", (
        T("question", "text", "Question", required=True, max_chars=70, max_words=12),
        T("options", "items", "Options", max_items=4,
          item_fields=(T("text", "text", "Option", required=True, max_chars=40),)),
        T("note", "text", "Prompt", max_chars=40, help="Default: Comment A, B, C or D")),
        min_count=0, max_count=1, default_seconds=4.5, min_seconds=3.0),
    SceneType("next_part", "Next part", (
        T("teaser", "text", "What comes next", required=True, max_chars=60, max_words=10),
        T("cta", "text", "Button text", max_chars=30, help="Like Follow for part 3"),
        T("comment", "text", "Comment line", max_chars=50, help="Like Comment PART 3 and I will send it")),
        min_count=0, max_count=1, default_seconds=3.2, min_seconds=2.2),
)

DEFAULT_FINANCE_DISCLAIMER = ("For information only. Not investment advice. Markets carry risk; "
                              "past performance does not guarantee future results.")

_HOOK = T("text", "text", "Hook line", required=True, max_chars=60, max_words=7, help="At most 7 words")
_KICKER = T("kicker", "text", "Kicker", max_chars=28)

TEMPLATES: dict[str, Template] = {}


def _reg(t: Template) -> Template:
    TEMPLATES[t.id] = t
    return t


_reg(Template(
    id="big_number", name="Big Number Reveal", category="data",
    description="One striking number: hook, odometer reveal, what it means, takeaway. Source line always.",
    aspects=ASPECTS, default_aspect="9:16", length=(8, 20),
    scene_types=(
        SceneType("hook", "Hook", (_HOOK, _KICKER), default_seconds=1.6, min_seconds=1.2),
        SceneType("reveal", "Number reveal", (
            T("value", "number", "Number", required=True),
            T("decimals", "number", "Decimals", min=0, max=3),
            T("prefix", "text", "Prefix", max_chars=4, help="For example $"),
            T("unit", "text", "Unit", max_chars=12, help="For example M, %, x"),
            T("label", "text", "What it counts", required=True, max_chars=60, max_words=10)),
            default_seconds=3.0, min_seconds=2.4),
        SceneType("meaning", "Meaning", (
            T("text", "text", "What it means", required=True, max_chars=90, max_words=14),
            T("compare_label", "text", "Comparison label", max_chars=30),
            T("compare_value", "number", "Comparison value"),
            T("value_label", "text", "This value's label", max_chars=30)),
            min_count=0, default_seconds=3.4),
        SceneType("takeaway", "Takeaway", (
            T("text", "text", "Takeaway", required=True, max_chars=70, max_words=10),),
            min_count=0, default_seconds=2.8),
    ),
    default_scenes=(
        {"type": "hook", "slots": {"text": "India now builds most of its phones", "kicker": "Manufacturing"}},
        {"type": "reveal", "slots": {"value": 99.2, "decimals": 1, "unit": "%", "label": "of phones sold in India are made in India"}},
        {"type": "meaning", "slots": {"text": "A decade ago most handsets were imported", "compare_label": "2014", "compare_value": 26, "value_label": "2024"}},
        {"type": "takeaway", "slots": {"text": "Assembly moved. Components are next."}},
    ),
    requires_source=True, default_style="swiss_grid", music_mood="documentary",
))

_reg(Template(
    id="kinetic_quote", name="Kinetic Quote", category="text",
    description="A quote that slams in beat by beat with emphasis words, held payoff and attribution.",
    aspects=ASPECTS, default_aspect="9:16", length=(8, 40),
    scene_types=(
        SceneType("hook", "Hook phrase", (T("text", "text", "Hook", required=True, max_chars=40, max_words=5),),
                  min_count=0, default_seconds=1.4, min_seconds=1.0),
        SceneType("line", "Beat", (
            T("text", "text", "Words", required=True, max_chars=60, max_words=8),
            T("emphasis", "text", "Emphasis words", max_chars=40, help="Words to color, separated by spaces")),
            min_count=1, max_count=12, default_seconds=1.8, min_seconds=1.0),
        SceneType("payoff", "Payoff", (
            T("text", "text", "Payoff", required=True, max_chars=60, max_words=8),
            T("emphasis", "text", "Emphasis words", max_chars=40)),
            min_count=1, max_count=1, default_seconds=2.4, min_seconds=1.5),
        SceneType("attribution", "Attribution", (
            T("name", "text", "Speaker", required=True, max_chars=40),
            T("title", "text", "Title", max_chars=60),
            T("photo", "image", "Photo")),
            min_count=0, default_seconds=2.4, min_seconds=2.0, voiceover=False),
    ),
    default_scenes=(
        {"type": "line", "slots": {"text": "The best way", "emphasis": "best"}},
        {"type": "line", "slots": {"text": "to predict the future", "emphasis": "future"}},
        {"type": "payoff", "slots": {"text": "is to invent it", "emphasis": "invent"}},
        {"type": "attribution", "slots": {"name": "Alan Kay", "title": "Computer scientist"}},
    ),
    default_style="editorial_serif", music_mood="lofi", captions_default=False,
))

_reg(Template(
    id="bar_race", name="Bar Chart Race", category="data",
    description="Ranked bars racing through time from your CSV, with a period ticker and a frozen final ranking.",
    aspects=("16:9", "9:16", "1:1", "4:5"), default_aspect="16:9", length=(15, 360),
    scene_types=(
        SceneType("title", "Title", (
            T("title", "text", "Title", required=True, max_chars=60, max_words=9),
            T("subtitle", "text", "Subtitle", max_chars=80),
            T("units", "text", "Units", max_chars=30)),
            default_seconds=2.5, min_seconds=2.0),
        SceneType("race", "Race", (
            T("heading", "text", "Heading during the race", max_chars=60),
            T("notes", "items", "Notes at periods", max_items=8,
              item_fields=(T("period", "text", "Period", required=True, max_chars=20),
                           T("text", "text", "Note", required=True, max_chars=60)))),
            default_seconds=20.0, min_seconds=6.0),
    ),
    default_scenes=(
        {"type": "title", "slots": {"title": "The world's largest economies", "subtitle": "GDP, 2000 to 2024", "units": "USD trillions"}},
        {"type": "race", "slots": {"heading": "GDP, USD trillions", "notes": [{"period": "2010", "text": "China passes Japan"}]}},
    ),
    data_kind="race", requires_source=True, default_style="swiss_grid", music_mood="epic", long_form=True,
    sample_data=("Year,United States,China,Japan,Germany,India,United Kingdom,France\n"
                 "2000,10.25,1.21,4.97,1.95,0.47,1.66,1.37\n2004,12.22,1.96,4.89,2.85,0.71,2.42,2.12\n"
                 "2008,14.77,4.59,5.11,3.75,1.2,2.93,2.92\n2012,16.25,8.53,6.27,3.53,1.83,2.71,2.68\n"
                 "2016,18.8,11.23,5.0,3.47,2.29,2.69,2.47\n2020,21.32,14.69,5.04,3.89,2.67,2.7,2.64\n"
                 "2024,28.78,18.53,4.11,4.66,3.89,3.59,3.17\n"),
))

_reg(Template(
    id="listicle", name="Countdown Listicle", category="text",
    description="Top N countdown: number slams, titles wipe in, one-line details, optional images, loopable.",
    aspects=("9:16", "1:1", "4:5", "16:9"), default_aspect="9:16", length=(15, 60),
    scene_types=(
        SceneType("hook", "Hook", (T("text", "text", "Hook (states the payoff)", required=True, max_chars=60,
                                     max_words=8), _KICKER), default_seconds=2.0, min_seconds=1.5),
        SceneType("item", "Item", (
            T("title", "text", "Title", required=True, max_chars=40, max_words=6),
            T("detail", "text", "Detail", max_chars=80, max_words=14),
            T("image", "image", "Image", ai_image=True),
            T("image_prompt", "text", "AI image prompt", max_chars=300)),
            min_count=3, max_count=10, default_seconds=4.5, min_seconds=3.0),
        SceneType("cta", "Call to action", (T("text", "text", "CTA", required=True, max_chars=50, max_words=8),),
                  min_count=0, default_seconds=2.2, min_seconds=1.5),
    ),
    default_scenes=(
        {"type": "hook", "slots": {"text": "5 habits that compound faster than money", "kicker": "Top 5"}},
        {"type": "item", "slots": {"title": "Reading daily", "detail": "Twenty pages a day is about 30 books a year"}},
        {"type": "item", "slots": {"title": "Sleep schedule", "detail": "Same bedtime, even on weekends"}},
        {"type": "item", "slots": {"title": "Walking meetings", "detail": "Ideas move when you do"}},
        {"type": "item", "slots": {"title": "Writing it down", "detail": "One page a night clears tomorrow"}},
        {"type": "item", "slots": {"title": "Saying no", "detail": "Protect the hours that matter"}},
        {"type": "cta", "slots": {"text": "Save this for Monday"}},
    ),
    default_style="brutalist_mono", music_mood="playful",
))

_reg(Template(
    id="versus", name="X vs Y", category="data",
    description="Two contenders, metric rounds with twin bars and a score ticker, then the verdict.",
    aspects=ASPECTS, default_aspect="9:16", length=(12, 45),
    scene_types=(
        SceneType("intro", "Split intro", (
            T("a_name", "text", "Name A", required=True, max_chars=24),
            T("b_name", "text", "Name B", required=True, max_chars=24),
            T("a_logo", "image", "Logo A"), T("b_logo", "image", "Logo B"),
            T("question", "text", "Question", max_chars=50)), default_seconds=2.2, min_seconds=2.0),
        SceneType("round", "Metric round", (
            T("label", "text", "Metric", required=True, max_chars=40),
            T("a", "number", "Value A", required=True), T("b", "number", "Value B", required=True),
            T("unit", "text", "Unit", max_chars=10), T("prefix", "text", "Prefix", max_chars=4),
            T("higher_is_better", "bool", "Higher is better")),
            min_count=1, max_count=6, default_seconds=3.4, min_seconds=2.8),
        SceneType("verdict", "Verdict", (T("text", "text", "Verdict", required=True, max_chars=70, max_words=12),),
                  default_seconds=2.6, min_seconds=2.0),
    ),
    default_scenes=(
        {"type": "intro", "slots": {"a_name": "Rail", "b_name": "Air", "question": "Delhi to Mumbai: which wins?"}},
        {"type": "round", "slots": {"label": "Door to door hours", "a": 16, "b": 5.5, "unit": "h", "higher_is_better": False}},
        {"type": "round", "slots": {"label": "Fare", "a": 1800, "b": 5400, "prefix": "Rs ", "higher_is_better": False}},
        {"type": "round", "slots": {"label": "CO2 per trip", "a": 9, "b": 160, "unit": " kg", "higher_is_better": False}},
        {"type": "verdict", "slots": {"text": "Rail wins on fare and carbon. Air wins on time."}},
    ),
    data_kind="versus", requires_source=True, default_style="soft_gradient", music_mood="uplifting",
))

_reg(Template(
    id="promo", name="Product Promo", category="promo",
    description="Launch video: claim, features in a device frame with camera push and callouts, recap, logo and CTA.",
    aspects=ASPECTS, default_aspect="16:9", length=(12, 90),
    scene_types=(
        SceneType("claim", "Claim", (T("text", "text", "Claim", required=True, max_chars=48, max_words=6),
                                     T("product", "text", "Product name", max_chars=30)),
                  default_seconds=2.5, min_seconds=2.0),
        SceneType("feature", "Feature", (
            T("title", "text", "Feature", required=True, max_chars=40, max_words=6),
            T("line", "text", "One line", max_chars=80, max_words=14),
            T("screenshot", "image", "Screenshot"),
            T("device", "choice", "Frame", choices=("browser", "phone")),
            T("callout", "text", "Callout label", max_chars=24),
            T("focus_x", "number", "Focus x (0 to 1)", min=0, max=1),
            T("focus_y", "number", "Focus y (0 to 1)", min=0, max=1)),
            min_count=1, max_count=4, default_seconds=5.0, min_seconds=4.0),
        SceneType("recap", "Recap", (
            T("benefits", "items", "Benefits", max_items=3,
              item_fields=(T("text", "text", "Benefit", required=True, max_chars=40),)),),
            min_count=0, default_seconds=3.2),
    ),
    default_scenes=(
        {"type": "claim", "slots": {"text": "Reports that write themselves", "product": "Ledgerly"}},
        {"type": "feature", "slots": {"title": "One click exports", "line": "PDF, Sheets or Slides from any view", "device": "browser", "callout": "Export", "focus_x": 0.8, "focus_y": 0.2}},
        {"type": "feature", "slots": {"title": "Live dashboards", "line": "Numbers update while you watch", "device": "browser", "callout": "Live", "focus_x": 0.3, "focus_y": 0.55}},
        {"type": "recap", "slots": {"benefits": [{"text": "Set up in minutes"}, {"text": "Works with your data"}, {"text": "Free for small teams"}]}},
        {"type": "end_card", "slots": {"headline": "Try Ledgerly today", "cta": "Start free", "url": "ledgerly.app"}},
    ),
    default_style="soft_gradient", music_mood="uplifting",
))

_reg(Template(
    id="product_explainer", name="Product Explainer", category="promo",
    description="SaaS or API explainer: the problem struck out, a hub diagram, an app window with switches, "
                "a code card that types itself, an endpoint list and a count with a tag marquee.",
    aspects=ASPECTS, default_aspect="9:16", length=(15, 90),
    scene_types=(
        SceneType("hook", "Hook", (T("text", "text", "Hook", required=True, max_chars=60, max_words=9),
                                   T("kicker", "text", "Kicker", max_chars=30)),
                  default_seconds=2.6, min_seconds=1.8),
        SceneType("problem", "Problem (struck out)", (
            T("title", "text", "Title", required=True, max_chars=40, max_words=6),
            T("items", "items", "Pain points", max_items=5,
              item_fields=(T("text", "text", "Pain point", required=True, max_chars=36),))),
            min_count=0, default_seconds=4.0, min_seconds=3.0),
        SceneType("hub", "Hub diagram", (
            T("title", "text", "Title", required=True, max_chars=40, max_words=6),
            T("line", "text", "One line", max_chars=80, max_words=14),
            T("center", "text", "Centre", required=True, max_chars=20),
            T("nodes", "items", "Connected things", max_items=8,
              item_fields=(T("text", "text", "Name", required=True, max_chars=20),))),
            min_count=0, max_count=2, default_seconds=4.5, min_seconds=3.5),
        SceneType("app", "App window (switches)", (
            T("title", "text", "Title", required=True, max_chars=40, max_words=6),
            T("line", "text", "One line", max_chars=80, max_words=14),
            T("window", "text", "Window path", max_chars=40, help="Shown in the title bar, like app.example.com/settings"),
            T("rows", "items", "Settings", max_items=6,
              item_fields=(T("label", "text", "Setting", required=True, max_chars=32),
                           T("on", "bool", "Switches on")))),
            min_count=0, max_count=3, default_seconds=4.5, min_seconds=3.5),
        SceneType("code", "Code card", (
            T("title", "text", "Title", required=True, max_chars=40, max_words=6),
            T("line", "text", "One line", max_chars=80, max_words=14),
            T("filename", "text", "File name", max_chars=40),
            T("code", "longtext", "Code", required=True, max_chars=700, help="Up to 12 lines; it types itself in.")),
            min_count=0, max_count=3, default_seconds=5.0, min_seconds=3.5),
        SceneType("api", "Endpoint list", (
            T("title", "text", "Title", required=True, max_chars=40, max_words=6),
            T("line", "text", "One line", max_chars=80, max_words=14),
            T("host", "text", "Host", max_chars=40),
            T("endpoints", "items", "Endpoints", max_items=6,
              item_fields=(T("method", "choice", "Method", choices=("GET", "POST", "PUT", "PATCH", "DELETE", "WS")),
                           T("path", "text", "Path", required=True, max_chars=40),
                           T("note", "text", "Note", max_chars=24))),
            T("highlight", "number", "Highlight row (1 to 6, 0 for none)", min=0, max=6)),
            min_count=0, max_count=2, default_seconds=4.5, min_seconds=3.5),
        SceneType("counter", "Counter and marquee", (
            T("value", "number", "Number", required=True),
            T("prefix", "text", "Prefix", max_chars=4), T("suffix", "text", "Suffix", max_chars=6),
            T("label", "text", "Label", required=True, max_chars=60, max_words=10),
            T("tags", "items", "Scrolling tags", max_items=16,
              item_fields=(T("text", "text", "Tag", required=True, max_chars=24),))),
            min_count=0, default_seconds=4.0, min_seconds=3.0),
    ),
    default_scenes=(
        {"type": "hook", "slots": {"text": "Take payments in one afternoon", "kicker": "Introducing Relay"}},
        {"type": "problem", "slots": {"title": "The old way", "items": [
            {"text": "Six separate integrations"}, {"text": "Six dashboards to check"},
            {"text": "Reconciling by hand"}, {"text": "Weeks of setup"}]}},
        {"type": "hub", "slots": {"title": "One connection", "line": "Every payment method through a single API",
                                  "center": "Relay", "nodes": [
                                      {"text": "UPI"}, {"text": "Cards"}, {"text": "Net banking"}, {"text": "Wallets"},
                                      {"text": "Payouts"}, {"text": "Refunds"}]}},
        {"type": "app", "slots": {"title": "Switch on what you need", "window": "relay.app/settings", "rows": [
            {"label": "UPI collect", "on": True}, {"label": "Card payments", "on": True},
            {"label": "Instant payouts", "on": True}, {"label": "Auto refunds", "on": False}]}},
        {"type": "code", "slots": {"title": "Three lines to go live", "filename": "checkout.py",
                                   "code": "from relay import Relay\n\nclient = Relay(api_key=\"rk_live_...\")\n"
                                           "client.payments.create(amount=4999, currency=\"INR\")"}},
        {"type": "api", "slots": {"title": "Every action is an endpoint", "host": "api.relay.dev", "highlight": 1,
                                  "endpoints": [
                                      {"method": "POST", "path": "/v1/payments", "note": "Collect"},
                                      {"method": "GET", "path": "/v1/payments/{id}", "note": "Status"},
                                      {"method": "POST", "path": "/v1/payouts", "note": "Pay out"},
                                      {"method": "POST", "path": "/v1/refunds", "note": "Refund"},
                                      {"method": "WS", "path": "/v1/events", "note": "Live events"}]}},
        {"type": "counter", "slots": {"value": 1200, "suffix": "+", "label": "teams already ship on Relay", "tags": [
            {"text": "Marketplaces"}, {"text": "SaaS"}, {"text": "D2C brands"}, {"text": "Edtech"},
            {"text": "Logistics"}, {"text": "Travel"}, {"text": "Healthcare"}, {"text": "Gaming"}]}},
        {"type": "end_card", "slots": {"headline": "Start building with Relay", "cta": "Get API keys",
                                       "url": "relay.dev"}},
    ),
    default_style="dark_tech", music_mood="uplifting",
))

_reg(Template(
    id="chart_story", name="Chart Story", category="data",
    description="Question, an animated line, bar or donut chart with a highlighted point and annotation, takeaway.",
    aspects=ASPECTS, default_aspect="9:16", length=(10, 45),
    scene_types=(
        SceneType("question", "Question", (T("text", "text", "Question", required=True, max_chars=70, max_words=10),),
                  default_seconds=2.2, min_seconds=1.6),
        SceneType("chart", "Chart", (
            T("title", "text", "Chart title", max_chars=60),
            T("chart", "choice", "Chart type", choices=("auto", "line", "bar", "donut")),
            T("highlight", "text", "Highlight (series or label)", max_chars=40),
            T("annotation", "text", "Annotation", max_chars=60),
            T("annotation_at", "text", "Annotate at label", max_chars=30)),
            default_seconds=6.5, min_seconds=4.0),
        SceneType("takeaway", "Takeaway", (T("text", "text", "Takeaway", required=True, max_chars=80, max_words=12),),
                  min_count=0, default_seconds=2.8),
    ),
    default_scenes=(
        {"type": "question", "slots": {"text": "How fast did solar get cheap?"}},
        {"type": "chart", "slots": {"title": "Solar module price, USD per watt", "chart": "line", "annotation": "90% cheaper in a decade", "annotation_at": "2020"}},
        {"type": "takeaway", "slots": {"text": "Cheaper than coal in most of the world"}},
    ),
    data_kind="series", requires_source=True, default_style="editorial_serif", music_mood="documentary",
    sample_data="Year,Price\n2010,2.02\n2012,0.85\n2014,0.72\n2016,0.48\n2018,0.32\n2020,0.20\n2022,0.27\n2024,0.11\n",
))

_reg(Template(
    id="market_recap", name="Market Recap", category="finance",
    description="Daily markets in 30 seconds: date stamp, index tiles with counters, movers, sparkline, what to watch, disclaimer.",
    aspects=("9:16", "1:1", "4:5", "16:9"), default_aspect="9:16", length=(15, 60),
    scene_types=(
        SceneType("date", "Date stamp", (
            T("date", "text", "Date", required=True, max_chars=30),
            T("headline", "text", "Headline", required=True, max_chars=60, max_words=9)),
            default_seconds=2.4, min_seconds=2.0),
        SceneType("tiles", "Index tiles", (T("heading", "text", "Heading", max_chars=40),),
                  default_seconds=4.2, min_seconds=3.0),
        SceneType("movers", "Gainers and losers", (T("heading", "text", "Heading", max_chars=40),),
                  min_count=0, default_seconds=3.8, min_seconds=3.0),
        SceneType("spark", "Featured chart", (
            T("name", "text", "Featured index", max_chars=30),
            T("caption", "text", "Caption", max_chars=60)), min_count=0, default_seconds=3.4),
        SceneType("watch", "What to watch", (
            T("items", "items", "Items", max_items=3,
              item_fields=(T("text", "text", "Item", required=True, max_chars=60),)),),
            min_count=0, default_seconds=3.4),
    ),
    default_scenes=(
        {"type": "date", "slots": {"date": "Monday, 26 October", "headline": "Tech lifts indices to a record close"}},
        {"type": "tiles", "slots": {"heading": "Indices"}},
        {"type": "movers", "slots": {"heading": "Top movers"}},
        {"type": "watch", "slots": {"items": [{"text": "Central bank minutes on Wednesday"}, {"text": "Quarterly results from the big banks"}]}},
    ),
    data_kind="tickers", requires_source=True, requires_disclaimer=True, default_style="newsprint",
    music_mood="documentary",
    sample_data=("Name,Value,Change %,D1,D2,D3,D4,D5\nNifty 50,24854.05,0.82,24410,24560,24502,24650,24854\n"
                 "Sensex,81224.75,0.79,80110,80460,80390,80850,81224\nNasdaq,18489.55,1.12,18010,18120,18290,18270,18489\n"
                 "S&P 500,5864.67,0.40,5790,5815,5808,5841,5864\nGold,2734.20,-0.35,2741,2749,2752,2744,2734\n"
                 "Brent,74.38,-1.42,76.1,75.8,75.2,75.4,74.38\n"),
))

_reg(Template(
    id="timeline", name="Timeline", category="story",
    description="Milestones on a track larger than the frame; the camera travels date to date while the line draws ahead.",
    aspects=("16:9", "9:16", "1:1", "4:5"), default_aspect="16:9", length=(15, 120),
    scene_types=(
        SceneType("title", "Title", (T("title", "text", "Title", required=True, max_chars=50, max_words=8),
                                     T("subtitle", "text", "Subtitle", max_chars=70)),
                  default_seconds=2.5, min_seconds=2.0),
        SceneType("track", "Milestones", (
            T("items", "items", "Milestones", required=True, max_items=12,
              item_fields=(T("date", "text", "Date", required=True, max_chars=14),
                           T("title", "text", "Title", required=True, max_chars=40),
                           T("desc", "text", "Description", max_chars=90),
                           T("image", "image", "Image"))),),
            default_seconds=16.0, min_seconds=6.0),
    ),
    default_scenes=(
        {"type": "title", "slots": {"title": "How the smartphone happened", "subtitle": "Five turning points"}},
        {"type": "track", "slots": {"items": [
            {"date": "1973", "title": "First handheld call", "desc": "A two pound prototype on a New York street"},
            {"date": "1994", "title": "The first smartphone", "desc": "Touchscreen, email and a stylus"},
            {"date": "2007", "title": "Multi-touch", "desc": "The phone becomes a pocket computer"},
            {"date": "2008", "title": "App stores", "desc": "Software becomes a marketplace"},
            {"date": "2024", "title": "On-device AI", "desc": "Assistants run on the phone itself"}]}},
    ),
    default_style="editorial_serif", music_mood="documentary",
))

_reg(Template(
    id="audiogram", name="Audiogram", category="audio",
    description="Podcast or voice clip: cover art, a live waveform from the audio and word-by-word captions.",
    aspects=("9:16", "1:1", "4:5"), default_aspect="9:16", length=(8, 120),
    scene_types=(
        SceneType("cover", "Cover", (
            T("show", "text", "Show name", required=True, max_chars=40),
            T("episode", "text", "Episode title", max_chars=70),
            T("guest", "text", "Guest", max_chars=40),
            T("art", "image", "Cover art")), default_seconds=2.2, min_seconds=1.5, voiceover=False),
        SceneType("clip", "Clip", (
            T("script", "longtext", "Script (spoken by the AI voice)", max_chars=2500,
              help="Leave empty when you upload an audio file"),
            T("transcript", "longtext", "Transcript of the uploaded audio (for captions)", max_chars=4000),
            T("audio", "image", "Audio upload")),
            default_seconds=15.0, min_seconds=4.0, voiceover=False),
    ),
    default_scenes=(
        {"type": "cover", "slots": {"show": "The Long Game", "episode": "Why small teams win", "guest": "with Priya Raman"}},
        {"type": "clip", "slots": {"script": "Small teams win because every person can hold the whole problem in their head. The moment you need a meeting to explain the plan, you have already lost a week."}},
        {"type": "end_card", "slots": {"headline": "Full episode on every podcast app", "cta": "Listen now", "url": "thelonggame.fm"}},
    ),
    default_style="soft_gradient", music_mood="none", captions_default=False,
))

TEMPLATE_IDS = tuple(TEMPLATES)


# ---------------------------------------------------------------------------
# The spec model
# ---------------------------------------------------------------------------

class _M(BaseModel):
    model_config = ConfigDict(extra="ignore")


# Hard bounds on untrusted spec content (client saves, previews, LLM drafts).
# The per-slot limits in the catalog are reported by validate(); these only
# keep a hostile spec from costing CPU, memory or disk in previews and renders.
MAX_SLOT_STR = 4000
MAX_SLOT_KEYS = 24
MAX_SLOT_LIST = 40
MAX_SLOT_DEPTH = 3
MAX_ABS_NUMBER = 1e15
MAX_DATA_ROWS = 400
MAX_DATA_COLS = 40
MAX_DATA_CELL = 120


def finite_number(v: Any) -> Optional[float]:
    """A float within +/- MAX_ABS_NUMBER, or None (NaN, inf, 1e308, text)."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(f) or abs(f) > MAX_ABS_NUMBER:
        return None
    return f


def _clean_slot_value(v: Any, depth: int = 0) -> Any:
    """JSON scalars, short strings, small lists and dicts; anything else is
    dropped (None). Never raises."""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return finite_number(v) if isinstance(v, float) else (v if abs(v) <= MAX_ABS_NUMBER else None)
    if isinstance(v, str):
        return v[:MAX_SLOT_STR]
    if depth >= MAX_SLOT_DEPTH:
        return None
    if isinstance(v, list):
        return [_clean_slot_value(x, depth + 1) for x in v[:MAX_SLOT_LIST]]
    if isinstance(v, dict):
        out = {}
        for k, x in list(v.items())[:MAX_SLOT_KEYS]:
            if isinstance(k, str) and len(k) <= 40:
                out[k] = _clean_slot_value(x, depth + 1)
        return out
    return None


def _clean_cell(v: Any) -> str:
    if v is None or isinstance(v, (bool, list, dict)):
        return ""
    if isinstance(v, (int, float)):
        f = finite_number(v)
        return "" if f is None else (str(int(f)) if f == int(f) and abs(f) < 1e15 else repr(f))[:MAX_DATA_CELL]
    return str(v).strip()[:MAX_DATA_CELL]


class Scene(_M):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], max_length=24)
    type: str = Field(max_length=30)
    slots: dict[str, Any] = Field(default_factory=dict)
    duration: Optional[float] = Field(default=None, ge=0.5, le=600)
    voiceover: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("slots", mode="before")
    @classmethod
    def _bound_slots(cls, v):
        if not isinstance(v, dict):
            return {}
        return _clean_slot_value(v, 0) or {}

    @field_validator("duration", mode="before")
    @classmethod
    def _finite_duration(cls, v):
        if v is None or v == "":
            return None
        f = finite_number(v)
        return None if f is None else f


class DataTable(_M):
    columns: list[str] = Field(default_factory=list, max_length=MAX_DATA_COLS)
    rows: list[list[Any]] = Field(default_factory=list, max_length=MAX_DATA_ROWS)

    @model_validator(mode="before")
    @classmethod
    def _rectangular(cls, v):
        """Cells become short strings and every row has one cell per column, so
        the data views never index past a row or call str methods on numbers."""
        if not isinstance(v, dict):
            return {"columns": [], "rows": []}
        cols = v.get("columns") if isinstance(v.get("columns"), list) else []
        rows = [r for r in (v.get("rows") if isinstance(v.get("rows"), list) else [])[:MAX_DATA_ROWS]
                if isinstance(r, list)]
        cols = [_clean_cell(c) for c in cols[:MAX_DATA_COLS]]
        width = len(cols) or min(MAX_DATA_COLS, max((len(r) for r in rows), default=0))
        cols = (cols + [f"Column {i + 1}" for i in range(len(cols), width)])[:width]
        cols = [c or f"Column {i + 1}" for i, c in enumerate(cols)]
        rows = [([_clean_cell(c) for c in r[:width]] + [""] * width)[:width] for r in rows]
        return {"columns": cols, "rows": rows}


class DataOptions(_M):
    top_n: Optional[int] = Field(default=None, ge=3, le=15)
    period_seconds: Optional[float] = Field(default=None, ge=0.3, le=4.0)
    chart: Optional[Literal["auto", "line", "bar", "donut"]] = None
    highlight: Optional[str] = Field(default=None, max_length=60)
    prefix: Optional[str] = Field(default=None, max_length=6)
    suffix: Optional[str] = Field(default=None, max_length=12)
    decimals: Optional[int] = Field(default=None, ge=0, le=4)
    compact: Optional[bool] = None


class PaidPartnership(_M):
    enabled: bool = False
    brand: Optional[str] = Field(default=None, max_length=60)


class Series(_M):
    """A reel series: a header on every frame ("NAME . PART 2 OF 6" with
    pips) and the next part number on the next_part card."""
    enabled: bool = False
    name: str = Field(default="", max_length=40)
    part: int = Field(default=1, ge=1, le=30)
    total: int = Field(default=3, ge=1, le=30)


class Options(_M):
    loop: bool = False
    captions: Optional[bool] = None  # None: template default (on with a voiceover)
    safe_zone: str = Field(default="organic", max_length=40)
    intensity: Optional[Literal["calm", "standard", "punchy"]] = None
    sfx: bool = True
    beat_sync: bool = True
    logo_bug: bool = False
    paid_partnership: PaidPartnership = Field(default_factory=PaidPartnership)
    ai_label: bool = False
    # Close pauses inside a scene's narration to about 0.3 s (build.tighten).
    tight_pauses: bool = True
    series: Series = Field(default_factory=Series)
    # A thin bar under the header that fills as the video plays.
    progress_bar: bool = False


class Pronunciation(_M):
    """How the voice says a word that is written differently on screen:
    written "API", spoken "A P I". Captions and kinetic text keep the
    written form. A row with either side blank is kept (the editor adds rows
    empty) and ignored by build._rules."""

    written: str = Field(default="", max_length=40)
    spoken: str = Field(default="", max_length=80)


class CTA(_M):
    text: Optional[str] = Field(default=None, max_length=40)
    url: Optional[str] = Field(default=None, max_length=80)


class Spec(_M):
    template_id: str
    style_id: str = DEFAULT_STYLE
    title: str = Field(default="Untitled", max_length=120)
    seed: int = Field(default_factory=lambda: random.randint(1, 2**31 - 1))
    scenes: list[Scene] = Field(default_factory=list, max_length=24)
    data: Optional[DataTable] = None
    data_options: DataOptions = Field(default_factory=DataOptions)
    source: Optional[str] = Field(default=None, max_length=160)
    disclaimer: Optional[str] = Field(default=None, max_length=400)
    options: Options = Field(default_factory=Options)
    pronunciations: list[Pronunciation] = Field(default_factory=list, max_length=30)

    @field_validator("seed", mode="before")
    @classmethod
    def _bound_seed(cls, v):
        f = finite_number(v)
        return random.randint(1, 2**31 - 1) if f is None else int(abs(f)) % (2**31 - 1) or 1


def default_spec(template_id: str, *, style_id: Optional[str] = None, seed: Optional[int] = None,
                 with_sample_data: bool = True) -> Spec:
    tpl = TEMPLATES[template_id]
    from .data import parse_csv

    data = None
    if with_sample_data and tpl.sample_data:
        data = DataTable(**parse_csv(tpl.sample_data))
    spec = Spec(
        template_id=template_id, style_id=style_id or tpl.default_style, title=tpl.name,
        scenes=[Scene(type=s["type"], slots=dict(s.get("slots") or {})) for s in tpl.default_scenes],
        data=data, source=("Sample data for illustration" if tpl.requires_source else None),
        **({"seed": seed} if seed else {}),
    )
    return normalize(spec)


def normalize(spec: Spec) -> Spec:
    """Add the non-removable compliance scenes and keep shared scenes last."""
    tpl = TEMPLATES.get(spec.template_id)
    if tpl is None:
        return spec
    if spec.style_id not in STYLE_IDS:
        spec.style_id = tpl.default_style
    if spec.options.safe_zone not in SAFE_ZONE_PRESETS:
        spec.options.safe_zone = "organic"
    scenes = [s for s in spec.scenes if tpl.scene_type(s.type) is not None]
    types = [s.type for s in scenes]
    if tpl.requires_source and "source_card" not in types:
        scenes.append(Scene(type="source_card", slots={}))
    if tpl.requires_disclaimer and "disclaimer" not in types:
        scenes.append(Scene(type="disclaimer", slots={}))
    if tpl.requires_disclaimer and not (spec.disclaimer or "").strip():
        spec.disclaimer = DEFAULT_FINANCE_DISCLAIMER
    # Order: template scenes, then source card, disclaimer, end card, logo sting at the end.
    order = {"source_card": 1, "disclaimer": 2, "end_card": 3}
    intro = scenes[0] if scenes and scenes[0].type == "logo_sting" else None
    body = [s for s in scenes if s.type not in order and s.type != "logo_sting"]
    tail = sorted([s for s in scenes if s.type in order], key=lambda s: order[s.type])
    outro = [s for s in scenes if s.type == "logo_sting" and s is not intro][:1]
    spec.scenes = ([intro] if intro else []) + body + tail + outro
    seen = set()
    for s in spec.scenes:
        if s.id in seen or not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", s.id or ""):
            s.id = uuid.uuid4().hex[:8]
        seen.add(s.id)
    return spec


def clamp_numbers(spec: Spec) -> Spec:
    """Number slots as finite floats inside their catalog range (in place).

    validate() reports out-of-range numbers to the user, but previews draw
    unsaved, unvalidated specs, so the builders only ever see bounded values
    (a "decimals" of 1e9 would otherwise format a gigabyte string)."""
    tpl = TEMPLATES.get(spec.template_id)
    if tpl is None:
        return spec
    for sc in spec.scenes:
        st = tpl.scene_type(sc.type)
        if st is None:
            continue
        for slot in st.slots:
            if slot.kind != "number" or slot.key not in sc.slots:
                continue
            v = sc.slots.get(slot.key)
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            f = finite_number(v)
            if f is not None:
                if slot.min is not None:
                    f = max(float(slot.min), f)
                if slot.max is not None:
                    f = min(float(slot.max), f)
            sc.slots[slot.key] = f
    return spec


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _words(s: str) -> int:
    return len((s or "").split())


def validate(spec: Spec, *, aspect: Optional[str] = None) -> dict:
    """{ok, errors: [{scene_id, slot, message}], warnings: [...], data: view}."""
    from .data import validate_table

    errors: list[dict] = []
    warnings: list[dict] = []
    tpl = TEMPLATES.get(spec.template_id)
    if tpl is None:
        return {"ok": False, "errors": [{"message": "Unknown template."}], "warnings": []}
    if aspect and aspect not in tpl.aspects:
        errors.append({"message": f"{tpl.name} does not support {aspect}."})
    counts: dict[str, int] = {}
    for sc in spec.scenes:
        st = tpl.scene_type(sc.type)
        if st is None:
            errors.append({"scene_id": sc.id, "message": f"Unknown scene type '{sc.type}'."})
            continue
        counts[sc.type] = counts.get(sc.type, 0) + 1
        for slot in st.slots:
            v = sc.slots.get(slot.key)
            empty = v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v)
            if slot.required and empty:
                errors.append({"scene_id": sc.id, "slot": slot.key, "message": f"{st.label}: {slot.label} is required."})
                continue
            if empty:
                continue
            if slot.kind in ("text", "longtext"):
                s = str(v)
                if slot.max_chars and len(s) > slot.max_chars:
                    errors.append({"scene_id": sc.id, "slot": slot.key,
                                   "message": f"{st.label}: {slot.label} is {len(s)} characters; the limit is {slot.max_chars}."})
                if slot.max_words and _words(s) > slot.max_words:
                    warnings.append({"scene_id": sc.id, "slot": slot.key,
                                     "message": f"{st.label}: {slot.label} has {_words(s)} words; {slot.max_words} or fewer reads best."})
            elif slot.kind == "number":
                f = finite_number(v)
                if f is None:
                    errors.append({"scene_id": sc.id, "slot": slot.key,
                                   "message": f"{st.label}: {slot.label} must be a number (at most 1e15)."})
                    continue
                if slot.min is not None and f < slot.min or slot.max is not None and f > slot.max:
                    errors.append({"scene_id": sc.id, "slot": slot.key,
                                   "message": f"{st.label}: {slot.label} must be between {slot.min:g} and {slot.max:g}."})
            elif slot.kind == "items":
                if not isinstance(v, list):
                    errors.append({"scene_id": sc.id, "slot": slot.key, "message": f"{st.label}: {slot.label} must be a list."})
                    continue
                if slot.max_items and len(v) > slot.max_items:
                    errors.append({"scene_id": sc.id, "slot": slot.key,
                                   "message": f"{st.label}: at most {slot.max_items} {slot.label.lower()}."})
                for i, item in enumerate(v):
                    if not isinstance(item, dict):
                        errors.append({"scene_id": sc.id, "slot": slot.key, "message": f"{slot.label} {i + 1} is invalid."})
                        continue
                    for f in slot.item_fields:
                        iv = item.get(f.key)
                        if f.required and (iv is None or not str(iv).strip()):
                            errors.append({"scene_id": sc.id, "slot": slot.key,
                                           "message": f"{slot.label} {i + 1}: {f.label} is required."})
                        elif iv is not None and f.max_chars and len(str(iv)) > f.max_chars:
                            errors.append({"scene_id": sc.id, "slot": slot.key,
                                           "message": f"{slot.label} {i + 1}: {f.label} is over {f.max_chars} characters."})
            elif slot.kind == "choice" and slot.choices and str(v) not in slot.choices:
                errors.append({"scene_id": sc.id, "slot": slot.key,
                               "message": f"{st.label}: {slot.label} must be one of {', '.join(slot.choices)}."})
        if sc.voiceover and len(sc.voiceover) > 600:
            warnings.append({"scene_id": sc.id, "message": f"{st.label}: the voiceover is long for one scene."})
    for st in tpl.scene_types:
        n = counts.get(st.type, 0)
        if n < st.min_count:
            errors.append({"message": f"{tpl.name} needs at least {st.min_count} '{st.label}' scene(s)."})
        if n > st.max_count:
            errors.append({"message": f"{tpl.name} allows at most {st.max_count} '{st.label}' scene(s)."})
    if tpl.requires_source and not (spec.source or "").strip():
        errors.append({"slot": "source", "message": "A source is required for data videos (shown on the source card)."})
    if tpl.requires_disclaimer and len((spec.disclaimer or "").strip()) < 20:
        errors.append({"slot": "disclaimer", "message": "A finance disclaimer is required for a market recap."})
    if (spec.options.paid_partnership.enabled and not (spec.options.paid_partnership.brand or "").strip()):
        errors.append({"slot": "paid_partnership", "message": "Name the brand for the paid partnership label."})
    data_view = None
    if tpl.data_kind:
        table = spec.data.model_dump() if spec.data else None
        if tpl.data_kind == "versus" and (not table or not table.get("rows")):
            data_view = {"ok": True, "problems": [], "warnings": [], "from": "scenes"}
        else:
            data_view = validate_table(tpl.data_kind, table, **({"top_n": spec.data_options.top_n or 10}
                                                                  if tpl.data_kind == "race" else {}))
            for p in data_view.get("problems", []):
                errors.append({"slot": "data", "message": p})
            for w in data_view.get("warnings", []):
                warnings.append({"slot": "data", "message": w})
    return {"ok": not errors, "errors": errors, "warnings": warnings, "data": data_view}


def catalog() -> list[dict]:
    return [t.view() for t in TEMPLATES.values()]
