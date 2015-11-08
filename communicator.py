 # coding=utf-8

"""Modulo principal que se encarga del control de los demás objetos y submódulos
	para permitir la comunicación. 
	@author: Gonzalez Leonardo Mauricio
	@author: Reinoso Ever Denis
	@organization: UNC - Fcefyn
	@date: Lunes 16 de Mayo de 2015 """

import re
import os
import sys
import time
import json
import Queue
import pickle
import threading
import subprocess

currentDirectory = os.getcwd() 
if not currentDirectory.endswith('Communicator'):
	os.chdir(currentDirectory + '/Communicator')

sys.path.append(os.path.abspath('Network/'))
sys.path.append(os.path.abspath('Email/'))
sys.path.append(os.path.abspath('Modem/'))
sys.path.append(os.path.abspath('Bluetooth/'))

import networkClass
import modemClass
import emailClass
import bluetoothClass

import messageClass
import transmitterClass
import logger
import contactList
import checkerClass

JSON_FILE = 'config.json'
JSON_CONFIG = json.load(open(JSON_FILE))

os.chdir(currentDirectory)

logger.set() # Solo se setea una vez, todos los objetos usan esta misma configuración

receptionBuffer = ''
transmissionBuffer = ''
modemSemaphore = ''

networkInstance = ''
gprsInstance = ''
emailInstance = ''
smsInstance = ''
bluetoothInstance = ''

checkerInstance = ''	 # Hilo que va a verificar las conexiones
transmitterInstance = '' # Hilo para la transmisión de paquetes

def open():
	"""Se realiza la apertura, inicialización de los componentes que se tengan disponibles
	"""
	global receptionBuffer, transmissionBuffer 
	global modemSemaphore, networkInstance, gprsInstance, emailInstance, smsInstance, bluetoothInstance
	global checkerInstance, transmitterInstance

	receptionBuffer = Queue.PriorityQueue(JSON_CONFIG["COMMUNICATOR"]["RECEPTION_BUFFER"])
	transmissionBuffer = Queue.PriorityQueue(JSON_CONFIG["COMMUNICATOR"]["TRANSMISSION_BUFFER"])
	modemSemaphore = threading.Semaphore(value = 1)

	# Creamos las instancias de los periféricos
	networkInstance = networkClass.Network(receptionBuffer)
	gprsInstance = modemClass.Gprs(modemSemaphore)
	emailInstance = emailClass.Email(receptionBuffer)
	smsInstance = modemClass.Sms(receptionBuffer, modemSemaphore)
	bluetoothInstance = bluetoothClass.Bluetooth(receptionBuffer)

	# Creamos la instancia del checker y el hilo que va a verificar las conexiones
	checkerInstance = checkerClass.Checker(modemSemaphore, networkInstance, gprsInstance, emailInstance, smsInstance, bluetoothInstance)

	# Se crea la instancia para la transmisión de paquetes
	transmitterInstance = transmitterClass.Transmitter(transmissionBuffer, networkInstance, bluetoothInstance, emailInstance, smsInstance, checkerInstance)

	if checkerInstance.verifyNetworkConnection() or checkerInstance.verifySmsConnection() or checkerInstance.verifyEmailConnection() or checkerInstance.verifyBluetoothConnection():
		checkerInstance.start()
		transmitterInstance.start()
		return True
	else:
		checkerInstance.start()
		transmitterInstance.start()
		logger.write('WARNING', '[COMMUNICATOR] No hay Modos para la recepción')
		return False

