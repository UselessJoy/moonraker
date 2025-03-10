# Helper for Moonraker to Klippy API calls.
#
# Copyright (C) 2020 Eric Callahan <arksine.code@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
from __future__ import annotations
from moonraker.utils import Sentinel
import logging
from ..utils import Sentinel
from ..common import WebRequest, APITransport, RequestType
# Annotation imports
from typing import (
    TYPE_CHECKING,
    Any,
    Union,
    Optional,
    Dict,
    List,
    TypeVar,
    Mapping,
    Callable,
    Coroutine
)
if TYPE_CHECKING:
    from ..confighelper import ConfigHelper
    from .klippy_connection import KlippyConnection as Klippy
    Subscription = Dict[str, Optional[List[Any]]]
    SubCallback = Callable[[Dict[str, Dict[str, Any]], float], Optional[Coroutine]]
    _T = TypeVar("_T")

INFO_ENDPOINT = "info"
ESTOP_ENDPOINT = "emergency_stop"
LIST_EPS_ENDPOINT = "list_endpoints"
GC_OUTPUT_ENDPOINT = "gcode/subscribe_output"
GCODE_ENDPOINT = "gcode/script"
ASYNC_COMMAND_ENDPOINT = "gcode/async_command"
SUBSCRIPTION_ENDPOINT = "objects/subscribe"
STATUS_ENDPOINT = "objects/query"
OBJ_LIST_ENDPOINT = "objects/list"
REG_METHOD_ENDPOINT = "register_remote_method"

