# ****************************************************************************************
# Based on Py-weather
# ****************************************************************************************

import indigo

import logging
import time
import requests

from datetime import datetime
from socket import socket, AF_INET, SOCK_STREAM

class PWS(object):

    def __init__(self, device):

        self.logger = logging.getLogger("Plugin.PWS")
        self.device = device
        
        self.address     = self.device.pluginProps.get('address', None)
        self.password    = self.device.pluginProps.get('password', None)
        self.server_host = self.device.pluginProps.get('host', 'www.pwsweather.com')
        self.server_port = self.device.pluginProps.get('port', 80)

        self.iss_device =  int(self.device.pluginProps.get('iss_device', None))
        self.baro_device = int(self.device.pluginProps.get('baro_device', None))

        self.logger.debug(u"{}: PWS station_id = {}, server_host = {}, server_port = {}".format(self.device.name, self.address, self.server_host, self.server_port))


    def __del__(self):
        stateList = [
            { 'key':'status',   'value':  "Off"},
            { 'key':'timestamp','value':  datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ]
        self.device.updateStatesOnServer(stateList)
        self.device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)


    def send_update(self):

        URI = "/pwsupdate/pwsupdate.php"
        url = "http://{}:{}/{}".format(self.server_host, self.server_port, URI)
        iss_device = indigo.devices[self.iss_device]
        baro_device = indigo.devices[self.baro_device]
        data = {
            'ID': self.address,
            'PASSWORD': self.password,
            'action':'updateraw',
            'softwaretype': 'Indigo WeatherLink Live', 
            'dateutc': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        
            'tempf': float(iss_device.states['temp']),
            'dewptf': float(iss_device.states['dew_point']),

            'baromin': float(baro_device.states['bar_absolute']),
            'humidity': float(iss_device.states['hum']),

            'rainin': float(iss_device.states['rain_60_min']),
            'dailyrainin': float(iss_device.states['rainfall_daily']),
            'monthrainin': float(iss_device.states['rainfall_monthly']),
            'yearrainin': float(iss_device.states['rainfall_year']),

            'windspeedmph': float(iss_device.states['wind_speed_avg_last_10_min']),
            'windgustmph': float(iss_device.states['wind_speed_hi_last_10_min']),
            'winddir': float(iss_device.states['wind_dir_scalar_avg_last_10_min'])
        }
        
        self.logger.debug(u"{}: PWS upload data = {}".format(self.device.name,data))
            
        try:
            r = requests.get(url, params=data)
        except Exception as err:
            self.logger.error(u"{}: send_update error: {}".format(self.device.name, err))
            status = "Request Error"
            stateImage = indigo.kStateImageSel.SensorTripped
        else:
            if not r.text.find('Logged and posted') >= 0:
                self.logger.error(u"{}: send_update error: {}".format(self.device.name, r.text))
                status = "Data Error"
                stateImage = indigo.kStateImageSel.SensorTripped
            else:
                self.logger.debug(u"{}: send_update complete".format(self.device.name))
                status = "OK"
                stateImage = indigo.kStateImageSel.SensorOn

        stateList = [
            { 'key':'status',   'value':  status},
            { 'key':'timestamp','value':  datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ]
        self.device.updateStatesOnServer(stateList)
        self.device.updateStateImageOnServer(stateImage)

        