"""
Script that receives data from the StarCamera computer. All functions are called by the GUI script.
"""
import numpy as np
import socket
import struct
import errno
import os
import random

def backupStarCamData(StarCam_data):
    # for the purposes of writing the StarCam data to a txt file
    scriptDir = os.path.dirname(os.path.realpath(__file__))
    data_file_location = scriptDir + os.path.sep + "data.txt"
    # write this data to a .txt file (always updating)
    data_file = open(data_file_location, "a+")
    unpacked_data = struct.unpack_from('Ifffffff', StarCam_data)
    text = ["%s, " % str(unpacked_data[0]), "%s, " % str(unpacked_data[1]), "%s, " % str(unpacked_data[2]), 
            "%s, " % str(unpacked_data[3]), "%s, " % str(unpacked_data[4]), "%s, " % str(unpacked_data[5]), 
            "%s" % str(unpacked_data[6]), "%s\n" % str(unpacked_data[7])]
    data_file.writelines(text)
    data_file.close()

def establishStarCamSocket(StarCam_IP):
    # establish port (hard-coded; both user computer and StarCamera computer have to agree on this
    # number!)
    StarCam_PORT = 8000
    server_addr = (StarCam_IP, StarCam_PORT)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(server_addr)
    print("Connected to %s" % repr(server_addr))
    return (s, StarCam_IP, StarCam_PORT)

def getStarCamData(clientSock_with_StarCam):
    # receive StarCamera telemetry data and camera settings (number of expected bytes is hard-coded in)
    (StarCam_data, _) = clientSock_with_StarCam.recvfrom(220)   
    # write data to backup txt file
    # backupStarCamData(StarCam_data)
    print("Received Star Camera data.")
    return StarCam_data

def getStarCamImage(clientSock_with_StarCam):
    image_bytes = bytearray()
    n = 1936*1216
    while (len(image_bytes) < n):
        packet = clientSock_with_StarCam.recv(n - len(image_bytes)) 
        if not packet:
            return None
        image_bytes.extend(packet)
    print("Received Star Camera image bytes. Total number is bytes is:", len(image_bytes))
    return image_bytes