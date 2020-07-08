import numpy as np
import time
import socket
import struct
import os

""" 
Write information to the Star Camera data file.
Inputs: None.
Outputs: None. Writes information to the file and closes file.
"""
def prepareBackupFile():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    data_file = open(script_dir + os.path.sep + "data.txt", "a+")
    header = ["C time (sec),GMT,RA (deg),DEC (deg),FR (deg),PS (arcsec/px),IR (deg),ALT (deg),AZ (deg)\n"]
    data_file.writelines(header)
    data_file.close()

"""
Write telemetry to backup data file for the user.
Inputs: Raw, unpacked Star Camera data.
Outputs: None. Writes information to file and closes.
"""
def backupStarCamData(StarCam_data):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    # write this data to a .txt file (always updating)
    data_file = open(script_dir + os.path.sep + "data.txt", "a+")
    unpacked_data = struct.unpack_from("dddddddddddddiiiiiiiiddiiiiiiiiiiiiiifiii", StarCam_data)
    text = ["%s," % str(unpacked_data[1]), "%s," % str(time.asctime(time.gmtime(unpacked_data[1]))), 
            "%s," % str(unpacked_data[6]), "%s," % str(unpacked_data[7]), "%s," % str(unpacked_data[8]), 
            "%s," % str(unpacked_data[9]), "%s," % str(unpacked_data[10]), "%s," % str(unpacked_data[11]),
            "%s\n" % str(unpacked_data[12])]
    data_file.writelines(text)
    data_file.close()

"""
Create a socket with the Star Camera server on which to receive telemetry and send commands.
Inputs: Known IP address of Star Camera computer.
Outputs: The Star Camera socket, the Star Camera IP, and the Star Camera port.
"""
def establishStarCamSocket(StarCam_IP):
    # establish port with Star Camera
    StarCam_PORT = 8000
    server_addr = (StarCam_IP, StarCam_PORT)
    # TCP socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(server_addr)
    print("Connected to %s" % repr(server_addr))
    return (s, StarCam_IP, StarCam_PORT)

"""
Receive telemetry and camera settings from Star Camera.
Inputs: The socket to communicate with the camera.
Outputs: Raw, unpacked Star Camera data.
"""
def getStarCamData(client_socket):
    # number of expected bytes is hard-coded
    (StarCam_data, _) = client_socket.recvfrom(224)   
    backupStarCamData(StarCam_data)
    print("Received Star Camera data.")
    return StarCam_data

"""
Receive image bytes from camera.
Inputs: The socket to communicate with the camera.
Outputs: Raw image bytes.
"""
def getStarCamImage(client_socket):
    image_bytes = bytearray()
    # image dimensions
    n = 1936*1216
    while (len(image_bytes) < n):
        packet = client_socket.recv(n - len(image_bytes)) 
        if not packet:
            return None
        image_bytes.extend(packet)
    print("Received Star Camera image bytes. Total number is bytes is:", 
          len(image_bytes))
    return image_bytes