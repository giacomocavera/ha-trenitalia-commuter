"""Config flow for Trenitalia Commuter."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api.exceptions import LeFrecceApiError, ViaggiaTrenoApiError
from .api.lefrecce import LeFrecceClient
from .api.viaggiatreno import ViaggiaTrenoClient
from .const import (
    CONF_DELAY_THRESHOLD,
    CONF_DEST_LF_ID,
    CONF_DEST_LF_NAME,
    CONF_DEST_VT_ID,
    CONF_DEST_VT_NAME,
    CONF_LEFRECCE_INTERVAL,
    CONF_MAX_TRAINS,
    CONF_NO_CHANGES,
    CONF_ORIGIN_LF_ID,
    CONF_ORIGIN_LF_NAME,
    CONF_ORIGIN_VT_ID,
    CONF_ORIGIN_VT_NAME,
    CONF_PAST_WINDOW,
    CONF_REGIONAL_ONLY,
    CONF_VT_INTERVAL,
    DEFAULT_DELAY_THRESHOLD_MINUTES,
    DEFAULT_LEFRECCE_SCAN_INTERVAL_MINUTES,
    DEFAULT_MAX_TRAINS,
    DEFAULT_PAST_WINDOW_MINUTES,
    DEFAULT_VT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .matcher import resolve_viaggiatreno_station
from .models import LeFrecceStation, ViaggiaTrenoStation


class TrenitaliaCommuterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Trenitalia Commuter."""

    VERSION = 1

    def __init__(self) -> None:
        self._origin_results: list[LeFrecceStation] = []
        self._dest_results: list[LeFrecceStation] = []
        self._origin_lf: LeFrecceStation | None = None
        self._dest_lf: LeFrecceStation | None = None
        self._origin_vt: ViaggiaTrenoStation | None = None
        self._origin_vt_candidates: list[ViaggiaTrenoStation] = []
        self._dest_vt: ViaggiaTrenoStation | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return TrenitaliaCommuterOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Search origin station."""
        errors: dict[str, str] = {}
        if user_input is not None:
            query = str(user_input["origin_query"]).strip()
            session = async_get_clientsession(self.hass)
            lf_client = LeFrecceClient(session)
            try:
                results = await lf_client.search_stations(query)
            except LeFrecceApiError:
                errors["base"] = "cannot_connect"
            else:
                if not results:
                    errors["origin_query"] = "no_stations_found"
                else:
                    self._origin_results = results
                    return await self.async_step_origin_select()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("origin_query"): selector.TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_origin_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Select origin station and match ViaggiaTreno ID."""
        errors: dict[str, str] = {}
        if user_input is not None:
            selected_id = int(user_input["origin_station"])
            self._origin_lf = next(
                st for st in self._origin_results if st.id == selected_id
            )
            session = async_get_clientsession(self.hass)
            vt_client = ViaggiaTrenoClient(session)
            try:
                match = await resolve_viaggiatreno_station(
                    vt_client, self._origin_lf
                )
            except ViaggiaTrenoApiError:
                errors["base"] = "cannot_connect"
            else:
                self._origin_vt_candidates = match.candidates
                if match.confident and match.matched is not None:
                    self._origin_vt = match.matched
                    return await self.async_step_dest_search()
                return await self.async_step_origin_vt_disambiguate()

        options = [
            selector.SelectOptionDict(
                value=str(st.id), label=f"{st.display_name} ({st.id})"
            )
            for st in self._origin_results
        ]
        return self.async_show_form(
            step_id="origin_select",
            data_schema=vol.Schema(
                {
                    vol.Required("origin_station"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_origin_vt_disambiguate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b: Manual confirmation/disambiguation of ViaggiaTreno origin ID."""
        errors: dict[str, str] = {}
        if user_input is not None:
            manual_id = str(user_input.get("manual_vt_id") or "").strip().upper()
            selected_id = str(user_input.get("vt_station") or "").strip().upper()
            chosen_id = manual_id or selected_id

            if not chosen_id or not chosen_id.startswith("S"):
                errors["base"] = "invalid_vt_id"
            else:
                matched = next(
                    (c for c in self._origin_vt_candidates if c.vt_id == chosen_id),
                    None,
                )
                self._origin_vt = matched or ViaggiaTrenoStation(
                    name=self._origin_lf.name if self._origin_lf else chosen_id,
                    vt_id=chosen_id,
                )
                return await self.async_step_dest_search()

        schema_dict: dict[Any, Any] = {}
        if self._origin_vt_candidates:
            vt_options = [
                selector.SelectOptionDict(
                    value=c.vt_id, label=f"{c.name} ({c.vt_id})"
                )
                for c in self._origin_vt_candidates
            ]
            schema_dict[vol.Optional("vt_station")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=vt_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        schema_dict[vol.Optional("manual_vt_id", default="")] = selector.TextSelector()

        return self.async_show_form(
            step_id="origin_vt_disambiguate",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "station": self._origin_lf.name if self._origin_lf else ""
            },
        )

    async def async_step_dest_search(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Search destination station."""
        errors: dict[str, str] = {}
        if user_input is not None:
            query = str(user_input["dest_query"]).strip()
            session = async_get_clientsession(self.hass)
            lf_client = LeFrecceClient(session)
            try:
                results = await lf_client.search_stations(query)
            except LeFrecceApiError:
                errors["base"] = "cannot_connect"
            else:
                if not results:
                    errors["dest_query"] = "no_stations_found"
                else:
                    self._dest_results = results
                    return await self.async_step_dest_select()

        return self.async_show_form(
            step_id="dest_search",
            data_schema=vol.Schema(
                {vol.Required("dest_query"): selector.TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_dest_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: Select destination station and resolve VT ID best-effort."""
        errors: dict[str, str] = {}
        if user_input is not None:
            selected_id = int(user_input["dest_station"])
            if self._origin_lf and selected_id == self._origin_lf.id:
                errors["dest_station"] = "same_station"
            else:
                self._dest_lf = next(
                    st for st in self._dest_results if st.id == selected_id
                )
                session = async_get_clientsession(self.hass)
                vt_client = ViaggiaTrenoClient(session)
                try:
                    match = await resolve_viaggiatreno_station(
                        vt_client, self._dest_lf
                    )
                    if match.confident and match.matched is not None:
                        self._dest_vt = match.matched
                except ViaggiaTrenoApiError:
                    self._dest_vt = None
                return await self.async_step_route_options()

        options = [
            selector.SelectOptionDict(
                value=str(st.id), label=f"{st.display_name} ({st.id})"
            )
            for st in self._dest_results
        ]
        return self.async_show_form(
            step_id="dest_select",
            data_schema=vol.Schema(
                {
                    vol.Required("dest_station"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_route_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 5: Route preferences and entry creation."""
        assert self._origin_lf is not None
        assert self._origin_vt is not None
        assert self._dest_lf is not None

        default_title = f"{self._origin_lf.name} -> {self._dest_lf.name}"

        if user_input is not None:
            no_changes = bool(user_input[CONF_NO_CHANGES])
            regional_only = bool(user_input[CONF_REGIONAL_ONLY])
            unique_id = (
                f"{self._origin_lf.id}_{self._dest_lf.id}_"
                f"{int(no_changes)}_{int(regional_only)}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            title = str(user_input.get("name") or default_title).strip()
            data = {
                CONF_ORIGIN_LF_ID: self._origin_lf.id,
                CONF_ORIGIN_LF_NAME: self._origin_lf.name,
                CONF_ORIGIN_VT_ID: self._origin_vt.vt_id,
                CONF_ORIGIN_VT_NAME: self._origin_vt.name,
                CONF_DEST_LF_ID: self._dest_lf.id,
                CONF_DEST_LF_NAME: self._dest_lf.name,
                CONF_DEST_VT_ID: self._dest_vt.vt_id if self._dest_vt else None,
                CONF_DEST_VT_NAME: self._dest_vt.name if self._dest_vt else None,
            }
            options = {
                CONF_NO_CHANGES: no_changes,
                CONF_REGIONAL_ONLY: regional_only,
                CONF_MAX_TRAINS: int(user_input[CONF_MAX_TRAINS]),
                CONF_DELAY_THRESHOLD: int(user_input[CONF_DELAY_THRESHOLD]),
                CONF_LEFRECCE_INTERVAL: DEFAULT_LEFRECCE_SCAN_INTERVAL_MINUTES,
                CONF_VT_INTERVAL: DEFAULT_VT_SCAN_INTERVAL_MINUTES,
                CONF_PAST_WINDOW: DEFAULT_PAST_WINDOW_MINUTES,
            }
            return self.async_create_entry(title=title, data=data, options=options)

        return self.async_show_form(
            step_id="route_options",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=default_title): selector.TextSelector(),
                    vol.Required(CONF_NO_CHANGES, default=True): selector.BooleanSelector(),
                    vol.Required(CONF_REGIONAL_ONLY, default=False): selector.BooleanSelector(),
                    vol.Required(
                        CONF_MAX_TRAINS, default=DEFAULT_MAX_TRAINS
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=15, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_DELAY_THRESHOLD, default=DEFAULT_DELAY_THRESHOLD_MINUTES
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )


class TrenitaliaCommuterOptionsFlow(OptionsFlow):
    """Handle options for Trenitalia Commuter."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage route and polling options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_NO_CHANGES: bool(user_input[CONF_NO_CHANGES]),
                    CONF_REGIONAL_ONLY: bool(user_input[CONF_REGIONAL_ONLY]),
                    CONF_MAX_TRAINS: int(user_input[CONF_MAX_TRAINS]),
                    CONF_DELAY_THRESHOLD: int(user_input[CONF_DELAY_THRESHOLD]),
                    CONF_LEFRECCE_INTERVAL: int(user_input[CONF_LEFRECCE_INTERVAL]),
                    CONF_VT_INTERVAL: int(user_input[CONF_VT_INTERVAL]),
                    CONF_PAST_WINDOW: int(user_input[CONF_PAST_WINDOW]),
                },
            )

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NO_CHANGES,
                        default=opts.get(CONF_NO_CHANGES, True),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_REGIONAL_ONLY,
                        default=opts.get(CONF_REGIONAL_ONLY, False),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_MAX_TRAINS,
                        default=opts.get(CONF_MAX_TRAINS, DEFAULT_MAX_TRAINS),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=15, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_DELAY_THRESHOLD,
                        default=opts.get(
                            CONF_DELAY_THRESHOLD, DEFAULT_DELAY_THRESHOLD_MINUTES
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_VT_INTERVAL,
                        default=opts.get(
                            CONF_VT_INTERVAL, DEFAULT_VT_SCAN_INTERVAL_MINUTES
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=60, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_LEFRECCE_INTERVAL,
                        default=opts.get(
                            CONF_LEFRECCE_INTERVAL,
                            DEFAULT_LEFRECCE_SCAN_INTERVAL_MINUTES,
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=5, max=120, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_PAST_WINDOW,
                        default=opts.get(
                            CONF_PAST_WINDOW, DEFAULT_PAST_WINDOW_MINUTES
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=90, step=5, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )