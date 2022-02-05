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
        self.device = device

        self.address = device.pluginProps.get(u'address', "")
        self.http_port = int(device.pluginProps.get(u'port', 80))

        self.pollFrequency = float(self.device.pluginProps.get('pollingFrequency', "10")) * 60.0
        self.next_poll = time.time()

        self.logger.debug(u"AirLink __init__ address = {}, port = {}, pollFrequency = {}".format(self.address, self.http_port, self.pollFrequency))

    def __del__(self):
        self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def http_poll(self):

        self.logger.info(u"{}: Polling AirLink Live".format(self.device.name))

        self.next_poll = time.time() + self.pollFrequency

        url = "http://{}:{}/v1/current_conditions".format(self.address, self.http_port)  # noqa
        try:
            response = requests.get(url, timeout=3.0)
        except requests.exceptions.RequestException as err:
            self.logger.error(u"{}: http_poll RequestException: {}".format(self.device.name, err))
            stateList = [
                {'key': 'status', 'value': 'HTTP Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        try:
            json_data = response.json()
        except Exception as err:
            self.logger.error(u"{}: http_poll JSON decode error: {}".format(self.device.name, err))
            stateList = [
                {'key': 'status', 'value': 'JSON Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.threaddebug("{}".format(response.text))

        if json_data['error']:
            self.logger.error(u"{}: http_poll Bad return code: {}".format(self.device.name, json_data['error']))
            stateList = [
                {'key': 'status', 'value': 'Server Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.debug(
            u"{}: http_poll success: did = {}, ts = {}, {} conditions".format(self.device.name, json_data['data']['did'], json_data['data']['ts'],
                                                                              len(json_data['data']['conditions'])))
        self.logger.threaddebug("{}".format(json_data))

        self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        return json_data['data']['conditions']