def send(message, receiver = '', device = ''):
	"""Se almacena en el buffer de transmisión el paquete a ser enviado, se guardara
	en caso de que se hayan establecido parametros correctos. En caso de tratarse 
	de un mensaje simple o archivo simple, se los convierte en Instancias para simplificar
	el manejo del mensaje por el transmisor. Pero se envia unicamente la cadena de
	texto o el archivo
	@param message: paquete a ser enviado, ya sea mensaje (o instancia) o un archivo (o instancia)
	@param receiver: es el contacto al que se envia el mensaje
	@param device: modo de envío preferente para ese mensaje en particular (puede no definirse)"""
	global transmissionBuffer, messageClass
	if not transmissionBuffer.full():
		if not isinstance(message,messageClass.Message):
			# Control sobre un mensaje simple
			if not isinstance(message,str):
				logger.write('WARNING', '[COMMUNICATOR] Mensaje descartado, porque no es texto simple ni subclase Mensaje')
				return False
			if receiver == '':
				logger.write('WARNING', '[COMMUNICATOR] Mensaje descartado, no se especifico el receptor')
				return False

			sender = JSON_CONFIG["COMMUNICATOR"]["NAME"] 
			# En caso de que se encuetre el archivo se crea una instancia de archivo
			if os.path.isfile(message): # Comprueba el path absoluto
				absoluteFilePath = message
				if not absoluteFilePath.startswith('/'): # Si no es un path absoluto, agrega el path a la carpeta actual
					absoluteFilePath = currentDirectory + '/' + absoluteFilePath
				# Se determinan los parametros de la instancia archivo por configuración
				priority = JSON_CONFIG["COMMUNICATOR"]["FILE_PRIORITY"]
				timeOut = JSON_CONFIG["COMMUNICATOR"]["FILE_TIME_OUT"]
				message = messageClass.FileMessage(receiver, sender, priority, timeOut, device, absoluteFilePath)
			elif os.path.isfile(JSON_CONFIG["COMMUNICATOR"]["FILES_PATH"] + '/' + message): # Commprueba en la carpeta actual
				absoluteFilePath = JSON_CONFIG["COMMUNICATOR"]["FILES_PATH"] + '/' + message
				# Se determinan los parametros de la instancia archivo por configuración
				priority = JSON_CONFIG["COMMUNICATOR"]["FILE_PRIORITY"]
				timeOut = JSON_CONFIG["COMMUNICATOR"]["FILE_TIME_OUT"]
				message = messageClass.FileMessage(receiver, sender, priority, timeOut, device, absoluteFilePath)
			else: # Se configura una instancia de Mensaje simple
				priority = JSON_CONFIG["COMMUNICATOR"]["MESSAGE_PRIORITY"]
				timeOut = JSON_CONFIG["COMMUNICATOR"]["MESSAGE_TIME_OUT"]
				textMessageTemp = message # Para no perder el mensaje de texto
				message = messageClass.Message(receiver, sender, priority, timeOut, device)
				message.textMessage = textMessageTemp # Se añade un campo para almacenar el mensaje
			# Se añade un campo para no enviar esta instancia, porque corresponden a mensajes simples
			message.sendInstance = False
		else:
			# Control de la existencia del archivo
			if isinstance(message, messageClass.FileMessage):
				# En caso de que se encuetre el archivo lo envia
				if os.path.isfile(message.fileName): # Comprueba el path absoluto
					if not message.fileName.startswith('/'): # Se añade el path al directorio, sino es un path absoluto
						message.fileName = currentDirectory + '/' + message.fileName
				elif os.path.isfile(JSON_CONFIG["COMMUNICATOR"]["FILES_PATH"] + '/' + message.fileName): # Commprueba en la carpeta configurada
					message.fileName = JSON_CONFIG["COMMUNICATOR"]["FILES_PATH"] + '/' + message.fileName
				else:
					logger.write('WARNING', '[NETWORK] Envio cancelado, no se encuentra el archivo (' + message.fileName + ') para el envío.')
					return False
			message.sendInstance = True # Corresponde enviar la instancia  
		# Se añade al mensaje un timestamp, lo mismo "sendInstance" solo sirven para
		# el envio, se borran al dejar de ser necesarios => no transmitir datos innecesarios
		message.timeStamp = time.time()
		# Se añade el mensaje, la cola se encarga de la sincronización de la inserción
		# la prioridad es una resta de 100 porque la priorityQueue saca primero la de prioridad
		# de menor valor, que no va con la lógica de esta implementación. Entonces priority < 100
		if message.priority > 100: 
			message.priority = 99 # Se le da la máxima prioridad 
			logger.write('WARNING', '[COMMUNICATOR] Se configuro una prioridad superior a las establecidas, se cambia por la máxima (99)')
		wakeUpTransmitter = transmissionBuffer.empty()
		# Se guarda también con el timeOut, entonces si la prioridad es la misma se
		# decide por el segundo parametro, cual es menor.. Y si selecciona el timeOut
		# determinara el mensaje más proximo a descartarse, que es el de mayor prioridad
		transmissionBuffer.put((100 - message.priority, message.timeOut, message)) # Se almacena una Tupla
		if wakeUpTransmitter:
			# Se despierta al hilo transmisor porque estaba esperando un mensaje
			transmitterInstance.notEmpty.acquire()
			transmitterInstance.notEmpty.notify()
			transmitterInstance.notEmpty.release()
		logger.write('DEBUG', '[COMMUNICATOR] Paquete almacenado en transmisor')
		return True
	else:
		logger.write('WARNING', '[COMMUNICATOR] El Buffer de transmisión esta lleno, no se puede enviar por el momento.')
		return False

