"""
User script that creates GUI for the user and takes his/her command to know the current StarCamera
data. Communicates with listening.py to receive this current data.
"""
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
import sys
import time
import numpy as np
import struct
import socket
import os
import listening_final
import ipaddress
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
import pyqtgraph.ptime as ptime

# path
scriptDir = os.path.dirname(os.path.realpath(__file__))
# camera image dimensions in pixels
CAMERA_WIDTH = 1936 
CAMERA_HEIGHT = 1216
# time limit for progress bar of telemetry-timing thread
TIME_LIMIT = 20 
# possible aperture values on Star Camera (Canon EF-232)
aperture_range = ['2.8', '3.0', '3.3', '3.6', '4.0', '4.3', '4.7', '5.1', '5.6', '6.1', '6.7', '7.3', '8.0', '8.7', '9.5', '10.3', '11.3', '12.3', '13.4', '14.6', '16.0', 
                  '17.4', '19.0', '20.7', '22.6', '24.6', '26.9', '29.3', '32.0']

class Counter(QThread):
    """ Runs a counter thread to keep track of how long telemetry takes to arrive. """
    countChanged = pyqtSignal(int)

    def run(self):
        self.count = 0
        while self.count < TIME_LIMIT:
            self.count += 1
            time.sleep(1) # units: seconds
            self.countChanged.emit(self.count)

class Slider(QSlider):
    """ Simple class for a slider bar for focus and aperture commanding. """
    minimumChanged = pyqtSignal(int)
    maximumChanged = pyqtSignal(int)

    def setMinimum(self, minimum):
        self.minimumChanged.emit(minimum)
        super(Slider, self).setMinimum(minimum)

    def setMaximum(self, maximum):
        self.maximumChanged.emit(maximum)
        super(Slider, self).setMaximum(maximum)

    def setPrevValue(self):
        self.previous_value = self.value()
        self.setStyleSheet("QSlider::groove:horizontal { \
        border: 1px solid #bbb; \
        background: white; \
        height: 5px; \
        border-radius: 4px; \
        } \
        \n \
        QSlider::sub-page:horizontal { \
        background: qlineargradient(x1: 0, y1: 0,    x2: 0, y2: 1, \
            stop: 0 #66e, stop: 1 #bbf); \
        background: qlineargradient(x1: 0, y1: 0.2, x2: 1, y2: 1, \
            stop: 0 #bbf, stop: 1 #2A82DA); \
        border: 1px solid #2A82DA; \
        height: 10px; \
        border-radius: 4px; \
        } \
        \n \
        QSlider::add-page:horizontal { \
        background: #fff; \
        border: 1px solid #777; \
        height: 10px; \
        border-radius: 4px; \
        } \
        \n \
        QSlider::handle:horizontal { \
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, \
            stop:0 #eee, stop:1 #ccc); \
        border: 1px solid #777; \
        width: 11px; \
        margin-top: -3px; \
        margin-bottom: -3px; \
        border-radius: 4px; \
        } \
        \n \
        QSlider::handle:horizontal:hover { \
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, \
            stop:0 #fff, stop:1 #ddd); \
        border: 1px solid #444; \
        border-radius: 4px; \
        } \
        \n \
        QSlider::sub-page:horizontal:disabled { \
        background: #bbb; \
        border-color: #999; \
        } \
        \n \
        QSlider::add-page:horizontal:disabled { \
        background: #eee; \
        border-color: #999; \
        } \
        \n \
        QSlider::handle:horizontal:disabled { \
        background: #eee; \
        border: 1px solid #aaa; \
        border-radius: 4px; \
        }")
    
    def updatePrevValue(self):
        self.previous_value = self.value()

class ApertureMenu(QComboBox):
    """ Class for updating an aperture drop-down menu. """
    def setPrevValue(self):
        self.previous_value = self.currentText()
    
    def updatePrevValue(self):
        self.previous_value = self.currentText()

class CommandingThread(QThread):
    """ Thread that sends commands upon user input. """
    # signals the thread can receive from the main GUI window
    commands_sent_confirmation = pyqtSignal(int)
    socket_transport = pyqtSignal(object)

    # pull Star Camera socket information
    def getSocket(self, socket_bundle):
        self.StarCam_socket = socket_bundle[0]
        self.StarCam_IP = socket_bundle[1]
        self.StarCam_PORT = socket_bundle[2]

    # transmit the commands via TCP to the Star Camera
    def sendCommands(self, data_to_send):   
        self.StarCam_socket.sendto(data_to_send, (self.StarCam_IP, self.StarCam_PORT))
        print("Commands sent to camera. Will display confirmation.")
        # display a little pop-up window to user to confirm transmission of commands
        self.displayConfirmation()

    # function to design commands confirmation pop-up window
    def displayConfirmation(self):
        # let user know their commands were sent
        msg = QMessageBox()
        msg.setWindowTitle("Star Camera")
        scriptDir = os.path.dirname(os.path.realpath(__file__))
        msg.setWindowIcon(QIcon(scriptDir + os.path.sep + "SO_icon.png"))
        msg.setIcon(QMessageBox.Information)
        msg.setText("Commands sent to the Star Camera. \n\nNote: If a command to make a static " \
                    "hot pixel map was sent, the Star Camera will make a map and then automatically " \
                    "set the flag to 0 to avoid re-making the map. The box will not remain checked " \
                    "in the Commands menu.")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

class TelemetryThread(QThread):
    """ Thread that receives telemetry from listening.py. """
    # the signal being sent by the thread will be of type struct (object)
    telemetry_received = pyqtSignal(object)
    image_received = pyqtSignal(object)
    telemetry_received_for_timer = pyqtSignal(bool)
    socket_transport = pyqtSignal(object)

    # function to get the socket and attach it as an attribute to the thread
    def getSocket(self, socket_bundle):
        self.StarCam_socket = socket_bundle[0]
        self.StarCam_IP = socket_bundle[1]
        self.StarCam_PORT = socket_bundle[2]
        
    # function of operation for telemetry thread
    def run(self):
        # continue receiving and updating telemetry from listening.py infinitely
        while True: 
            telemetry = listening_final.getStarCamData(self.StarCam_socket)
            # emit this telemetry to the main GUI thread
            self.telemetry_received.emit(telemetry)
            self.telemetry_received_for_timer.emit(True)
            # receive and emit image data to the main GUI thread
            image = listening_final.getStarCamImage(self.StarCam_socket)
            self.image_received.emit(image)

