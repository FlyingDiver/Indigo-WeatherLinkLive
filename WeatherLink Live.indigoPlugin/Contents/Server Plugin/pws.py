# ****************************************************************************************
# Based on Py-weather
# ****************************************************************************************

import indigo

import logging
import time
import requests

from datetime import datetime


class PWS(object):

    def __init__(self, device):

        self.logger = logging.getLogger("Plugin.PWS")
        self.deviceId = device.id

        self.address = device.pluginProps.get('address', None)
        self.password = device.pluginProps.get('password', None)
        self.server_host = device.pluginProps.get('host', 'www.pwsweather.com')
        self.server_port = device.pluginProps.get('port', 80)

        self.iss_device = int(device.pluginProps.get('iss_device', None))
        self.baro_device = int(device.pluginProps.get('baro_device', None))

        self.updateFrequency = (float(device.pluginProps.get('updateFrequency', "10")) * 60.0)
        self.next_update = time.time()

        self.logger.debug(f"{device.name}: PWS station_id = {self.address}, server_host = {self.server_host}, server_port = {self.server_port}")

    def __del__(self):
        device = indigo.devices[self.deviceId]

        stateList = [
            {'key': 'status', 'value': "Off"},
            {'key': 'timestamp', 'value': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ]
        device.updateStatesOnServer(stateList)
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def send_update(self):
        device = indigo.devices[self.deviceId]

        self.logger.debug(f"{device.name}: Sending Update")

        self.next_update = time.time() + self.updateFrequency

        URI = "/pwsupdate/pwsupdate.php"
        url = f"http://{self.server_host}:{self.server_port}/{URI}"  # noqa
        iss_device = indigo.devices[self.iss_device]
        baro_device = indigo.devices[self.baro_device]
        data = {
            'ID': self.address,
            'PASSWORD': self.password,
            'softwaretype': 'Indigo WeatherLink Live',
            'action': 'updateraw',
            'dateutc': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),

            'tempf': float(iss_device.states['temp']),
            'dewptf': float(iss_device.states['dew_point']),

            'baromin': float(baro_device.states['bar_sea_level']),
            'humidity': float(iss_device.states['hum']),

            'rainin': float(iss_device.states['rain_60_min']),
            'dailyrainin': float(iss_device.states['rainfall_daily']),
            'monthrainin': float(iss_device.states['rainfall_monthly']),
            'yearrainin': float(iss_device.states['rainfall_year']),

            'windspeedmph': float(iss_device.states['wind_speed_avg_last_10_min']),
            'windgustmph': float(iss_device.states['wind_speed_hi_last_10_min']),
            'winddir': float(iss_device.states['wind_dir_scalar_avg_last_10_min']),

        }

        self.logger.debug(f"{device.name}: PWS upload data = {data}")

        try:
            r = requests.get(url, params=data)
        except Exception as err:
            self.logger.error(f"{device.name}: send_update error: {err}")
            status = "Request Error"
            stateImage = indigo.kStateImageSel.SensorTripped
        else:
            if not r.text.find('Logged and posted') >= 0:
                self.logger.error(f"{device.name}: send_update error: {r.text}")
                status = "Data Error"
                stateImage = indigo.kStateImageSel.SensorTripped
            else:
                self.logger.debug(f"{device.name}: send_update complete")
                status = "OK"
                stateImage = indigo.kStateImageSel.SensorOn

        stateList = [
            {'key': 'status', 'value': status},
            {'key': 'timestamp', 'value': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ]
        device.updateStatesOnServer(stateList)
        device.updateStateImageOnServer(stateImage)
