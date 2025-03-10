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
      self.bot = Bot(self.BOT_TOKEN)
      self.server.register_endpoint(
          "/server/bot/send_logs", RequestType.POST, self._handle_send_logs)

  async def _handle_send_logs(self, web_request: WebRequest):
      try:
        name = web_request.get('name', None)
        phone = web_request.get('phone', None)
        email = web_request.get('email', None)
        serial_number = web_request.get('serial_number')
        description = web_request.get('description', None)
        logs_path = pathlib.Path("~/printer_data/logs").expanduser().resolve()
        logs_media_group = []
        logs = ['klippy.log', 'moonraker.log', 'KlipperScreen.log']
        for file in logs:
            fullpath = pathlib.Path(logs_path.joinpath(file))
            if fullpath.exists():
                if (len(logs) - len(logs_media_group) == 1):
                    caption = f"Имя: {name}\nТелефон: {phone}\nСерийный номер: {serial_number}\nПочта: {email}\nОписание проблемы: {description}"
                else:
                    caption = None
                logs_media_group.append(InputMediaDocument(media = FSInputFile(fullpath), caption = caption))
        await self.bot.send_media_group(self.GROUP_ID, logs_media_group)
        return "ok"
      except Exception as e:
          logging.error(f"error on send_logs {e}")
          raise self.server.error(e)


def load_component(config) -> TelegaBot:
    return TelegaBot(config)