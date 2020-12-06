#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

try:
    import indigo
except ImportError:
    pass

import time
import logging
from aprs import APRS
from pws import PWS
from wunderground import WU
from weatherlink import WeatherLink

kCurDevVersCount = 0        # current version of plugin devices
        
        
################################################################################
class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)

        try:
            self.logLevel = int(self.pluginPrefs[u"logLevel"])
        except:
            self.logLevel = logging.INFO
        self.indigo_log_handler.setLevel(self.logLevel)

    def startup(self):
        self.logger.info(u"Starting WeatherLink Live")

        self.updateNeeded = False
        self.weatherlinks = {}          # Dict of Indigo WeatherLink devices, indexed by device.id
        self.sensorDevices = {}         # Dict of Indigo sensor/transmitter devices, indexed by device.id
        self.senders = {}               # Dict of Indigo APRS account devices, indexed by device.id
        self.knownDevices = {}          # Dict of sensor/transmitter devices received by base station, indexed by lsid
        
                    
    def shutdown(self):
        self.logger.info(u"Shutting down WeatherLink Live")


    def runConcurrentThread(self):

        try:
            while True:

                # Process any broadcast data from weather stations
                
                for link in self.weatherlinks.values():
                    self.processConditions(link.udp_receive())

                # Get non-broadcast data from weather stations per schedule or forced update

                for link in self.weatherlinks.values():
                    if (time.time() > link.next_poll) or self.updateNeeded:
                        self.processConditions(link.http_poll())
                        self.sleep(2.0)
                        link.udp_start()
                self.updateNeeded = False

                # Upload weather data to networks as needed
                
                for aprs in self.senders.values():
                    if time.time() > aprs.next_update:                    
                        aprs.send_update()

            
                self.sleep(1.0)

        except self.stopThread:
            pass        

################################################################################
#
#   Process the condition data returned from the WLL
#
################################################################################
 
    def processConditions(self, conditions):
    
        if conditions == None:
            return
        
        for condition in conditions:

            sensor_lsid = str(condition['lsid'])
            sensor_type = str(condition['data_structure_type'])
         
            if sensor_lsid not in self.knownDevices:
                sensorInfo = {"lsid": sensor_lsid, "type": sensor_type}
                self.knownDevices[sensor_lsid] = sensorInfo
                self.logger.debug(u"Added sensor {} to knownDevices: {}".format(sensor_lsid, sensorInfo))
                

            for sensorDev in self.sensorDevices.values():
                if sensorDev.address == sensor_lsid:
                    stateList = self.sensorDictToList(condition)
                    sensorDev.updateStatesOnServer(stateList)
                    self.logger.threaddebug(u"{}: Updating sensor: {}".format(sensorDev.name, stateList))