class GUI(QDialog):
    """ Main GUI window class. """
    # signals the main window can send to the worker threads
    send_commands_signal = pyqtSignal(object)
    socket_transport = pyqtSignal(object)

    """ Initialize the main GUI window. """
    def __init__(self, parent = None):
        super(GUI, self).__init__(parent)

        # move window to position on user's computer screen and resize it
        self.move(100, 0)
        self.setFixedSize(1800, 975)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        # create the telemetry worker thread attached to the GUI window
        self.GUItelemetry = TelemetryThread()
        # create the commanding worker thread attached to the GUI window
        self.GUIcommanding = CommandingThread() 

        # send this socket to the two worker threads (telemetry and commanding)
        self.socket_transport.connect(self.GUItelemetry.getSocket)
        self.socket_transport.connect(self.GUIcommanding.getSocket)

        # connect clicking of command button to calling the actual function to send these 
        # commands
        self.send_commands_signal.connect(self.GUIcommanding.sendCommands)
        # connect the signal emitted by the thread upon telemetry reception to the display 
        # telemetry function
        self.GUItelemetry.telemetry_received.connect(self.displayTelemetryAndCameraSettings)
        self.GUItelemetry.telemetry_received.connect(self.updatePlotData)
        # connect the signal emitted by the thread upon image reception to the display 
        # image function
        self.GUItelemetry.image_received.connect(self.updateImageData)

        # timing thread for seeing how long telemetry takes to arrive
        self.timing_thread = Counter()
        self.timing_thread.countChanged.connect(self.onCountChanged)

        # start the threads running!
        print("Starting commanding thread...")
        print("Starting the telemetry thread...")
        # for updating in image display (don't have to re-draw fully every time)
        self.first_image = 1

        # establish aesthetics of the GUI
        self.designGUI()
    
    """ Design the main GUI window. """
    def designGUI(self):
        # define the original palette of the GUI for customization purposes
        self.originalPalette = QApplication.palette()

        # put little Simons Observatory icon in the window corner
        self.setWindowIcon(QIcon(scriptDir + os.path.sep + "SO_icon.png"))

        # drop-down menu for user to switch between operating system styles
        styleComboBox = QComboBox()
        styleComboBox.addItems(QStyleFactory.keys())
        styleComboBox.setCurrentText("Fusion")
        # second drop-down menu for user to choose color scheme
        self.colorComboBox = QComboBox()
        self.colorComboBox.addItems(["Dark", "Light"])

        # label these drop-down menus
        styleLabel = QLabel("&Style")
        styleLabel.setBuddy(styleComboBox)
        colorLabel = QLabel("&Color Scheme")
        colorLabel.setBuddy(self.colorComboBox)
        # connect the user selection of options in these drop-down menus to the 
        # change style function below that alters the appearance of the GUI
        styleComboBox.activated[str].connect(self.changeStyle)
        self.colorComboBox.activated[str].connect(self.changeStyle)

        # create the telemetry section of the GUI
        self.topRightGroupBox = QGroupBox("&Telemetry")

        # set up area for live-stream of data from StarCamera
        telemetry_layout = QFormLayout()
        self.time_box = QLabel()
        telemetry_layout.addRow(QLabel("Time:"), self.time_box)
        self.ra_box = QLabel()
        telemetry_layout.addRow(QLabel("RA [deg]:"), self.ra_box)
        self.dec_box = QLabel()
        telemetry_layout.addRow(QLabel("DEC [deg]:"), self.dec_box)
        self.fr_box = QLabel()
        telemetry_layout.addRow(QLabel("FR [deg]:"), self.fr_box)
        self.ir_box = QLabel()
        telemetry_layout.addRow(QLabel("IR [deg]:"), self.ir_box)
        self.ps_box = QLabel()
        telemetry_layout.addRow(QLabel("PS [arcsec/px]:"), self.ps_box)
        self.az_box = QLabel()
        telemetry_layout.addRow(QLabel("AZ [deg]:"), self.az_box)
        self.alt_box = QLabel()
        telemetry_layout.addRow(QLabel("ALT [deg]:"), self.alt_box)

        # add progress bar to telemetry section for timing purposes
        self.progress = QProgressBar(self)
        self.progress.setGeometry(0, 0, 300, 25)
        self.progress.setMaximum(20)
        self.progress.setTextVisible(False)
        self.progress_value = self.progress.value()
        self.progress_bar_label = QLabel("Waiting for telemetry:")
        telemetry_layout.addRow(self.progress_bar_label, self.progress)
        self.topRightGroupBox.setLayout(telemetry_layout)

        # create the commanding section of the GUI
        self.topLeftGroupBox = QGroupBox("&Commands")

        self.infinity_focus_box = QComboBox()
        self.infinity_focus_box.addItems(["False", "True"])
        self.infinity_focus_box_prev_value = 0 
        self.max_aperture_box = QComboBox()
        self.max_aperture_box.addItems(["True", "False"])
        self.max_aperture_box_prev_value = 1 

        # layout to house entry fields for each command
        cmd_layout = QFormLayout()

        # logodds parameter entry field
        self.logodds = QLineEdit()
        self.logodds.setText("1.00e+08")
        self.prev_logodds = float(self.logodds.text())
        cmd_layout.addRow(QLabel("Logodds parameter:"), self.logodds)

        # latitude and longitude entry fields
        self.latitude_box = QLineEdit()
        self.latitude_box.setText("40.79243469238281")
        self.latitude_box_prev_value = float(self.latitude_box.text())
        self.longitude_box = QLineEdit()
        self.longitude_box.setText("-73.68112182617188")
        self.longitude_box_prev_value = float(self.longitude_box.text())
        self.height_box = QLineEdit()
        self.height_box.setText("57.77")
        self.height_box_prev_value = float(self.height_box.text())

        cmd_layout.addRow(QLabel("Your latitude in degrees:"), self.latitude_box)
        cmd_layout.addRow(QLabel("Your longitude in degrees:"), self.longitude_box)
        cmd_layout.addRow(QLabel("Your height (above WGS84 ellipsoid) in meters:"), self.height_box)

        # exposure entry field
        self.exposure_box = QLineEdit()
        self.exposure_box.setMaxLength(9)
        self.exposure_box.setText("700")     # default exposure time is 700 msec
        self.exposure_box_prev_value = float(self.exposure_box.text())
        cmd_layout.addRow(QLabel("Exposure time in milliseconds:"), self.exposure_box)

        # create slider for focus
        self.current_focus = 0               # dummy current focus value for before camera settings are received
        self.focus_slider = Slider(tickPosition = QSlider.TicksAbove, orientation = Qt.Horizontal)
        self.focus_slider.setValue(self.current_focus)
        # layouts for focus tools
        focus_slider_vbox = QVBoxLayout()
        focus_slider_hbox = QHBoxLayout()
        focus_slider_hbox.setContentsMargins(0, 0, 0, 0)
        focus_slider_vbox.setContentsMargins(0, 0, 0, 0)
        focus_slider_vbox.setSpacing(1)
        # label the focus slider
        label_minimum = QLabel(alignment = Qt.AlignLeft)
        self.focus_slider.minimumChanged.connect(label_minimum.setNum)
        label_maximum = QLabel(alignment = Qt.AlignRight)
        self.focus_slider.maximumChanged.connect(label_maximum.setNum)
        self.focus_slider_label = QLabel(str(self.focus_slider.value()), alignment = Qt.AlignCenter)
        self.focus_slider.valueChanged.connect(self.focus_slider_label.setNum)
        # function called upon initialization of focus slider to establish previous_value attribute 
        # for reference later
        self.focus_slider.setPrevValue()
        # add all these widgets to the focus layouts
        focus_slider_vbox.addWidget(self.focus_slider)
        focus_slider_vbox.addLayout(focus_slider_hbox)
        focus_slider_hbox.addWidget(label_minimum, Qt.AlignLeft)
        focus_slider_hbox.addWidget(self.focus_slider_label, Qt.AlignCenter)
        focus_slider_hbox.addWidget(label_maximum, Qt.AlignRight)
        # add these focus layouts to the main commanding layout
        cmd_layout.addRow(QLabel("Change focus:"))
        cmd_layout.addRow(focus_slider_vbox)
        cmd_layout.addRow(QLabel("Set focus to infinity?"), self.infinity_focus_box)

        # create drop-down menu for aperture (if you can implement a slider with non-uniform spacing, 
        # do that here)
        self.aperture_menu = ApertureMenu()
        self.aperture_menu.addItems(aperture_range)
        self.aperture_menu.setPrevValue()
        cmd_layout.addRow(QLabel("Set aperture to:"), self.aperture_menu)
        cmd_layout.addRow(QLabel("Set aperture to maximum?"), self.max_aperture_box)

        # create entry fields for each of the blob parameters
        blob_params = QFormLayout()
        blob_params_label = QLabel()
        blob_params_label.setText("Blob parameters:")
        # check box for making and using static hot pixel maps
        self.make_staticHP = QCheckBox("Make new static hot pixel map")
        # default is not to make a new static hot pixel map (presumed that one has already
        # been made and tested)
        self.make_staticHP.setChecked(False) 
        self.prev_makeHP = 0
        self.use_staticHP = QCheckBox("Use static hot pixel map")
        self.prev_useHP = 1
        # default is to always use static hot pixel map
        self.use_staticHP.setChecked(True)
        blob_params.addRow(self.make_staticHP)
        blob_params.addRow(self.use_staticHP)

        # different blob parameters...
        self.new_spike_limit = QLineEdit()
        self.new_spike_limit.setText("3.0")
        self.prev_spike_limit = float(self.new_spike_limit.text())
        blob_params.addRow(QLabel("Spike limit:"), self.new_spike_limit)

        self.new_dynamic_hot_pixels = QComboBox()
        self.new_dynamic_hot_pixels.addItems(["On", "Off"])
        self.prev_dynamic_hot_pixels = 1
        blob_params.addRow(QLabel("Dynamic hot pixels:"), self.new_dynamic_hot_pixels)

        self.new_r_smooth = QLineEdit()
        self.new_r_smooth.setText("2.0")
        self.prev_r_smooth = float(self.new_r_smooth.text())
        blob_params.addRow(QLabel("Image smooth filter radius:"), self.new_r_smooth)

        self.new_high_pass_filter = QComboBox()
        self.new_high_pass_filter.addItems(["Off", "On"])
        self.prev_high_pass_filter = 0 
        blob_params.addRow(QLabel("High pass filter:"), self.new_high_pass_filter)

        self.new_r_high_pass_filter = QLineEdit()
        self.new_r_high_pass_filter.setText("10")
        self.prev_r_high_pass_filter = float(self.new_r_high_pass_filter.text())
        blob_params.addRow(QLabel("Image high pass filter radius:"), self.new_r_high_pass_filter)

        self.new_centroid_search_border = QLineEdit()
        self.new_centroid_search_border.setText("1.0")
        self.prev_centroid_value = float(self.new_centroid_search_border.text())
        blob_params.addRow(QLabel("Centroid search border:"), self.new_centroid_search_border)

        self.new_filter_return_image = QComboBox()
        self.new_filter_return_image.addItems(["False", "True"])
        self.prev_filter_return_image = 0
        blob_params.addRow(QLabel("Filter returned image?:"), self.new_filter_return_image)

        self.new_n_sigma = QLineEdit()
        self.new_n_sigma.setText("2.0")
        self.prev_n_sigma = float(self.new_n_sigma.text())
        blob_params.addRow(QLabel("Blob threshold = n*sigma + mean:"), self.new_n_sigma)

        self.new_unique_star_spacing = QLineEdit()
        self.new_unique_star_spacing.setText("15")
        self.prev_unique_star_spacing = float(self.new_unique_star_spacing.text())
        blob_params.addRow(QLabel("Spacing between unique stars:"), self.new_unique_star_spacing)

        # add all these blob parameters layout to main commanding layout
        cmd_layout.addRow(blob_params_label, blob_params)

        # button to send commands when user clicks it
        self.cmd_button = QPushButton("Send Commands")
        self.cmd_button.setToolTip("Send your commands to Star Camera")
        self.cmd_button.clicked.connect(self.commandButtonClicked)
        cmd_layout.addRow(self.cmd_button)
        # add commanding layout to layout of main left box on GUI window
        self.topLeftGroupBox.setLayout(cmd_layout) 

        # create section for displaying StarCamera photos
        self.photoTab = QTabWidget()
        # interpret image data as row-major instead of col-major
        pg.setConfigOptions(imageAxisOrder = "row-major")
        # create window with GraphicsView widget
        self.image_widget = pg.GraphicsLayoutWidget()
        self.image_widget.setWindowTitle("Star Camera Image")
        self.image_view = self.image_widget.addViewBox()
        # show widget alone in its own window
        self.image_widget.show() 
        # create image item
        self.img_item = pg.ImageItem(border = "w")
        self.image_view.addItem(self.img_item)
        self.photoTab.addTab(self.image_widget, "&Images")

        # lists to append telemetry to upon arrival
        self.time, self.alt, self.az, self.ra, self.dec, self.fr, self.ir, self.ps = [], [], [], [], [], [], [], []
        # create pyqtgraph plot widgets
        self.alt_graph_widget = pg.PlotWidget()
        self.az_graph_widget = pg.PlotWidget()
        self.ra_graph_widget = pg.PlotWidget()
        self.dec_graph_widget = pg.PlotWidget()
        self.fr_graph_widget = pg.PlotWidget()
        self.ps_graph_widget = pg.PlotWidget()
        self.ir_graph_widget = pg.PlotWidget()
        # add grid
        self.alt_graph_widget.showGrid(x = True, y = True)
        self.az_graph_widget.showGrid(x = True, y = True)
        self.ra_graph_widget.showGrid (x = True, y = True)
        self.dec_graph_widget.showGrid(x = True, y = True)
        self.fr_graph_widget.showGrid(x = True, y = True)
        self.ps_graph_widget.showGrid(x = True, y = True)
        self.ir_graph_widget.showGrid(x = True, y = True)
        # add all tabs/graphs to the GUI photo section
        self.photoTab.addTab(self.alt_graph_widget, "&Altitude")
        self.photoTab.addTab(self.az_graph_widget, "&Azimuth")
        self.photoTab.addTab(self.ra_graph_widget, "&RA")
        self.photoTab.addTab(self.dec_graph_widget, "&DEC")
        self.photoTab.addTab(self.fr_graph_widget, "&FR")
        self.photoTab.addTab(self.ps_graph_widget, "&PS")
        self.photoTab.addTab(self.ir_graph_widget, "&IR")

        # create the top section of the GUI
        topLayout = QVBoxLayout()

        # place for entering IP address of StarCamera computer (known)
        self.ip_input = QLineEdit()
        font = self.ip_input.font()
        font.setPointSize(11)
        self.ip_input.setFont(font)
        ip_layout = QHBoxLayout()
        ip_sublayout = QFormLayout()
        ip_label = QLabel()
        ip_label.setFont(QFont('Helvetica', 11, QFont.DemiBold))
        ip_label.setText("Enter the Star Camera IP address:")
        ip_sublayout.addRow(ip_label, self.ip_input)
        ip_layout.addLayout(ip_sublayout)
        self.ip_button = QPushButton("Start")
        self.ip_button.clicked.connect(self.startButtonClicked)
        self.ip_button.setDefault(True)
        self.ip_button.setFont(QFont('Helvetica', 11, QFont.DemiBold))
        self.ip_button.resize(100, 30)
        ip_layout.addWidget(self.ip_button)

        # add style customization widgets to this top layout
        topLayout.addWidget(styleLabel)
        topLayout.addWidget(styleComboBox)
        topLayout.addWidget(colorLabel)
        topLayout.addWidget(self.colorComboBox)
        topLayout.addLayout(ip_layout)
        # instructions for user operating the Star Camera GUI
        instructions = QLabel()
        text = "Enter your commands to control the Star Camera. The default latitude and longitude " \
               "are those of RM 1E3 of the Devlin Lab in David Rittenhouse Laboratory (DRL); " \
               "if you are at a different location, " \
               "specify your latitude and longitude in their entry fields. To change the focus to a " \
               "certain count, specify the position on the 'Set focus to:' scrollbar. To change the " \
               "aperture to one of the camera's f-numbers, select one from the drop-down menu. 2.8 is " \
               "maximum aperture (fully open) and 32.0 is minimum aperture (fully closed). If you would " \
               "like to set the focus to infinity or the aperture to maximum, select true in the drop-down " \
               "menu(s). For changing the blob-finding parameters, enter the desired values in the proper " \
               "entry field. If you are taking dark images and wish to re-make the static hot pixel mask, check " \
               "the box, though this is not recommended (one has been made and tested previously). To turn this " \
               "static hot pixel map on and off, check the 'use' button. These checkboxes will update to the current " \
               "Star Camera settings on every iteration the telemetry is received from the camera. " \
               "The 'Logodds' parameter controls how many false positives Astrometry generates (the lower the " \
               "number, the more false positives allowed). We suggest keeping this parameter at the default value " \
               "unless you are absolutely sure of changing it. For changing the exposure, only enter integer values " \
               "between 1 millisecond and 1 second. The camera will adjust the exposure to a decimal value, which " \
               "will be displayed, but only enter commands as integers. Once the commands you wish to send are entered, " \
               "press the 'Send Commands' button. Left click on the graphics to export data and save as files." 
        instructions.setFont(QFont('Helvetica', 9, QFont.Light))
        instructions.setText(text)
        instructions.setWordWrap(True)
        # add these instructions to the top layout
        topLayout.addWidget(instructions)

        # add main portions of GUI to the main GUI layout
        mainLayout = QGridLayout()
        mainLayout.addWidget(self.topLeftGroupBox, 1, 0)
        mainLayout.addWidget(self.topRightGroupBox, 1, 1)
        mainLayout.addWidget(self.photoTab, 1, 2)
        mainLayout.addLayout(topLayout, 0, 0, 1, 3)
        mainLayout.setRowStretch(1, 1)
        mainLayout.setRowStretch(2, 1)
        mainLayout.setColumnStretch(2, 2)

        # attach this main layout to the actual GUI window
        self.setLayout(mainLayout)
        self.setWindowTitle("Star Camera")
        self.changeStyle("Fusion")

    """ Change the GUI operating system style. """
    def changeStyle(self, styleName):
        QApplication.setStyle(QStyleFactory.create(styleName))
        self.changePalette()

    """ Change the GUI color palette. """
    def changePalette(self):
        if self.colorComboBox.currentText() == "Light":
            QApplication.setPalette(self.originalPalette)
            # background color for all telemetry graphs in this color scheme
            self.image_widget.setBackground("#ffffff")
            self.alt_graph_widget.setBackground("#ffffff")
            self.az_graph_widget.setBackground("#ffffff")
            self.ra_graph_widget.setBackground("#ffffff")
            self.dec_graph_widget.setBackground("#ffffff")
            self.fr_graph_widget.setBackground("#ffffff")
            self.ps_graph_widget.setBackground("#ffffff")
            self.ir_graph_widget.setBackground("#ffffff")
            # titles of graphs
            titleStyle = {"color": "#524f4f", "font-size": "30pt"}
            self.alt_graph_widget.setTitle("Observed  Altitude [deg]", **titleStyle)
            self.az_graph_widget.setTitle("Observed Azimuth [deg]", **titleStyle)
            self.ra_graph_widget.setTitle("Observed Right Ascension [deg]", **titleStyle)
            self.dec_graph_widget.setTitle("Observed  Declination [deg]", **titleStyle)
            self.fr_graph_widget.setTitle("Observed Field Rotation [deg]", **titleStyle)
            self.ps_graph_widget.setTitle("Observed Pixel Scale [arcsec/px]", **titleStyle)
            self.ir_graph_widget.setTitle("Observed Image Rotation [deg]", **titleStyle)
            # axes labels for graphs
            labelStyle = {"color": "#524f4f", "font-size": "10pt"}
            self.alt_graph_widget.setLabel("left", "Altitude [deg]", **labelStyle)
            self.alt_graph_widget.setLabel("right", "Altitude [deg]", **labelStyle)
            self.alt_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.az_graph_widget.setLabel("left", "Azimuth [deg]", **labelStyle)
            self.az_graph_widget.setLabel("right", "Azimuth [deg]", **labelStyle)
            self.az_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.ra_graph_widget.setLabel("left", "RA [deg]", **labelStyle)
            self.ra_graph_widget.setLabel("right", "RA [deg]", **labelStyle)
            self.ra_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.dec_graph_widget.setLabel("left", "DEC [deg]", **labelStyle)
            self.dec_graph_widget.setLabel("right", "DEC [deg]", **labelStyle)
            self.dec_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.fr_graph_widget.setLabel("left", "FR [deg]", **labelStyle)
            self.fr_graph_widget.setLabel("right", "FR [deg]", **labelStyle)
            self.fr_graph_widget.setLabel("bottom", "Raw time (seconds)", **labelStyle)
            self.ps_graph_widget.setLabel("left", "PS [arcsec/px]", **labelStyle)
            self.ps_graph_widget.setLabel("right", "PS [arcsec/px]", **labelStyle)
            self.ps_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.ir_graph_widget.setLabel("left", "IR [deg]", **labelStyle)
            self.ir_graph_widget.setLabel("right", "IR [deg]", **labelStyle)
            self.ir_graph_widget.setLabel("bottom", "Local sidereal time [deg]", **labelStyle)
            # create a reference to the line of each graph for updating telemetry as it arrives
            pen = pg.mkPen(color = "#524f4f", width = 3)
            self.altitude_line = self.alt_graph_widget.plot(self.time, self.alt, pen = pen, symbol = "o", symbolSize = 9, symbolBrush = ("#524f4f"))
            self.azimuth_line = self.az_graph_widget.plot(self.time, self.az, pen = pen, symbol = "o", symbolSize = 9, symbolBrush = ("#524f4f"))
            self.ra_line = self.ra_graph_widget.plot(self.time, self.ra, pen = pen, symbol = "o", symbolSize = 9, symbolBrush = ("#524f4f"))
            self.dec_line = self.dec_graph_widget.plot(self.time, self.dec, pen = pen, symbol = "o", symbolSize = 9, symbolBrush = ("#524f4f"))
            self.fr_line = self.fr_graph_widget.plot(self.time, self.fr, pen = pen, symbol = "o", symbolSize = 9, symbolBrush = ("#524f4f"))
            self.ps_line = self.ps_graph_widget.plot(self.time, self.ps, pen = pen, symbol = "o", symbolSize = 9, symbolBrush = ("#524f4f")) 
            self.ir_line = self.ir_graph_widget.plot(self.time, self.ir, pen = pen, symbol = "o", symbolSize = 9, symbolBrush = ("#524f4f"))
        elif self.colorComboBox.currentText() == "Dark":
            # define dark color palette
            self.dark_palette = QPalette()
            self.dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            self.dark_palette.setColor(QPalette.WindowText, Qt.white)
            self.dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
            self.dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            self.dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
            self.dark_palette.setColor(QPalette.ToolTipText, Qt.white)
            self.dark_palette.setColor(QPalette.Text, Qt.white)
            self.dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
            self.dark_palette.setColor(QPalette.ButtonText, Qt.white)
            self.dark_palette.setColor(QPalette.BrightText, Qt.red)
            self.dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
            self.dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            self.dark_palette.setColor(QPalette.HighlightedText, Qt.black)
            # background color for all telemetry graphs in this color scheme
            self.image_widget.setBackground("#434343")
            self.alt_graph_widget.setBackground("#434343")
            self.az_graph_widget.setBackground("#434343")
            self.ra_graph_widget.setBackground("#434343")
            self.dec_graph_widget.setBackground("#434343")
            self.fr_graph_widget.setBackground("#434343")
            self.ps_graph_widget.setBackground("#434343")
            self.ir_graph_widget.setBackground("#434343")
            # titles of graphs
            titleStyle = {"color": "#FFF", "font-size": "30pt"}
            self.alt_graph_widget.setTitle("Observed  Altitude [deg]", **titleStyle)
            self.az_graph_widget.setTitle("Observed Azimuth [deg]", **titleStyle)
            self.ra_graph_widget.setTitle("Observed Right Ascension [deg]", **titleStyle)
            self.dec_graph_widget.setTitle("Observed  Declination [deg]", **titleStyle)
            self.fr_graph_widget.setTitle("Observed Field Rotation [deg]", **titleStyle)
            self.ps_graph_widget.setTitle("Observed Pixel Scale [arcsec/px]", **titleStyle)
            self.ir_graph_widget.setTitle("Observed Image Rotation [deg]", **titleStyle)
            # axes labels for graphs
            labelStyle = {"color": "#FFF", "font-size": "10pt"}
            self.alt_graph_widget.setLabel("left", "Altitude [deg]", **labelStyle)
            self.alt_graph_widget.setLabel("right", "Altitude [deg]", **labelStyle)
            self.alt_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.az_graph_widget.setLabel("left", "Azimuth [deg]", **labelStyle)
            self.az_graph_widget.setLabel("right", "Azimuth [deg]", **labelStyle)
            self.az_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.ra_graph_widget.setLabel("left", "RA [deg]", **labelStyle)
            self.ra_graph_widget.setLabel("right", "RA [deg]", **labelStyle)
            self.ra_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.dec_graph_widget.setLabel("left", "DEC [deg]", **labelStyle)
            self.dec_graph_widget.setLabel("right", "DEC [deg]", **labelStyle)
            self.dec_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.fr_graph_widget.setLabel("left", "FR [deg]", **labelStyle)
            self.fr_graph_widget.setLabel("right", "FR [deg]", **labelStyle)
            self.fr_graph_widget.setLabel("bottom", "Raw time (seconds)", **labelStyle)
            self.ps_graph_widget.setLabel("left", "PS [arcsec/px]", **labelStyle)
            self.ps_graph_widget.setLabel("right", "PS [arcsec/px]", **labelStyle)
            self.ps_graph_widget.setLabel("bottom", "Raw time [seconds]", **labelStyle)
            self.ir_graph_widget.setLabel("left", "IR [deg]", **labelStyle)
            self.ir_graph_widget.setLabel("right", "IR [deg]", **labelStyle)
            self.ir_graph_widget.setLabel("bottom", "Local sidereal time [deg]", **labelStyle)
            # create a reference to the line of each graph for updating telemetry as it arrives
            pen = pg.mkPen(color = "w", width = 3)
            self.altitude_line = self.alt_graph_widget.plot(self.time, self.alt, pen = pen, symbol = "o", symbolsize = 8, symbolBrush = ("w"))
            self.azimuth_line = self.az_graph_widget.plot(self.time, self.az, pen = pen, symbol = "o", symbolSize = 8, symbolBrush = ("w"))
            self.ra_line = self.ra_graph_widget.plot(self.time, self.ra, pen = pen, symbol = "o", symbolSize = 8, symbolBrush = ("w"))
            self.dec_line = self.dec_graph_widget.plot(self.time, self.dec, pen = pen, symbol = "o", symbolSize = 8, symbolBrush = ("w"))
            self.fr_line = self.fr_graph_widget.plot(self.time, self.fr, pen = pen, symbol = "o", symbolSize = 8, symbolBrush = ("w"))
            self.ps_line = self.ps_graph_widget.plot(self.time, self.ps, pen = pen, symbol = "o", symbolSize = 8, symbolBrush = ("w")) 
            self.ir_line = self.ir_graph_widget.plot(self.time, self.ir, pen = pen, symbol = "o", symbolSize = 8, symbolBrush = ("w"))
            QApplication.setPalette(self.dark_palette)
        """ deprecated:
        elif self.colorComboBox.currentText() == "Nightime Blue":
            self.video_palette = QPalette()
            self.video_palette.setColor(QPalette.Window, QColor(27, 35, 38))
            self.video_palette.setColor(QPalette.WindowText, QColor(234, 234, 234))
            self.video_palette.setColor(QPalette.Base, QColor(27, 35, 38))
            self.video_palette.setColor(QPalette.AlternateBase, QColor(12, 15, 16))
            self.video_palette.setColor(QPalette.ToolTipBase, QColor(27, 35, 38))
            self.video_palette.setColor(QPalette.ToolTipText, Qt.white)
            self.video_palette.setColor(QPalette.Text, QColor(234, 234, 234))
            self.video_palette.setColor(QPalette.Button, QColor(27, 35, 38))
            self.video_palette.setColor(QPalette.ButtonText, Qt.white)
            self.video_palette.setColor(QPalette.BrightText, QColor(100, 215, 222))
            self.video_palette.setColor(QPalette.Link, QColor(126, 71, 130))
            self.video_palette.setColor(QPalette.Disabled, QPalette.Light, Qt.black)
            self.video_palette.setColor(QPalette.Disabled, QPalette.Shadow, QColor(12, 15, 16))
            QApplication.setPalette(self.video_palette)
        """

    """ Activate connections when IP address is input and start button is clicked. """
    def startButtonClicked(self):
        self.ip_input.text()
        try:
            ipaddress.ip_address(self.ip_input.text())
            # after IP address is entered and 'start' button is clicked, establish socket with the 
            # StarCamera
            try:
                self.socket_package = listening_final.establishStarCamSocket(self.ip_input.text())
                self.main_socket = self.socket_package[0]
                self.StarCam_IP = self.socket_package[1]
                self.StarCam_PORT = self.socket_package[2]
                # emit this socket to the commanding and telemetry threads
                self.socket_transport.emit(self.socket_package)
                # start the telemetry thread, now equipped with a working socket to the StarCamera
                self.GUItelemetry.start()
                self.timing_thread.start()
                # turn off the ability to re-enter the IP address in case the 'enter' button is pressed 
                # again
                self.ip_button.setEnabled(False)
            except socket.error:
                msg = QMessageBox()
                msg.setWindowTitle("Star Camera")
                msg.setWindowIcon(QIcon(scriptDir + os.path.sep + "SO_icon.png"))
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Could not establish a connection with Star Camera based on this IP address. Please enter another.")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
        except ValueError:
            msg = QMessageBox()
            msg.setWindowTitle("Star Camera")
            msg.setWindowIcon(QIcon(scriptDir + os.path.sep + "SO_icon.png"))
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Invalid IP address. Please enter another.")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()

    """ Display the telemetry and camera settings on the GUI. """
    def displayTelemetryAndCameraSettings(self, data):
        # unpack the telemetry and camera settings
        unpacked_data = struct.unpack_from("d d d d d d d d d d d d ii ii ii ii d d ii ii ii if ii i", data)

        # telemetry data parsing (always update, no matter what, since user is not interacting 
        # with this panel)
        self.time_box.setText(time.ctime(unpacked_data[0]))
        self.time.append(unpacked_data[0])
        self.ra_box.setText(str(unpacked_data[5]))
        self.ra.append(unpacked_data[5])
        self.dec_box.setText(str(unpacked_data[6]))
        self.dec.append(unpacked_data[6])
        self.fr_box.setText(str(unpacked_data[7]))
        self.fr.append(unpacked_data[7])
        self.az_box.setText(str(unpacked_data[11]))
        self.az.append(unpacked_data[11])
        self.alt_box.setText(str(unpacked_data[10]))
        self.alt.append(unpacked_data[10])
        self.ir_box.setText(str(unpacked_data[9]))
        self.ir.append(unpacked_data[9])
        self.ps_box.setText(str(unpacked_data[8]))
        self.ps.append(unpacked_data[8])

        # if newly received logodds value is different from previous value, update logodds field
        # (and do the same for all following fields for camera settings)
        if (self.prev_logodds != unpacked_data[1]):
            self.logodds.setText("{:.2e}".format(unpacked_data[1]))
            # update previous logodds attribute as well
            self.prev_logodds = unpacked_data[1]

        if (self.latitude_box_prev_value != np.degrees(unpacked_data[2])):
            self.latitude_box.setText(str(np.degrees(unpacked_data[2])))
            self.latitude_box_prev_value = np.degrees(unpacked_data[2])

        if (self.longitude_box_prev_value != unpacked_data[3]):
            self.longitude_box.setText(str(unpacked_data[3]))
            self.longitude_box_prev_value = unpacked_data[3]

        if (self.height_box_prev_value != unpacked_data[4]):
            self.height_box.setText(str(unpacked_data[4]))
            self.height_box_prev_value = unpacked_data[4]

        # reset telemetry timing thread/clock
        self.timing_thread.count = 0
        self.progress.setValue(0)
        self.progress_bar_label.setText("Waiting for telemetry: %.0f seconds" % 0)

        # display new focus information on commanding window
        self.focus_slider.setMinimum(unpacked_data[17])
        self.focus_slider.setMaximum(unpacked_data[18])

        if (self.focus_slider.previous_value != unpacked_data[13]):
            self.focus_slider.setValue(unpacked_data[13])
            self.focus_slider.updatePrevValue()

        if (self.infinity_focus_box_prev_value != unpacked_data[14]):
            self.infinity_focus_box_prev_value = unpacked_data[14]
            if (unpacked_data[14] == 1):
                self.infinity_focus_box.setCurrentText("True")
            else:
                self.infinity_focus_box.setCurrentText("False")

        # display new aperture information on commanding window
        if (self.aperture_menu.previous_value != str(unpacked_data[19]/10)):
            self.aperture_menu.setCurrentText(str(unpacked_data[19]/10))
            self.aperture_menu.updatePrevValue()

        if (self.max_aperture_box_prev_value != unpacked_data[16]):
            self.max_aperture_box_prev_value = unpacked_data[16]
            if (unpacked_data[16] == 1):
                self.max_aperture_box.setCurrentText("True")
            else:
                self.max_aperture_box.setCurrentText("False")

        if (self.exposure_box_prev_value != unpacked_data[20]):
            self.exposure_box.setText(str(unpacked_data[20]))
            self.exposure_box_prev_value = unpacked_data[20]

        # display new blob parameter information on commanding window
        if (self.prev_spike_limit != unpacked_data[22]):
            self.new_spike_limit.setText(str(unpacked_data[22]))
            self.prev_spike_limit = unpacked_data[22]

        if (self.prev_dynamic_hot_pixels != unpacked_data[23]):
            self.prev_dynamic_hot_pixels = unpacked_data[23]
            if (unpacked_data[23] == 1):
                self.new_dynamic_hot_pixels.setCurrentText("On")
            else:
                self.new_dynamic_hot_pixels.setCurrentText("Off")

        if (self.prev_r_smooth != unpacked_data[24]):
            self.new_r_smooth.setText(str(unpacked_data[24]))
            self.prev_r_smooth = unpacked_data[24]

        if (self.prev_high_pass_filter != unpacked_data[25]):
            self.prev_high_pass_filter = unpacked_data[25]
            if (unpacked_data[25] == 1):
                self.new_high_pass_filter.setCurrentText("On")
            else:
                self.new_high_pass_filter.setCurrentText("Off")

        if (self.prev_r_high_pass_filter != unpacked_data[26]):
            self.new_r_high_pass_filter.setText(str(unpacked_data[26]))
            self.prev_r_high_pass_filter = unpacked_data[26]

        if (self.prev_centroid_value != unpacked_data[27]):
            self.new_centroid_search_border.setText(str(unpacked_data[27]))
            self.prev_centroid_value = unpacked_data[27]

        if (self.prev_filter_return_image != unpacked_data[28]):
            self.prev_filter_return_image = unpacked_data[28]
            if (unpacked_data[28] == 1):
                self.new_filter_return_image.setCurrentText("True")
            else:
                self.new_filter_return_image.setCurrentText("False")
        
        if (self.prev_n_sigma != unpacked_data[29]):
            self.new_n_sigma.setText(str(unpacked_data[29]))
            self.prev_n_sigma = unpacked_data[29]

        if (self.prev_unique_star_spacing != unpacked_data[30]):
            self.new_unique_star_spacing.setText(str(unpacked_data[30]))
            self.prev_unique_star_spacing = unpacked_data[30]

        if (self.prev_makeHP != bool(unpacked_data[31])):
            self.make_staticHP.setChecked(bool(unpacked_data[31]))
            self.prev_makeHP = unpacked_data[31]

        if (self.prev_useHP != bool(unpacked_data[32])):
            self.use_staticHP.setChecked(bool(unpacked_data[32]))
            self.prev_useHP = unpacked_data[32]

    """ Update StarCamera image data. """
    def updateImageData(self, image_bytes):
        # convert bytearray to numpy array for manipulation
        image_bytes = np.array(image_bytes) 
        image_bytes = np.reshape(image_bytes, (CAMERA_HEIGHT, CAMERA_WIDTH))
        # reverse array along vertical direction (flip y coordinates)
        image_bytes = image_bytes[::-1, ::-1]
        image_bytes = image_bytes[::, ::-1]
        self.img_item.setImage(image_bytes)

    """ Update telemetry plot data on GUI. """
    def updatePlotData(self):
        # update each telemetry plot with new time and respective data points
        self.altitude_line.setData(self.time, self.alt) 
        self.azimuth_line.setData(self.time, self.az)
        self.ra_line.setData(self.time, self.ra)
        self.dec_line.setData(self.time, self.dec)
        self.fr_line.setData(self.time, self.fr)
        self.ps_line.setData(self.time, self.ps)
        self.ir_line.setData(self.time, self.ir)

    """ Update the telemetry timer as its internal clock updates. """
    def onCountChanged(self, value):
        # update the progress bar upon Counter increment
        self.progress.setValue(value)
        self.progress_bar_label.setText("Waiting for telemetry: %.0f seconds" % value)

    """ Package the commands when the 'Send Commands' button is clicked on the GUI. """
    def commandButtonClicked(self):
        # logodds parameter
        logodds = float(self.logodds.text())

        # latitude (deg) and longitude (deg)
        latitude = float(self.latitude_box.text())
        longitude = float(self.longitude_box.text())
        height = float(self.height_box.text())

        # exposure parameter
        exposure = float(self.exposure_box.text())

        # get focus information from GUI and process it as command
        set_focus_to_amount = self.focus_slider.value()
        infinity_focus_bool = self.infinity_focus_box.currentText()
        if infinity_focus_bool == "True":
            infinity_focus_bool = 1
        else: 
            infinity_focus_bool = 0

        # get aperture scale information from GUI and process it as command
        aperture_old_value_index = aperture_range.index(self.aperture_menu.previous_value)
        aperture_new_value_index = aperture_range.index(self.aperture_menu.currentText())
        set_aperture_steps = aperture_new_value_index - aperture_old_value_index

        # get aperture menu information from GUI and process it as command
        max_aperture_bool = self.max_aperture_box.currentText()
        if max_aperture_bool == "True":
            max_aperture_bool = 1
        else:
            max_aperture_bool = 0

        # get blob parameters from GUI
        if self.make_staticHP.isChecked():
            # threshold for pixel value to be a static hot pixel
            make_HP_bool = 20           
        else:
            make_HP_bool = 0
        
        if self.use_staticHP.isChecked():
            use_HP_bool = 1
        else:
            use_HP_bool = 0

        if self.new_spike_limit.text() != "":
            spike_limit_value = float(self.new_spike_limit.text())
        else:
            spike_limit_value = -1
        
        dynamic_hot_pixels_bool = self.new_dynamic_hot_pixels.currentText()
        if dynamic_hot_pixels_bool == "On":
            dynamic_hot_pixels_bool = 1
        else:
            dynamic_hot_pixels_bool = 0

        if self.new_r_smooth.text() != "":
            r_smooth_value = float(self.new_r_smooth.text())
        else:
            r_smooth_value = -1

        high_pass_filter_bool = self.new_high_pass_filter.currentText()
        if high_pass_filter_bool == "On":
            high_pass_filter_bool = 1
        else:
            high_pass_filter_bool = 0

        if self.new_r_high_pass_filter.text() != "":
            r_high_pass_filter_value = float(self.new_r_high_pass_filter.text())
        else:
            r_high_pass_filter_value = -1
        
        if self.new_centroid_search_border.text() != "":
            centroid_search_border_value = float(self.new_centroid_search_border.text())
        else: 
            centroid_search_border_value = -1

        filter_return_image_bool = self.new_filter_return_image.currentText()
        if filter_return_image_bool == "True":
            filter_return_image_bool = 1
        else:
            filter_return_image_bool = 0

        if self.new_n_sigma.text() != "":
            n_sigma_value = float(self.new_n_sigma.text())
        else:
            n_sigma_value = -1

        if self.new_unique_star_spacing.text() != "":    
            star_spacing_value = float(self.new_unique_star_spacing.text())
        else:
            star_spacing_value = -1

        # print values of commands prior to packing into struct (for testing, comment out 
        # when not)
        # print("Exposure time:", exposure)
        # print("Logodds:", logodds)
        # print("Latitude:", latitude)
        # print("Longitude:", longitude)
        # print("Focus value: ", set_focus_to_amount)
        # print("Infinity focus?: ", infinity_focus_bool)
        # print("Aperture steps: ", set_aperture_steps)
        # print("Max aperture?: ", max_aperture_bool)
        # print("Spike limit value: ", spike_limit_value)
        # print("Dynamic hot pixels?: ", dynamic_hot_pixels_bool)
        # print("Smooth radius value: ", r_smooth_value)
        # print("High pass filter?: ", high_pass_filter_bool)
        # print("High pass filter radius value: ", r_high_pass_filter_value)
        # print("Centroid search border value: ", centroid_search_border_value)
        # print("Filter return image?: ", filter_return_image_bool)
        # print("n sigma value: ", n_sigma_value)
        # print("Unique star spacing value: ", star_spacing_value)

        # package commands to send to camera
        cmds_for_camera = struct.pack('dddddffifiifffffffff', logodds, latitude, longitude, height, exposure, 
                                       set_focus_to_amount, infinity_focus_bool, set_aperture_steps,
                                       max_aperture_bool, make_HP_bool, use_HP_bool, spike_limit_value, 
                                       dynamic_hot_pixels_bool, r_smooth_value, high_pass_filter_bool, 
                                       r_high_pass_filter_value, centroid_search_border_value, 
                                       filter_return_image_bool, n_sigma_value, star_spacing_value)
        # send these commands to things listening to the send_commands_signal
        self.send_commands_signal.emit(cmds_for_camera)

        # update previous value attributes of the focus and aperture sliders
        self.focus_slider.updatePrevValue()
        self.aperture_menu.updatePrevValue() 

if __name__ == "__main__":
    # create the main window GUI
    app = QApplication(sys.argv)
    gallery = GUI()
    gallery.show()
    sys.exit(app.exec_())