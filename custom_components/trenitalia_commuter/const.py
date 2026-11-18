"""Constants for the Trenitalia Commuter integration."""

from __future__ import annotations

from zoneinfo import ZoneInfo

DOMAIN = "trenitalia_commuter"
ROME_TZ = ZoneInfo("Europe/Rome")

LEFRECCE_BASE_URL = "https://www.lefrecce.it/Channels.Website.BFF.WEB/website"
VIAGGIATRENO_BASE_URL = (
    "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno"
)
VIAGGIATRENO_USER_AGENT = "Mozilla/5.0"

DEFAULT_PAST_WINDOW_MINUTES = 45
DEFAULT_SOLUTIONS_LIMIT = 15
DEFAULT_MAX_TRAINS = 8
DEFAULT_DELAY_THRESHOLD_MINUTES = 5
DEFAULT_LEFRECCE_SCAN_INTERVAL_MINUTES = 20
DEFAULT_VT_SCAN_INTERVAL_MINUTES = 2
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15

CONF_ORIGIN_LF_ID = "origin_lefrecce_id"
CONF_ORIGIN_LF_NAME = "origin_lefrecce_name"
CONF_ORIGIN_VT_ID = "origin_vt_id"
CONF_ORIGIN_VT_NAME = "origin_vt_name"

CONF_DEST_LF_ID = "dest_lefrecce_id"
CONF_DEST_LF_NAME = "dest_lefrecce_name"
CONF_DEST_VT_ID = "dest_vt_id"
CONF_DEST_VT_NAME = "dest_vt_name"

CONF_NO_CHANGES = "no_changes"
CONF_REGIONAL_ONLY = "regional_only"
CONF_MAX_TRAINS = "max_trains"
CONF_DELAY_THRESHOLD = "delay_threshold"
CONF_LEFRECCE_INTERVAL = "lefrecce_interval"
CONF_VT_INTERVAL = "vt_interval"
CONF_PAST_WINDOW = "past_window"