################################################################################
#
#   convert the raw dict the WLL provides to a device-state list, including conversion and UI state generation
#
################################################################################
              
    def sensorDictToList(self, sensor_dict):
        # Retrieve user selected reporting units
        units_temperature = self.pluginPrefs.get("units_temperature", "F")
        units_barometric_pressure = self.pluginPrefs.get("units_barometric_pressure", "IN")
        units_wind = self.pluginPrefs.get("units_wind", "MPH")

        def temperature_conversion(value_to_convert):
            if units_temperature == "C":
                return (((value_to_convert - 32.0) * 5.0) / 9.0), "C"
            else:
                # Assume default Fahrenheit
                return value_to_convert, "F"

        def barometric_pressure_conversion(value_to_convert):
            if units_barometric_pressure == "MM":
                return value_to_convert * 25.4, "mm"
            elif units_barometric_pressure == "MB":
                return value_to_convert * 33.8639, "mb"
            elif units_barometric_pressure == "HP":
                return value_to_convert * 33.8639, "hPa"
            else:
                # Assume default Inches
                return value_to_convert, "in"

        def wind_conversion(value_to_convert):
            if units_wind == "K":
                return value_to_convert * 0.868976, "Knots"
            elif units_wind == "KPH":
                return value_to_convert * 1.60934, "Km/h"
            elif units_wind == "MPS":
                return value_to_convert * 0.44704, "m/s"
            else:
                # Assume default MPH
                return value_to_convert, "mph"

        # get values to convert rain counts to actual units
        rainCollector = {   0: (None, None),
                            1: (0.01,  "in"),
                            2: (0.2,   "mm"),
                            3: (0.1,   "mm"),
                            4: (0.001, "in")
        }
        factor, units = rainCollector[sensor_dict.get('rain_size', 1)]
        
        sensorList = []
        for key, value in sensor_dict.items():
                    
            # consolidate redundant states (same info from http and udp with different names)
            if key == "rainfall_last_15_min":
                key = "rain_15_min"
            elif key == "rainfall_last_60_min":
                key = "rain_60_min"
            elif key == "rainfall_last_24_hr":
                key = "rain_24_hr"

            if not (isinstance(value, int) or isinstance(value, float)):
                self.logger.debug("sensorDictToList: key = {}, value = {} ({}) coerced to value 0".format(key, value, type(value)))
                value = 0
            
            if key in ['temp','temp_in', 'dew_point', 'dew_point_in', 'heat_index_in', 'wind_chill', 'wet_bulb', 'heat_index', 'thw_index', 'thsw_index']:
                value, ui_label = temperature_conversion(value)
                sensorList.append({'key': key, 'value': value, 'decimalPlaces': 1, 'uiValue': u'{:.1f} °{}'.format(value, ui_label)})
                
            elif key in ['temp_1','temp_2', 'temp_3', 'temp_4']:
                value, ui_label = temperature_conversion(value)
                sensorList.append({'key': key, 'value': value, 'decimalPlaces': 1, 'uiValue': u'{:.1f} °{}'.format(value, ui_label)})
                
            elif key in ['hum', 'hum_in']:
                sensorList.append({'key': key, 'value': value, 'decimalPlaces': 0, 'uiValue': u'{:.0f}%'.format(value)})
            
            elif key in ['bar_sea_level', 'bar_trend', 'bar_absolute']:
                value, ui_label = barometric_pressure_conversion(value)
                sensorList.append({'key': key, 'value': value, 'decimalPlaces': 2, 'uiValue': u'{:.2f} {}'.format(value, ui_label)})
            
            elif key in ['wind_speed_last', 'wind_speed_avg_last_1_min', 'wind_speed_avg_last_2_min', 'wind_speed_hi_last_2_min', 
                         'wind_speed_avg_last_10_min', 'wind_speed_hi_last_10_min']:
                value, ui_label = wind_conversion(value)
                sensorList.append({'key': key, 'value': value, 'decimalPlaces': 0, 'uiValue': u'{:.0f} {}'.format(value, ui_label)})
            
            elif key in ['wind_dir_last', 'wind_dir_scalar_avg_last_1_min', 'wind_dir_scalar_avg_last_2_min', 'wind_dir_at_hi_speed_last_2_min', 
                         'wind_dir_scalar_avg_last_10_min', 'wind_dir_at_hi_speed_last_10_min']:
                sensorList.append({'key': key, 'value': value, 'decimalPlaces': 0, 'uiValue': u'{:d}°'.format(value)})
            
            elif key in ['rain_storm_start_at', 'rain_storm_last_end_at', 'rain_storm_last_start_at', 'timestamp']:
                time_string = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(float(value)))
                sensorList.append({'key': key, 'value': time_string, 'decimalPlaces': 0, 'uiValue': u'{}'.format(time_string)})

            elif key in ['rain_rate_last', 'rain_rate_hi', 'rain_rate_hi_last_15_min', 'rain_storm_last']:
                rain = float(value) * factor
                sensorList.append({'key': key, 'value': rain, 'decimalPlaces': 2, 'uiValue': u'{:.2f} {}/hr'.format(rain, units)})
            
            elif key in ['rain_15_min', 'rain_60_min', 'rain_24_hr', 'rain_storm', 'rain_storm_last',
                        'rainfall_daily', 'rainfall_monthly', 'rainfall_year']:
                rain = float(value) * factor
                sensorList.append({'key': key, 'value': rain, 'decimalPlaces': 2, 'uiValue': u'{:.2f} {}'.format(rain, units)})
            
            else:        
                sensorList.append({'key': key, 'value': value})
        
        return sensorList


    ########################################
    # Plugin Preference Methods
    ########################################

    def validatePrefsConfigUi(self, valuesDict):
        errorDict = indigo.Dict()

        try:
            self.logLevel = int(valuesDict[u"logLevel"])
        except:
            self.logLevel = logging.INFO
        self.indigo_log_handler.setLevel(self.logLevel)

        if len(errorDict) > 0:
            return (False, valuesDict, errorDict)
        return (True, valuesDict)

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            try:
                self.logLevel = int(valuesDict[u"logLevel"])
            except:
                self.logLevel = logging.INFO
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(u"WeatherLink Live logLevel = " + str(self.logLevel))


    ########################################
    # Device Management Methods
    ########################################
      
    def deviceStartComm(self, device):
        self.logger.debug(u"{}: Starting Device".format(device.name))

        instanceVers = int(device.pluginProps.get('devVersCount', 0))
        if instanceVers == kCurDevVersCount:
            self.logger.threaddebug(u"{}: Device is current version: {}".format(device.name ,instanceVers))
        elif instanceVers < kCurDevVersCount:
            newProps = device.pluginProps
            newProps["devVersCount"] = kCurDevVersCount
            device.replacePluginPropsOnServer(newProps)
            self.logger.debug(u"{}: Updated device version: {} -> {}".format(device.name,  instanceVers, kCurDevVersCount))
        else:
            self.logger.warning(u"{}: Invalid device version: {}".format(device.name, instanceVers))

        device.stateListOrDisplayStateIdChanged()
                
        if device.deviceTypeId == "weatherlink":
 
            self.weatherlinks[device.id] = WeatherLink(device)
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
            
        elif device.deviceTypeId == "aprs_sender":
 
            self.senders[device.id] = APRS(device)
            
        elif device.deviceTypeId == "pws_sender":
 
            self.senders[device.id] = PWS(device)
            
        elif device.deviceTypeId == "wu_sender":
 
            self.senders[device.id] = WU(device)
            
        elif device.deviceTypeId in ['issSensor', 'moistureSensor', 'tempHumSensor', 'baroSensor']:

            if device.pluginProps.get('status_state', None) in ["temp", "temp_in", "dew_point", "dew_point_in", "heat_index", 
                "heat_index_in", "wind_chill", "temp_1", "temp_2", "temp_3", "temp_4"]:
                device.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensorOn)

            elif device.pluginProps.get('status_state', None) in ["rain_15_min", "rain_60_min", "rain_24_hr"]:
                device.updateStateImageOnServer(indigo.kStateImageSel.Auto)

            elif device.pluginProps.get('status_state', None) in ["hum", "hum_in", "moist_soil_1", "moist_soil_2", "moist_soil_3", 
                "moist_soil_4", "wet_leaf_1", "wet_leaf_2"]:
                device.updateStateImageOnServer(indigo.kStateImageSel.HumiditySensorOn)
        			
            elif device.pluginProps.get('status_state', None) in ["bar_sea_level", "bar_absolute"]:
                device.updateStateImageOnServer(indigo.kStateImageSel.Auto)

            elif device.pluginProps.get('status_state', None) in ["wind_speed_last", "wind_speed_avg_last_2_min"]:
                device.updateStateImageOnServer(indigo.kStateImageSel.WindSpeedSensor)

            else:
                device.updateStateImageOnServer(indigo.kStateImageSel.Auto)

            self.sensorDevices[device.id] = device

        else:
            self.logger.warning(u"{}: Invalid device type: {}".format(device.name, device.deviceTypeId))

        self.updateNeeded = True
        self.logger.debug(u"{}: deviceStartComm complete, sensorDevices = {}".format(device.name, self.sensorDevices))

            
    
    def deviceStopComm(self, device):
        self.logger.debug(u"{}: Stopping Device".format(device.name))
        if device.deviceTypeId == "weatherlink":
            del self.weatherlinks[device.id]
        elif device.deviceTypeId in ["aprs_sender", "pws_sender", "wu_sender"]:
            del self.senders[device.id]
        else:
            del self.sensorDevices[device.id]

        self.logger.debug(u"{}: deviceStopComm complete, sensorDevices = {}".format(device.name, self.sensorDevices))
            
            
    def getDeviceDisplayStateId(self, device):
            
        try:
            status_state = device.pluginProps['status_state']
        except:
            status_state = indigo.PluginBase.getDeviceDisplayStateId(self, device)
            
        self.logger.debug(u"{}: getDeviceDisplayStateId returning: {}".format(device.name, status_state))

        return status_state
    
    
    ################################################################################
    #        
    # return a list of all "Available" devices (not associated with an Indigo device)
    #
    ################################################################################
    
    def availableDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug(u"availableDeviceList: filter = {}, targetId = {}".format(filter, targetId))

        sensorTypes = {
            '1': 'Integrated Sensor Suite',
            '2': 'Leaf/Soil Moisture Sensors',
            '3': 'Internal Barometric Sensor',
            '4': 'Internal Temperature/Humidity Sensor'
        }

        retList =[]
        for devInfo in self.knownDevices.values():
            if devInfo['type'] == filter:
                retList.append((devInfo['lsid'], "{}: {}".format(devInfo['lsid'], sensorTypes[filter])))               
        retList.sort(key=lambda tup: tup[1])
        self.logger.debug(u"availableDeviceList: retList = {}".format(retList))
        return retList
        

    def issDeviceList(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        retList = []
        for sensor in self.sensorDevices.values():
            if sensor.deviceTypeId == "issSensor":
                retList.append((sensor.id, sensor.name))
        retList.sort(key=lambda tup: tup[1])
        return retList

    def baroDeviceList(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        retList = []
        for sensor in self.sensorDevices.values():
            if sensor.deviceTypeId == "baroSensor":
                retList.append((sensor.id, sensor.name))
        retList.sort(key=lambda tup: tup[1])
        return retList


    def pickWeatherLink(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        retList = []
        for link in self.weatherlinks.values():
            retList.append((link.device.id, link.device.name))
        retList.sort(key=lambda tup: tup[1])
        return retList


    ########################################
    # Menu Methods
    ########################################

    def pollWeatherLinkMenu(self, valuesDict, typeId):
        try:
            deviceId = int(valuesDict["targetDevice"])
        except:
            self.logger.error(u"Bad Device specified for Clear SMTP Queue operation")
            return False

        for linkID, link in self.weatherlinks.items():
            if linkID == deviceId:
                self.processConditions(link.http_poll())            
        return True
  
    def dumpKnownDevices(self):
        self.logger.info(u"Known device list:\n" + str(self.knownDevices))
        
    # doesn't do anything, just needed to force other menus to dynamically refresh
    def menuChanged(self, valuesDict, typeId, devId):
        return valuesDict


