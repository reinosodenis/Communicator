 # coding=utf-8

import logger
import contactList
import bluetoothReceptor

import Queue
import inspect
import threading
import bluetooth
import commentjson

CONNECTIONS = 3
TIMEOUT = 1.5

JSON_FILE = 'config.json'
JSON_CONFIG = commentjson.load(open(JSON_FILE))

class Bluetooth(object):

	bluetoothProtocol = JSON_CONFIG["BLUETOOTH"]["PROTOCOL"]
	localServiceName = JSON_CONFIG["BLUETOOTH"]["SERVICE"]
	localUUID = JSON_CONFIG["BLUETOOTH"]["UUID"]
	localSocketRFCOMM = bluetooth.BluetoothSocket
	localSocketL2CAP = bluetooth.BluetoothSocket
	localPortRFCOMM = ''
	localPortL2CAP = ''

	isActive = False
	receptionBuffer = Queue.Queue()

	def __init__(self, _receptionBuffer):
		self.receptionBuffer = _receptionBuffer
		# Creamos un nuevo socket Bluetooth que usa el protocolo de transporte especificado
		self.localSocketRFCOMM = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
		self.localSocketL2CAP = bluetooth.BluetoothSocket(bluetooth.L2CAP)
		# Enlazamos al adaptador local algun puerto disponible usando SDP (Service Discovery Protocol)
		self.localSocketRFCOMM.bind(('', bluetooth.PORT_ANY))
		self.localSocketL2CAP.bind(('', bluetooth.PORT_ANY))
		# Especificamos el numero de conexiones permitidas (todavia sin aceptar) antes de rechazar las nuevas entrantes
		self.localSocketRFCOMM.listen(CONNECTIONS)
		self.localSocketL2CAP.listen(CONNECTIONS)
		# Especificamos el tiempo de espera de conexiones (funcion 'accept')
		self.localSocketRFCOMM.settimeout(TIMEOUT)
		self.localSocketL2CAP.settimeout(TIMEOUT)
		# Especificamos el anuncio de nuestro servicio
		bluetooth.advertise_service(self.localSocketRFCOMM, self.localServiceName,
									service_id = self.localUUID,
									service_classes = [self.localUUID, bluetooth.SERIAL_PORT_CLASS],
									profiles = [bluetooth.SERIAL_PORT_PROFILE])
		bluetooth.advertise_service(self.localSocketL2CAP, self.localServiceName,
									service_id = self.localUUID,
									service_classes = [self.localUUID])
		# Almacenamos el puerto asignado por el 'bind'
		self.localPortRFCOMM = self.localSocketRFCOMM.getsockname()[1]
		self.localPortL2CAP = self.localSocketL2CAP.getsockname()[1]

	def __del__(self):
		self.localSocketRFCOMM.close()
		logger.write('INFO', '[BLUETOOTH] Objeto destruido.')

	def connect(self):
		pass #TODO

	def send(self, destinationServiceName, destinationMAC, destinationUUID, messageToSend):
		logger.write('DEBUG','[BLUETOOTH] Buscando el servicio \'%s\'.' % destinationServiceName)
		serviceMatches = bluetooth.find_service(uuid = destinationUUID, address = destinationMAC)
		if len(serviceMatches) == 0:
			logger.write('DEBUG', '[BLUETOOTH] No se pudo encontrar el servicio \'%s\'.' % destinationServiceName)
			return False
		else:
			firstMatch = serviceMatches[0]
			name = firstMatch['name']
			host = firstMatch['host']
			port = firstMatch['port']
			logger.write('DEBUG', '[BLUETOOTH] Conectando con la direccion \'%s\'...' % host)
			# Crea un nuevo socket Bluetooth que usa el protocolo de transporte especificado
			remoteSocket = bluetooth.BluetoothSocket(bluetoothProtocol)
			# Conecta el socket con el dispositivo remoto (host) sobre el puerto (channel) especificado
			remoteSocket.connect((host, port))
			logger.write('DEBUG', '[BLUETOOTH] Conectado con el dispositivo Bluetooth.')
			remoteSocket.send(messageToSend)
			# Cierra la conexion del socket cliente
			remoteSocket.send('END')
			remoteSocket.close()
			return True

	def receive(self):
		rfcommThread = threading.Thread(target = self.receiveRFCOMM, name = 'rfcommReceptor')
		rfcommThread.start()
		rfcommThread.join()

	def receiveRFCOMM(self):
		while self.isActive:
			try:
				# Espera por una conexion entrante y devuelve un nuevo socket que representa la conexion, como asi tambien la direccion del cliente
				remoteSocket, remoteAddress = self.localSocketRFCOMM.accept()
				remoteSocket.settimeout(TIMEOUT)
				logger.write('DEBUG', '[BLUETOOTH] Conexion desde \'%s\' aceptada.' % remoteAddress[0])
				threadName = 'Thread-%s' % remoteAddress[0]
				receptorThread = bluetoothReceptor.BluetoothReceptor(threadName, remoteSocket, self.receptionBuffer)
				receptorThread.isActive = True
				receptorThread.start()
			except bluetooth.BluetoothError, msg:
				# Para que el bloque 'try' (en la funcion 'accept') no se quede esperando indefinidamente
				pass
		logger.write('WARNING','[BLUETOOTH] Funcion \'%s\' terminada.' % inspect.stack()[0][3])

	def receiveL2CAP(self):
		queueThreads = Queue.Queue() # BORRAR: el cliente seria el que termina el thread creado. por lo que no haria falta
		while self.isActive:
			try:
				# Espera por una conexion entrante y devuelve un nuevo socket que representa la conexion, como asi tambien la direccion del cliente
				remoteSocket, remoteAddress = self.localSocketL2CAP.accept()
				remoteSocket.settimeout(TIMEOUT)
				logger.write('DEBUG', '[BLUETOOTH] Conexion desde \'%s\' aceptada.' % remoteAddress[0])
				threadName = 'Thread-%s' % remoteAddress[0]
				receptorThread = bluetoothReceptor.BluetoothReceptor(threadName, remoteSocket, self.receptionBuffer)
				receptorThread.isActive = True
				receptorThread.start()
				queueThreads.put(receptorThread)
			except bluetooth.BluetoothError, msg:
				# Para que el bloque 'try' (en la funcion 'accept') no se quede esperando indefinidamente
				pass
		# Terminamos los hilos creados (por la opcion 'Salir' del menu principal)
		while not queueThreads.empty():
			receptorThread = queueThreads.get()
			receptorThread.isActive = False
		logger.write('WARNING','[BLUETOOTH] Funcion \'%s\' terminada.' % inspect.stack()[0][3])
