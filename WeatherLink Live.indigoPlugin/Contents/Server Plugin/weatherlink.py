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
class WeatherLink(object):

    def __init__(self, device):
        self.logger = logging.getLogger("Plugin.WeatherLink")
        self.device = device

        self.address = device.pluginProps.get(u'address', "")
        self.http_port = int(device.pluginProps.get(u'port', 80))
        self.udp_port = None
        self.sock = None

        self.pollFrequency = float(self.device.pluginProps.get('pollingFrequency', "10")) * 60.0
        self.next_poll = time.time()

        self.logger.debug(f"WeatherLink __init__ address = {self.address}, port = {self.http_port}, pollFrequency = {self.pollFrequency}")

    def __del__(self):
        self.sock.close()
        stateList = [
            {'key': 'status', 'value': "Off"},
            {'key': 'timestamp', 'value': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ]
        self.device.updateStatesOnServer(stateList)
        self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def udp_start(self):

        if not self.device.pluginProps['enableUDP']:
            self.logger.debug(u"{}: udp_start() aborting, not enabled".format(self.device.name))
            return

        url = f"http://{self.address}:{self.http_port}/v1/real_time"    # noqa
        try:
            response = requests.get(url, timeout=3.0)
        except requests.exceptions.RequestException as err:
            self.logger.error(u"{}: udp_start() RequestException: {}".format(self.device.name, err))
            stateList = [
                {'key': 'status', 'value': 'HTTP Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        try:
            json_data = response.json()
        except Exception as err:
            self.logger.error(u"{}: udp_start() JSON decode error: {}".format(self.device.name, err))
            stateList = [
                {'key': 'status', 'value': 'JSON Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        if json_data['error']:
            if json_data['error']['code'] == 409:
                self.logger.debug(u"{}: udp_start() aborting, no ISS sensors".format(self.device.name))
            else:
                self.logger.error(u"{}: udp_start() error, code: {}, message: {}".format(self.device.name, json_data['error']['code'],
                                                                                         json_data['error']['message']))
            stateList = [
                {'key': 'status', 'value': 'Server Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.debug(u"{}: udp_start() broadcast_port = {}, duration = {}".format(self.device.name, json_data['data']['broadcast_port'],
                                                                                       json_data['data']['duration']))

        # set up socket listener

        if not self.sock:
            try:
                self.udp_port = int(json_data['data']['broadcast_port'])
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                self.sock.settimeout(0.1)
                self.sock.bind(('', self.udp_port))
            except Exception as err:
                self.logger.error(f"{self.device.name}: udp_start() Exception: {err}")
                stateList = [
                    {'key': 'status', 'value': 'Socket Error'},
                ]
                self.device.updateStatesOnServer(stateList)
            else:
                self.logger.debug(u"{}: udp_start() socket listener started".format(self.device.name))

    def udp_receive(self):
        if not self.sock:
            self.logger.threaddebug(f"{self.device.name}: udp_receive error: no socket")
            return

        try:
            data, addr = self.sock.recvfrom(2048)
        except socket.timeout as err:
            return
        except socket.error as err:
            self.logger.error(f"{device.name}: udp_receive socket error: {err}")
            stateList = [
                {'key': 'status', 'value': 'socket Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        try:
            raw_data = data.decode("utf-8")
            self.logger.threaddebug(f"{raw_data}")
            json_data = json.loads(raw_data)
        except Exception as err:
            self.logger.error(f"{self.device.name}: udp_receive JSON decode error: {err}")
            stateList = [
                {'key': 'status', 'value': 'JSON Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.threaddebug(
            f"{self.device.name}: udp_receive success: did = {json_data['did']}, ts = {json_data['ts']}, {len(json_data['conditions'])} conditions")
        self.logger.threaddebug(f"{json_data}")

        time_string = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(float(json_data['ts'])))

        stateList = [
            {'key': 'did', 'value': json_data['did']},
            {'key': 'timestamp', 'value': time_string}
        ]
        self.device.updateStatesOnServer(stateList)

        return json_data['conditions']

    def http_poll(self):

        self.logger.info(f"{self.device.name}: Polling WeatherLink Live")

        self.next_poll = time.time() + self.pollFrequency

        url = f"http://{self.address}:{self.http_port}/v1/current_conditions"   # noqa
        try:
            response = requests.get(url, timeout=3.0)
        except requests.exceptions.RequestException as err:
            self.logger.error(f"{self.device.name}: http_poll RequestException: {err}")
            stateList = [
                {'key': 'status', 'value': 'HTTP Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        try:
            json_data = response.json()
        except Exception as err:
            self.logger.error(f"{self.device.name}: http_poll JSON decode error: {err}")
            stateList = [
                {'key': 'status', 'value': 'JSON Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.threaddebug(f"{response.text}")

        if json_data['error']:
            self.logger.error(f"{self.device.name}: http_poll Bad return code: {json_data['error']}")
            stateList = [
                {'key': 'status', 'value': 'Server Error'},
            ]
            self.device.updateStatesOnServer(stateList)
            self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return

        self.logger.debug(
            f"{self.device.name}: http_poll success: did = {json_data['data']['did']}, ts = {json_data['data']['ts']}, {len(json_data['data']['conditions'])} conditions")
        self.logger.threaddebug(f"{json_data}")

        time_string = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(float(json_data['data']['ts'])))

        stateList = [
            {'key': 'status', 'value': 'OK'},
            {'key': 'did', 'value': json_data['data']['did']},
            {'key': 'timestamp', 'value': time_string}
        ]
        self.device.updateStatesOnServer(stateList)
        self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        return json_data['data']['conditions']
