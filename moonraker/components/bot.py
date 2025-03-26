# Example Component
#
# Copyright (C) 2021  Eric Callahan <arksine.code@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import pathlib
from aiogram import Bot
from aiogram.types import InputMediaDocument, FSInputFile
# from confighelper import ConfigHelper
from ..common import RequestType, WebRequest

class TelegaBot:
  BOT_TOKEN = '7477283210:AAEVzG27uoRdepXFl5ksHkE7rvbhYsQuY5s'
  GROUP_ID = -1002345493894
  def __init__(self, config):
      self.server = config.get_server()
      self.name = None
      self.phone = None
      self.email = None
      self.serial_number = None
      self.description = None
      self.bot = Bot(self.BOT_TOKEN)
      self.server.register_endpoint(
          "/server/bot/send_logs", RequestType.POST, self._handle_send_logs)

  async def _handle_send_logs(self, web_request: WebRequest):
      try:
        self.name = web_request.get('name', None)
        self.phone = web_request.get('phone', None)
        self.email = web_request.get('email', None)
        self.serial_number = web_request.get('serial_number')
        self.description = web_request.get('description', None)

        logs_path = pathlib.Path("~/printer_data/logs").expanduser().resolve()
        logs = ['klippy.log', 'moonraker.log', 'KlipperScreen.log']
        config_path = pathlib.Path("~/printer_data/config").expanduser().resolve()
        configs = ['printer.cfg', 'moonraker.conf', 'KlipperScreen.conf']
        media_group = self.create_media_group(logs_path, logs) + self.create_media_group(config_path, configs, True)

        await self.bot.send_media_group(self.GROUP_ID, media_group)
        return "ok"
      except Exception as e:
          logging.error(f"error on send_logs {e}")
          raise self.server.error(e)


  def create_media_group(self, path, files, is_last_path=False):
    mg = []
    caption = None
    for file in files:
      fullpath = pathlib.Path(path.joinpath(file))
      if fullpath.exists():
          if is_last_path:
            if (len(files) - len(mg) == 1):
                caption = f"Имя: {self.name}\nТелефон: {self.phone}\nСерийный номер: {self.serial_number}\nПочта: {self.email}\nОписание проблемы: {self.description}"
          mg.append(InputMediaDocument(media = FSInputFile(fullpath), caption = caption))
    return mg

def load_component(config) -> TelegaBot:
    return TelegaBot(config)