def receive():
	"""Se obtiene de un buffer circular el mensaje recibido mas antiguo.
	@return: Mensaje recibido
	@rtype: str"""
	if receptionBuffer.qsize() > 0:
		message = receptionBuffer.get_nowait()
		return message[1] # Es una tupla y el primer elemento corresponde a la prioridad
	else:
		logger.write('INFO', '[COMUNICADOR] El buffer de mensajes esta vacio.')
		return None

def lenght():
	"""Devuelve el tamaño del buffer de recepción.
	@return: Cantidad de elementos en el buffer
	@rtype: int"""
	if receptionBuffer.qsize() == None: return 0
	else: return receptionBuffer.qsize()

def connectGprs():
	ttyUSBPattern = re.compile('ttyUSB[0-9]+')
	lsDevProcess = subprocess.Popen(['ls', '/dev/'], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
	lsDevOutput, lsDevError = lsDevProcess.communicate()
	ttyUSBDevices = ttyUSBPattern.findall(lsDevOutput)
	# Se detectaron dispositivos USB conectados
	if len(ttyUSBDevices) > 0:
		if gprsInstance.serialPort not in ttyUSBDevices:
			wvdialProcess = subprocess.Popen('wvdialconf', stdout = subprocess.PIPE, stderr = subprocess.PIPE)
			wvdialOutput, wvdialError = wvdialProcess.communicate()
			ttyUSBPattern = re.compile('ttyUSB[0-9]+<Info>')
			modemsList = ttyUSBPattern.findall(wvdialError)
			if len(modemsList) > 0:
				gprsSerialPort = modemsList[0].replace('<Info>','')
				if gprsInstance.connect(gprsSerialPort):
					gprsInstance.isActive = True
					gprsInfo = gprsSerialPort + ' - ' + gprsInstance.local_IP_Address
					gprsThread = threading.Thread(target = gprsInstance.verifyConnection, name = 'gprsVerifyConnection')
					gprsThread.start()
					logger.write('INFO','[GPRS] Listo para usarse (' + gprsInfo + ').')
					return True
				else:
					logger.write('WARNING','[GPRS] Error al intentar conectar con la red GPRS.')
					gprsInstance.serialPort = None
					gprsInstance.closePort()
					return False
		# Si llegamos acá es porque el módem ya esta funcionando en modo GPRS
		elif gprsInstance.getStatus():
			logger.write('WARNING', '[GPRS] El módem ya está funcionando en modo GPRS!')
			return True
	else:
		logger.write('WARNING', '[GPRS] No se encontró ningún módem para trabajar en modo GPRS.')
		return False

def disconnectGprs():
	return gprsInstance.disconnect()

def close():
	"""Se cierran los componentes del sistema, unicamente los abiertos previamente"""
	global receptionBuffer, transmissionBuffer, checkerInstance, transmitterInstance
	global smsInstance, networkInstance, gprsInstance, bluetoothInstance, emailInstance
	
	del receptionBuffer
	del transmissionBuffer

	checkerInstance.isActive = False
	checkerInstance.join()
	del checkerInstance
	
	transmitterInstance.isActive = False
	transmitterInstance.notEmpty.acquire() # Por si esta a la espera de mensajes
	transmitterInstance.notEmpty.notify()
	transmitterInstance.notEmpty.release()
	transmitterInstance.join()
	del transmitterInstance
	
	del smsInstance
	del networkInstance
	del gprsInstance
	del emailInstance
	del bluetoothInstance