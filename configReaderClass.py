# coding=utf-8
"""	Este objeto se ocupa de leer las configuraciones establecidas para
	el sistema, para determinar el comportamiento del mismo

	@author: Gonzalez Leonardo Mauricio
	@author: Reinoso Ever Denis
	@organization: UNC - FCEFYN
	@date: Lunes 16 de Abril de 2015 """

import os

ethernetPriority = 4
bluetoothPriority = 4
emailPriority =  2
smsPriority = 0
processNotifications = True
warningNotifiactions = True
errorNotifications = True

def readConfigFile():
	configurationFile =  open('properties.conf').readlines() # Apertura de Archivo
	configurationFile = ''.join(configurationFile) # Conversión a String para ejecución
	try:
		exec(configurationFile)
	except Exception:
		print '[COMUNICADOR-ERROR] El archivo properties.conf no esta bien configurado,\
se usa la configuración por defecto.'

readConfigFile()