class KlippyAPI(APITransport):
    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.klippy: Klippy = self.server.lookup_component("klippy_connection")
        self.eventloop = self.server.get_event_loop()
        app_args = self.server.get_app_args()
        self.version = app_args.get('software_version')
        # Maintain a subscription for all moonraker requests, as
        # we do not want to overwrite them
        self.host_subscription: Subscription = {}
        self.subscription_callbacks: List[SubCallback] = []

        # Register GCode Aliases
        self.server.register_endpoint(
            "/printer/print/pause", RequestType.POST, self._gcode_pause
        )
        self.server.register_endpoint(
            "/printer/print/resume", RequestType.POST, self._gcode_resume
        )
        self.server.register_endpoint(
            "/printer/print/cancel", RequestType.POST, self._gcode_cancel
        )
        self.server.register_endpoint(
            "/printer/print/start", RequestType.POST, self._gcode_start_print
        )
        self.server.register_endpoint(
            "/printer/restart", RequestType.POST, self._gcode_restart
        )
        self.server.register_endpoint(
            "/printer/firmware_restart", RequestType.POST, self._gcode_firmware_restart
        )
        self.server.register_endpoint(
            "/printer/load_backup_config", RequestType.POST, self._load_backup_config
        )
        self.server.register_event_handler(
            "server:klippy_disconnect", self._on_klippy_disconnect
        )
        ####      NEW      ####
        self.server.register_endpoint(
            "/printer/check_backup", RequestType.POST, self._check_backup)
        self.server.register_endpoint(
            "/printer/print/rebuild", RequestType.POST, self._gcode_rebuild)
        self.server.register_endpoint(
            "/printer/print/remove", RequestType.POST, self._gcode_remove)
        self.server.register_endpoint(
            "/printer/get-neopixel-color", RequestType.GET, self._gcode_get_neopixel_color)
        self.server.register_endpoint(
            "/printer/getscrewimage", RequestType.GET, self.get_screw_image)
        self.server.register_endpoint(
            "/printer/setautooff", RequestType.POST, self._set_auto_off)
        self.server.register_endpoint(
            "/printer/offautooff", RequestType.POST, self._off_auto_off)
        self.server.register_endpoint(
            "/printer/setKlipperLang", RequestType.POST, self._set_klipper_lang)
        
        self.server.register_endpoint(
            "/printer/setSafetyPrinting", RequestType.POST, self._set_safety_printing)
        
        self.server.register_endpoint(
            "/printer/setQuiteMode", RequestType.POST, self._set_quite_mode)
        
        self.server.register_endpoint(
            "/printer/setWatchBedMesh", RequestType.POST, self._set_watch_bed_mesh)

        self.server.register_endpoint(
            "/printer/setAutoloadBedMesh", RequestType.POST, self._set_autoload_bed_mesh)
        
        self.server.register_endpoint(
            "/printer/setwifimode", RequestType.POST, self._set_wifi_mode)
        
        self.server.register_endpoint(
            "/printer/open_message", RequestType.POST, self._send_message)
        self.server.register_endpoint(
            "/printer/close_message", RequestType.POST, self._close_message)
        
        self.server.register_endpoint(
            "/printer/turn_off_heaters", RequestType.POST, self._turn_off_heaters)
        
        self.server.register_endpoint(
            "/printer/gcode/async_command", RequestType.POST, self._run_async_command)
        
        self.server.register_endpoint(
            "/printer/resonance_tester/action", RequestType.POST, self._resonance_tester_action)
        
        self.server.register_endpoint(
            "/printer/setActiveTension", RequestType.POST, self._set_active_tension)
        
        self.server.register_endpoint(
            "/printer/pid_calibrate/stop_pid_calibrate", RequestType.POST, self._stop_pid_calibrate)
        
        self.server.register_endpoint(
            "/printer/fixing/repeat_update", RequestType.POST, self._repeat_update)
        
        self.server.register_endpoint(
            "/printer/fixing/close_dialog", RequestType.POST, self._close_dialog)
        ####    END NEW    ####
    def _on_klippy_disconnect(self) -> None:
            self.host_subscription.clear()
            self.subscription_callbacks.clear()
            
    async def _gcode_pause(self, web_request: WebRequest) -> str:
        return await self.pause_print()

    async def _gcode_resume(self, web_request: WebRequest) -> str:
        return await self.resume_print()

    async def _gcode_cancel(self, web_request: WebRequest) -> str:
        return await self.cancel_print()

    async def _gcode_start_print(self, web_request: WebRequest) -> str:
        filename: str = web_request.get_str('filename')
        user = web_request.get_current_user()
        return await self.start_print(filename, user=user)


    async def _gcode_restart(self, web_request: WebRequest) -> str:
        return await self.do_restart("RESTART")

    async def _gcode_firmware_restart(self, web_request: WebRequest) -> str:
        return await self.do_restart("FIRMWARE_RESTART")
    
    async def _gcode_save_default_neopixel_color(self, web_request:WebRequest) -> str:
        neopixel: str = web_request.get_str('neopixel')
        return await self.save_default_neopixel_color(neopixel)
    
    async def _gcode_get_neopixel_color(self, web_request:WebRequest) -> str:
        neopixel: str = web_request.get_str('neopixel')
        return await self.get_neopixel_color(neopixel)
        
    async def _gcode_rebuild(self, web_request: WebRequest) -> str:
        return await self.do_rebuild("SDCARD_RUN_FILE")

    ####      NEW      ####
    async def _send_message(self, web_request: WebRequest) -> str:
        message_type: str = web_request.get_str('message_type')
        message: str = web_request.get_str('message')
        return await self.open_message(message_type, message)
    async def open_message(self, message_type, message, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "messages/open_message", {'message_type': message_type, 'message': message}, default)

    async def _close_message(self, web_request: WebRequest) -> str:
        return await self.close_message()
    async def close_message(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "messages/close_message", {}, default)

    async def _turn_off_heaters(self, web_request: WebRequest) -> str:
        return await self.off_heaters()
    async def off_heaters(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "heaters/turn_off_heaters", {}, default)

    async def _check_backup(self, web_request: WebRequest) -> str:
        return await self.check_backup()
    async def check_backup(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "configfile/check_backup", {}, default)

    async def _load_backup_config(self, web_request: WebRequest) -> str:
        return await self.load_backup_config()
    async def load_backup_config(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "configfile/load_backup_config", {}, default)

    async def _set_wifi_mode(self, web_request: WebRequest) -> str:
        return await self.do_set_wifi_mode(web_request.get_str('wifi_mode'))
    async def do_set_wifi_mode(self, wifi_mode, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "wifi_mode/set_wifi_mode", {'wifi_mode': wifi_mode}, default)

    async def _set_auto_off(self, web_request: WebRequest) -> str:
        return await self.do_set_auto_off(web_request.get_boolean('autoOff_enable'))
    async def do_set_auto_off(self, enable, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "autooff/set_auto_off", {'autoOff_enable': enable}, default)

    async def _set_klipper_lang(self, web_request: WebRequest) -> str:
        return await self.do_set_klipper_lang(web_request.get_str('lang'))
    async def do_set_klipper_lang(self, lang, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "locale/set_lang", {'lang': lang}, default)

    async def _set_safety_printing(self, web_request: WebRequest) -> str:
        return await self.do_set_safety_printing(web_request.get_boolean('safety_enabled'))
    async def do_set_safety_printing(self, safety, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "safety_printing/set_safety_printing", {'safety_enabled': safety}, default)

    async def _set_quite_mode(self, web_request: WebRequest) -> str:
        return await self.do_set_quite_mode(web_request.get_str('stepper'), web_request.get_boolean('quite_mode'))
    async def do_set_quite_mode(self, stepper, quite_mode, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            f"tmc/set_quite_mode/{stepper}", {'quite_mode': quite_mode}, default)

    async def _set_watch_bed_mesh(self, web_request: WebRequest) -> str:
        return await self.do_set_watch_bed_mesh(web_request.get_boolean('watch_bed_mesh'))
    async def do_set_watch_bed_mesh(self, watch_bed_mesh, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "virtual_sdcard/set_watch_bed_mesh", {'watch_bed_mesh': watch_bed_mesh}, default)

    async def _set_autoload_bed_mesh(self, web_request: WebRequest) -> str:
        return await self.do_set_autoload_bed_mesh(web_request.get_boolean('autoload_bed_mesh'))
    async def do_set_autoload_bed_mesh(self, autoload_bed_mesh, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "virtual_sdcard/set_autoload_bed_mesh", {'autoload_bed_mesh': autoload_bed_mesh}, default)

    async def _set_active_tension(self, web_request: WebRequest) -> str:
        return await self.do_set_active_tension(web_request.get_str('tension'))
    async def do_set_active_tension(self, tension, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "resonance_tester/set_active_tension", {'tension': tension}, default)

    async def _stop_pid_calibrate(self, web_request: WebRequest) -> str:
        return await self.do_stop_pid_calibrate()
    async def do_stop_pid_calibrate(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "pid_calibrate/stop_pid_calibrate", {}, default)

    async def _off_auto_off(self, web_request: WebRequest) -> str:
        return await self.do_off_auto_off()
    async def do_off_auto_off(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "autooff/off_autooff", {}, default)

    async def _repeat_update(self, web_request: WebRequest) -> str:
        return await self.do_repeat_update()
    async def do_repeat_update(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "fixing/repeat_update", {}, default)

    async def _close_dialog(self, web_request: WebRequest) -> str:
        return await self.do_close_dialog()
    async def do_close_dialog(self, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        return await self._send_klippy_request(
            "fixing/close_dialog", {}, default)

    async def _run_async_command(self, web_request: WebRequest) -> str:
        return await self.do_run_async_command(web_request.get_str('command'))
    async def do_run_async_command(self, command, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        params = {'command': command}
        return await self._send_klippy_request(
            ASYNC_COMMAND_ENDPOINT, params, default)

    async def _resonance_tester_action(self, web_request: WebRequest) -> str:
        return await self.do_resonance_tester_action(web_request.get_str('action'), web_request.get_list('args'))
    async def do_resonance_tester_action(self, action, args, default: Union[Sentinel, _T] = Sentinel.MISSING) -> str:
        params = {'action': action, 'args': args}
        return await self._send_klippy_request(
            "resonance_tester/shaper_graph", params, default)

    async def do_rebuild(
        self, gc: str, wait_klippy_started: bool = False
    ) -> str:
        # WARNING: Do not call this method from within the following
        # event handlers when "wait_klippy_started" is set to True:
        # klippy_identified, klippy_started, klippy_ready, klippy_disconnect
        # Doing so will result in "wait_started" blocking for the specifed
        # timeout (default 20s) and returning False.
        if wait_klippy_started:
            await self.klippy.wait_started()
        try:
            await self.run_gcode(gc)
        except:
                raise

    async def _gcode_remove(self, web_request: WebRequest) -> str:
        await self.do_remove("SDCARD_REMOVE_FILE")

    async def do_remove(
            self, gc: str, wait_klippy_started: bool = False
    ) -> str:
        if wait_klippy_started:
            await self.klippy.wait_started()
        try:
            await self.run_gcode(gc)
        except:
            raise   

    async def get_screw_image(self, web_request:WebRequest) -> str:
        result = await self.run_gcode("GET_SCREW_IMAGE")
        return result

    async def get_neopixel_color(self, neopixel: str) -> str:
        return await self.run_gcode(f'GET_COLOR NEOPIXEL="{neopixel}"')

    async def save_default_neopixel_color(self, neopixel: str, r: float, g: float, b: float) -> str:
        script = f'SAVE_DEFAULT_COLOR NEOPIXEL="{neopixel}" RED="{r}" GREEN="{g}" BLUE="{b}"'
        return await self.run_gcode(script)
    ####    END NEW    ####

    async def _send_klippy_request(
        self,
        method: str,
        params: Dict[str, Any],
        default: Any = Sentinel.MISSING,
        transport: Optional[APITransport] = None
    ) -> Any:
        try:
            req = WebRequest(method, params, transport=transport or self)
            result = await self.klippy.request(req)
        except self.server.error:
            if default is Sentinel.MISSING:
                raise
            result = default
        return result

    async def run_gcode(self,
                        script: str,
                        default: Any = Sentinel.MISSING
                        ) -> str:
        params = {'script': script}
        result = await self._send_klippy_request(
            GCODE_ENDPOINT, params, default)
        return result

    async def start_print(
        self,
        filename: str,
        wait_klippy_started: bool = False,
        user: Optional[Dict[str, Any]] = None
    ) -> str:
        # WARNING: Do not call this method from within the following
        # event handlers when "wait_klippy_started" is set to True:
        # klippy_identified, klippy_started, klippy_ready, klippy_disconnect
        # Doing so will result in "wait_started" blocking for the specifed
        # timeout (default 20s) and returning False.
        # XXX - validate that file is on disk
        if filename[0] == '/':
            filename = filename[1:]
        # Escape existing double quotes in the file name
        filename = filename.replace("\"", "\\\"")
        script = f'SDCARD_PRINT_FILE FILENAME="{filename}"'
        if wait_klippy_started:
            await self.klippy.wait_started()
        logging.info(f"Requesting Job Start, filename = {filename}")
        ret = await self.run_gcode(script)
        self.server.send_event("klippy_apis:job_start_complete", user)
        return ret

    async def pause_print(
        self, default: Union[Sentinel, _T] = Sentinel.MISSING
    ) -> Union[_T, str]:
        self.server.send_event("klippy_apis:pause_requested")
        logging.info("Requesting job pause...")
        return await self._send_klippy_request(
            "pause_resume/pause", {}, default)
  
    async def resume_print(
        self, default: Union[Sentinel, _T] = Sentinel.MISSING
    ) -> Union[_T, str]:
        self.server.send_event("klippy_apis:resume_requested")
        logging.info("Requesting job resume...")
        return await self._send_klippy_request(
            "pause_resume/resume", {}, default)

    async def cancel_print(
        self, default: Union[Sentinel, _T] = Sentinel.MISSING
    ) -> Union[_T, str]:
        self.server.send_event("klippy_apis:cancel_requested")
        logging.info("Requesting job cancel...")
        return await self._send_klippy_request(
            "pause_resume/cancel", {}, default)

    async def do_restart(
        self, gc: str, wait_klippy_started: bool = False
    ) -> str:
        # WARNING: Do not call this method from within the following
        # event handlers when "wait_klippy_started" is set to True:
        # klippy_identified, klippy_started, klippy_ready, klippy_disconnect
        # Doing so will result in "wait_started" blocking for the specifed
        # timeout (default 20s) and returning False.
        if wait_klippy_started:
            await self.klippy.wait_started()
        try:
            result = await self.run_gcode(gc)
        except self.server.error as e:
            if str(e) == "Klippy Disconnected":
                result = "ok"
            else:
                raise
        return result

    async def list_endpoints(self,
                             default: Union[Sentinel, _T] = Sentinel.MISSING
                             ) -> Union[_T, Dict[str, List[str]]]:
        return await self._send_klippy_request(
            LIST_EPS_ENDPOINT, {}, default)

    async def emergency_stop(self) -> str:
        return await self._send_klippy_request(ESTOP_ENDPOINT, {})

    async def get_klippy_info(self,
                              send_id: bool = False,
                              default: Union[Sentinel, _T] = Sentinel.MISSING
                              ) -> Union[_T, Dict[str, Any]]:
        params = {}
        if send_id:
            ver = self.version
            params = {'client_info': {'program': "Moonraker", 'version': ver}}
        return await self._send_klippy_request(INFO_ENDPOINT, params, default)

    async def get_object_list(self,
                              default: Union[Sentinel, _T] = Sentinel.MISSING
                              ) -> Union[_T, List[str]]:
        result = await self._send_klippy_request(
            OBJ_LIST_ENDPOINT, {}, default)
        if isinstance(result, dict) and 'objects' in result:
            return result['objects']
        if default is not Sentinel.MISSING:
            return default
        raise self.server.error("Invalid response received from Klippy", 500)

    async def query_objects(self,
                            objects: Mapping[str, Optional[List[str]]],
                            default: Union[Sentinel, _T] = Sentinel.MISSING
                            ) -> Union[_T, Dict[str, Any]]:
        params = {'objects': objects}
        result = await self._send_klippy_request(
            STATUS_ENDPOINT, params, default)
        if isinstance(result, dict) and "status" in result:
            return result["status"]
        if default is not Sentinel.MISSING:
            return default
        raise self.server.error("Invalid response received from Klippy", 500)

    async def subscribe_objects(
        self,
        objects: Mapping[str, Optional[List[str]]],
        callback: Optional[SubCallback] = None,
        default: Union[Sentinel, _T] = Sentinel.MISSING
    ) -> Union[_T, Dict[str, Any]]:
        # The host transport shares subscriptions amongst all components
        for obj, items in objects.items():
            if obj in self.host_subscription:
                prev = self.host_subscription[obj]
                if items is None or prev is None:
                    self.host_subscription[obj] = None
                else:
                    uitems = list(set(prev) | set(items))
                    self.host_subscription[obj] = uitems
            else:
                self.host_subscription[obj] = items
        params = {"objects": dict(self.host_subscription)}
        result = await self._send_klippy_request(SUBSCRIPTION_ENDPOINT, params, default)
        if isinstance(result, dict) and "status" in result:
            if callback is not None:
                self.subscription_callbacks.append(callback)
            return result["status"]
        if default is not Sentinel.MISSING:
            return default
        raise self.server.error("Invalid response received from Klippy", 500)

    async def subscribe_from_transport(
        self,
        objects: Mapping[str, Optional[List[str]]],
        transport: APITransport,
        default: Union[Sentinel, _T] = Sentinel.MISSING,
    ) -> Union[_T, Dict[str, Any]]:
        params = {"objects": dict(objects)}
        result = await self._send_klippy_request(
            SUBSCRIPTION_ENDPOINT, params, default, transport
        )
        if isinstance(result, dict) and "status" in result:
            return result["status"]
        if default is not Sentinel.MISSING:
            return default
        raise self.server.error("Invalid response received from Klippy", 500)

    async def subscribe_gcode_output(self) -> str:
        template = {'response_template':
                    {'method': "process_gcode_response"}}
        return await self._send_klippy_request(GC_OUTPUT_ENDPOINT, template)

    async def register_method(self, method_name: str) -> str:
        return await self._send_klippy_request(
            REG_METHOD_ENDPOINT,
            {'response_template': {"method": method_name},
             'remote_method': method_name})

    def send_status(
        self, status: Dict[str, Any], eventtime: float
    ) -> None:
        for cb in self.subscription_callbacks:
            self.eventloop.register_callback(cb, status, eventtime)
        self.server.send_event("server:status_update", status)

def load_component(config: ConfigHelper) -> KlippyAPI:
    return KlippyAPI(config)
