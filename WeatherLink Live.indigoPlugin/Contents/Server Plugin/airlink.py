#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import time
import socket
import json
import logging
import requests
import threading
import indigo


################################################################################
class AirLink(object):

    def __init__(self, device):
        self.logger = logging.getLogger("Plugin.AirLink")
        self.deviceId = device.id

        self.address = device.pluginProps.get(u'address', "")
        self.http_port = int(device.pluginProps.get(u'port', 80))

        self.pollFrequency = float(device.pluginProps.get('pollingFrequency', "10")) * 60.0
        self.next_poll = time.time()

        self.logger.debug(f"AirLink __init__ address = {self.address}, port = {self.http_port}, pollFrequency = {self.pollFrequency}")

    def __del__(self):
        device = indigo.devices[self.deviceId]
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def http_poll(self):
        device = indigo.devices[self.deviceId]

        self.logger.info(f"{device.name}: Polling AirLink Live")

        self.next_poll = time.time() + self.pollFrequency

        url = f"http://{self.address}:{self.http_port}/v1/current_conditions"  # noqa
        try:
            response = requests.get(url, timeout=3.0)
        except requests.exceptions.RequestException as err:
            self.logger.error(f"{device.name}: http_poll RequestException: {err}")
            stateList = [
                {'key': 'status', 'value': 'HTTP Error'},
            ]
            device.updateStatesOnServer(stateList)
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        try:
            json_data = response.json()
        except Exception as err:
            self.logger.error(f"{device.name}: http_poll JSON decode error: {err}")
            stateList = [
                {'key': 'status', 'value': 'JSON Error'},
            ]
            device.updateStatesOnServer(stateList)
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.threaddebug(f"{response.text}")

        if json_data['error']:
            self.logger.error(f"{device.name}: http_poll Bad return code: {json_data['error']}")
            stateList = [
                {'key': 'status', 'value': 'Server Error'},
            ]
            device.updateStatesOnServer(stateList)
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.debug(
            f"{device.name}: http_poll success: did = {json_data['data']['did']}, ts = {json_data['data']['ts']}, {len(json_data['data']['conditions'])} conditions")
        self.logger.threaddebug(f"{json_data}")

        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        return json_data['data']['conditions']
