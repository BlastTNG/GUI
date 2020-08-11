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
script_dir = os.path.dirname(os.path.realpath(__file__))
# camera image dimensions in pixels
CAMERA_WIDTH = 1936 
CAMERA_HEIGHT = 1216
# time limit for progress bar of telemetry-timing thread
TIME_LIMIT = 30 
# possible aperture values on Star Camera (Canon EF f/2.8)
aperture_range = ["2.8", "3.0", "3.3", "3.6", "4.0", "4.3", "4.7", "5.1", "5.6", "6.1", "6.7", "7.3", "8.0", "8.7", 
                  "9.5", "10.3", "11.3", "12.3", "13.4", "14.6", "16.0", "17.4", "19.0", "20.7", "22.6", "24.6", "26.9",
                  "29.3", "32.0"]

"""
Class that runs a counter thread to keep track of how long telemetry takes to arrive from the Star Camera.
Attributes: count_changed (a signal that transmits current clock count) and the count itself.
Methods: run(), which increments the counter and emits its value.
"""
class Counter(QThread):
    count_changed = pyqtSignal(int)

    def run(self):
        self.count = 0
        while self.count < TIME_LIMIT and (not self.isInterruptionRequested()):
            self.count += 1
            time.sleep(1)
            self.count_changed.emit(self.count)

    def reset(self):
        self.requestInterruption()
        self.count = 0


"""
Class for a horizontal slider the user can adjust.
Attributes: minimum_changed (a signal that encodes the minimum of the slider), maximum_changed (signal that encodes 
the maximum of the slider), and previous value of the slider.
Methods: setMinimum() - change the minimum of the slider; setMaximum() - change the maximum of the slider; 
setPrevValue() - establish the previous value holder of the slider; updatePrevValue() - change the previous value 
holder.
"""
class Slider(QSlider):
    minimum_changed = pyqtSignal(int)
    maximum_changed = pyqtSignal(int)

    def setMinimum(self, minimum):
        self.minimum_changed.emit(minimum)
        super(Slider, self).setMinimum(minimum)

    def setMaximum(self, maximum):
        self.maximum_changed.emit(maximum)
        super(Slider, self).setMaximum(maximum)

    def setPrevValue(self):
        self.previous_value = self.value()
        # style slider bar while we're at it
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

"""
Class for a drop-down menu.
Attributes: previous value of the menu.
Methods: setPrevValue() - set the previous value of the menu initially; updatePrevValue() - update the previous value
of the menu.
"""
class ApertureMenu(QComboBox):
    def setPrevValue(self):
        self.previous_value = self.currentText()
    
    def updatePrevValue(self):
        self.previous_value = self.currentText()

"""
Class for a thread that sends commands to the Star Camera.
Attributes: a confirmation that commands were sent, a signal carrying the Star Camera socket information, and the 
socket information once established.
Methods: getSocket() - get the socket information and attach it to the thread as attributes; sendCommands() - send the
packaged commands to the Star Camera; displayConfirmation() - display a pop-up window for the user confirming their
commands were sent.
"""
class CommandingThread(QThread):
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
        self.StarCam_socket.sendto(data_to_send, (self.StarCam_IP, 
                                                  self.StarCam_PORT))
        print("Commands sent to camera. Will display confirmation.")
        self.displayConfirmation()

    # function to design commands confirmation pop-up window
    def displayConfirmation(self):
        msg = QMessageBox()
        msg.setWindowTitle("Star Camera")
        script_dir = os.path.dirname(os.path.realpath(__file__))
        msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
        msg.setIcon(QMessageBox.Information)
        msg.setText("Commands sent to the Star Camera. \n\nNote: If a command to make a static hot pixel map was " \
                    "sent, the Star Camera will make a map and then automatically set the flag to 0 to avoid " \
                    "re-making the map. The box will not remain checked in the Commands menu. \n\nNote: If you " \
                    "entered other lens adapter commands along with re-performing auto-focus, they will be ignored " \
                    "to prevent driver issues (e.g. aperture, exposure).")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

"""
Class for a thread that perpetually receives telemetry and current camera settings.
Attributes: signals for telemetry & image reception and transmitting the socket.
Methods: getSocket() - get socket information and attach it to the thread and the run() function, which perpetually 
loops to receive data as it comes in from the camera.
"""
class TelemetryThread(QThread):
    # the signal being sent by the thread will be of type struct (object)
    telemetry_received = pyqtSignal(object)
    image_received = pyqtSignal(object)
    telemetry_received_for_timer = pyqtSignal(bool)
    socket_transport = pyqtSignal(object)
    disconnected = pyqtSignal(bool)

    # function to get the socket and attach it as an attribute to the thread
    def getSocket(self, socket_bundle):
        self.StarCam_socket = socket_bundle[0]
        self.StarCam_IP = socket_bundle[1]
        self.StarCam_PORT = socket_bundle[2]
        
    # function of operation for telemetry thread
    def run(self):
        while not self.isInterruptionRequested(): 
            telemetry = listening_final.getStarCamData(self.StarCam_socket)
            if isinstance(telemetry, type(None)):
                self.disconnected.emit(True)
                break
            # emit this telemetry to the main GUI thread
            self.telemetry_received.emit(telemetry)
            self.telemetry_received_for_timer.emit(True)
            # receive and emit image data to the main GUI thread
            image = listening_final.getStarCamImage(self.StarCam_socket) 
            if isinstance(image, type(None)):
                self.disconnected.emit(True)
                break
            else:
                self.image_received.emit(image)

"""
Class for creating the main GUI window. Methods are described below before each one.
"""
class GUI(QDialog):
    # signals the main window can send to the worker threads
    send_commands_signal = pyqtSignal(object)
    socket_transport = pyqtSignal(object)

    """ 
    Initialize the main GUI window. 
    Inputs: self, no parents.
    Outputs: None.
    """
    def __init__(self, parent = None):
        super(GUI, self).__init__(parent)

        # move window to position on user's computer screen and resize it
        self.move(100, 0)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)

        self.GUItelemetry = TelemetryThread()
        self.GUIcommanding = CommandingThread() 

        # send this socket to the two worker threads (telemetry and commanding)
        self.socket_transport.connect(self.GUItelemetry.getSocket)
        self.socket_transport.connect(self.GUIcommanding.getSocket)

        # connect clicking of command button to calling the actual function to 
        # send these commands
        self.send_commands_signal.connect(self.GUIcommanding.sendCommands)
        # connect signal emitted by thread upon telemetry reception to display 
        # telemetry function
        self.GUItelemetry.telemetry_received.connect(self.displayTelemetryAndCameraSettings)
        self.GUItelemetry.telemetry_received.connect(self.updatePlotData)
        # connect signal emitted by thread upon image reception to the display 
        # image function
        self.GUItelemetry.image_received.connect(self.updateImageData)
        self.GUItelemetry.disconnected.connect(self.resetConnection)

        self.timing_thread = Counter()
        self.timing_thread.count_changed.connect(self.onCountChanged)
        self.GUItelemetry.disconnected.connect(self.timing_thread.reset)

        # get data file ready for future reference
        listening_final.prepareBackupFile()

        # for updating in image display (don't have to re-draw fully every time)
        self.first_image = 1

        self.designGUI()
    
    """ 
    Design for the main GUI window. 
    Inputs: self.
    Outputs: None - creates the appearance of the main window.
    """
    def designGUI(self):
        # define the original palette of the GUI for customization purposes
        self.original_palette = QApplication.palette()

        # put little Simons Observatory icon in the window corner
        self.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))

        # drop-down menu for user to choose color scheme
        self.color_box = QComboBox()
        self.color_box.addItems(["Dark", "Light"])

        # label drop-down menu
        color_label = QLabel("&Color Scheme")
        color_label.setToolTip("Change the color scheme")
        color_label.setBuddy(self.color_box)
        self.color_box.activated[str].connect(self.changeStyle)

        # create the telemetry section of the GUI
        self.telemetry_group_box = QGroupBox("&Telemetry")
        self.telemetry_group_box.setMinimumWidth(375)

        telemetry_layout = QFormLayout()
        self.time_box = QLabel()
        self.time_box.setToolTip("The timestamp corresponding to the most recent image and Astrometry solution")
        telemetry_layout.addRow(QLabel("Greenwich Mean Time (GMT):"), self.time_box)
        self.ra_box = QLabel()
        self.ra_box.setToolTip("Observed right ascension (degrees)")
        telemetry_layout.addRow(QLabel("RA [deg]:"), self.ra_box)
        self.dec_box = QLabel()
        self.dec_box.setToolTip("Observed declination (degrees)")
        telemetry_layout.addRow(QLabel("DEC [deg]:"), self.dec_box)
        self.fr_box = QLabel()
        self.fr_box.setToolTip("Field rotation (degrees)")
        telemetry_layout.addRow(QLabel("FR [deg]:"), self.fr_box)
        self.ir_box = QLabel()
        self.ir_box.setToolTip("Image rotation (degrees)")
        telemetry_layout.addRow(QLabel("IR [deg]:"), self.ir_box)
        self.ps_box = QLabel()
        self.ps_box.setToolTip("Pixel scale (arcseconds per pixel)")
        telemetry_layout.addRow(QLabel("PS [arcsec/px]:"), self.ps_box)
        self.az_box = QLabel()
        self.az_box.setToolTip("Azimuth (degrees)")
        telemetry_layout.addRow(QLabel("AZ [deg]:"), self.az_box)
        self.alt_box = QLabel()
        self.alt_box.setToolTip("Altitude (degrees)")
        telemetry_layout.addRow(QLabel("ALT [deg]:"), self.alt_box)

        # add progress bar to telemetry section for timing purposes
        self.progress = QProgressBar(self)
        self.progress.setGeometry(0, 0, 300, 25)
        self.progress.setMaximum(20)
        self.progress.setTextVisible(False)
        self.progress_value = self.progress.value()
        self.progress_bar_label = QLabel("Waiting for telemetry:")
        telemetry_layout.addRow(self.progress_bar_label, self.progress)
        self.telemetry_group_box.setLayout(telemetry_layout)

        # create the commanding section of the GUI
        self.commanding_group_box = QGroupBox("&Commands")

        self.infinity_focus_box = QComboBox()
        self.infinity_focus_box.setToolTip("Automatically set the focus to infinity")
        self.infinity_focus_box.addItems(["False", "True"])
        self.infinity_focus_box_prev_value = 0 
        self.max_aperture_box = QComboBox()
        self.max_aperture_box.setToolTip("Open the aperture fully")
        self.max_aperture_box.addItems(["True", "False"])
        self.max_aperture_box_prev_value = 1 

        # layout to house entry fields for each command
        cmd_layout = QFormLayout()
        cmd_layout.setSpacing(2)

        # logodds parameter entry field
        self.logodds = QLineEdit()
        self.logodds.setToolTip("Threshold for how stringent Astrometry is with false positives - higher is more")
        self.logodds.setText("1.00e+08")
        self.prev_logodds = float(self.logodds.text())
        cmd_layout.addRow(QLabel("Logodds parameter:"), self.logodds)

        # latitude and longitude entry fields
        self.latitude_box = QLineEdit()
        self.latitude_box.setToolTip("Latitude (degrees)")
        self.latitude_box.setText("40.79243469238281")
        self.latitude_box_prev_value = float(self.latitude_box.text())
        self.longitude_box = QLineEdit()
        self.longitude_box.setToolTip("Longitude (degrees)")
        self.longitude_box.setText("-73.68112182617188")
        self.longitude_box_prev_value = float(self.longitude_box.text())
        self.height_box = QLineEdit()
        self.height_box.setToolTip("A GPS might give this as elevation or altitude")
        self.height_box.setText("57.77")
        self.height_box_prev_value = float(self.height_box.text())
        cmd_layout.addRow(QLabel("Your latitude in degrees:"), self.latitude_box)
        cmd_layout.addRow(QLabel("Your longitude in degrees:"), self.longitude_box)
        cmd_layout.addRow(QLabel("Your height (above WGS84 ellipsoid) in meters:   "), self.height_box)

        # exposure entry field
        self.exposure_box = QLineEdit()
        self.exposure_box.setToolTip("How the camera will take an image for")
        self.exposure_box.setMaxLength(9)
        self.exposure_box.setText("800")
        self.exposure_box_prev_value = float(self.exposure_box.text())
        cmd_layout.addRow(QLabel("Exposure time in milliseconds:"), self.exposure_box)

        # timeout for solving Astrometry
        self.timelimit = QSpinBox()
        self.timelimit.setToolTip("How many cycles Astrometry will iterate\nthrough before timing out (if a " \
                                  "solution is not found)")
        self.timelimit.setValue(5)
        self.prev_timelimit = 5
        # can't time out immediately or we will never solve!
        self.timelimit.setMinimum(1)
        # also don't want to try to solve forever
        self.timelimit.setMaximum(50)
        cmd_layout.addRow(QLabel("Astrometry timeout in cycles:"), self.timelimit)

        # create slider for focus
        self.current_focus = 0
        self.focus_slider = Slider(tickPosition = QSlider.TicksAbove, orientation = Qt.Horizontal)
        self.focus_slider.setToolTip("Change the focus manually")
        self.focus_slider.setValue(self.current_focus)
        # layouts for focus tools
        focus_slider_vbox = QVBoxLayout()
        focus_slider_hbox = QHBoxLayout()
        focus_slider_hbox.setContentsMargins(0, 0, 0, 0)
        focus_slider_vbox.setContentsMargins(0, 0, 0, 0)
        # label the focus slider
        label_minimum = QLabel(alignment = Qt.AlignLeft)
        self.focus_slider.minimum_changed.connect(label_minimum.setNum)
        self.label_maximum = QLabel(alignment = Qt.AlignRight)
        self.focus_slider.maximum_changed.connect(self.label_maximum.setNum)
        self.focus_slider_label = QLabel(str(self.focus_slider.value()), alignment = Qt.AlignCenter)
        self.focus_slider.valueChanged.connect(self.focus_slider_label.setNum)
        self.focus_slider.setPrevValue()
        # add all these widgets to the focus layouts
        focus_slider_vbox.addWidget(self.focus_slider)
        focus_slider_vbox.addLayout(focus_slider_hbox)
        focus_slider_hbox.addWidget(label_minimum, Qt.AlignLeft)
        focus_slider_hbox.addWidget(self.focus_slider_label, Qt.AlignCenter)
        focus_slider_hbox.addWidget(self.label_maximum, Qt.AlignRight)

        # sublayout for auto-focusing
        self.auto_focus_box = QCheckBox("&Automatic &Focusing:")
        self.auto_focus_state = 0
        # default is to assume auto-focusing has already taken place (if this 
        # is not true, GUI will update upon connection to the camera)
        self.auto_focus_box.setChecked(False)
        self.auto_focus_box.setToolTip("Re-enter auto-focusing or turn it off (and maintain current position)")
        self.auto_focus_group = QGroupBox()
        self.auto_focus_group.setContentsMargins(0, 0, 0, 0)
        # since we begin in auto-focusing by default, make sure this area is 
        # enabled (will disable it when program leaves auto-focusing)
        self.auto_focus_group.setEnabled(True)
        auto_focus_layout = QFormLayout()
        auto_focus_layout.setSpacing(2)
        # disable auto-focus subgroup if auto focus box is unchecked
        self.auto_focus_box.stateChanged.connect(self.toggleAutoFocusBox)
        self.prev_auto_focus = 0
        self.start_focus_pos = QSpinBox()
        self.start_focus_pos.setToolTip("Where to start the auto-focusing search")
        self.prev_start_focus = 0
        self.end_focus_pos = QSpinBox()
        self.end_focus_pos.setToolTip("Where to end the auto-focusing search")
        self.prev_end_focus = 0
        self.focus_step = QSpinBox()
        self.focus_step.setToolTip("How many focus positions to step by")
        self.focus_step.setMinimum(1)
        self.focus_step.setMaximum(200)
        self.prev_focus_step = 0
        self.photos_per_focus = QSpinBox()
        self.photos_per_focus.setToolTip("How many pictures to take at each focus position")
        self.photos_per_focus.setMinimum(2)
        self.photos_per_focus.setMaximum(10)
        self.photos_per_focus.setValue(3)
        self.prev_photos_per_focus = 3
        auto_focus_layout.setContentsMargins(3, 3, 3, 3)
        auto_focus_layout.addRow(self.auto_focus_box)
        auto_focus_layout.addRow(QLabel("Starting position for auto-focusing range:           "), self.start_focus_pos)
        auto_focus_layout.addRow(QLabel("Ending position for auto-focusing range:"), self.end_focus_pos)
        auto_focus_layout.addRow(QLabel("Granularity of auto-focus checker:"), self.focus_step)
        auto_focus_layout.addRow(QLabel("Number of photos to take per focus:"), self.photos_per_focus)
        self.auto_focus_group.setLayout(auto_focus_layout)

        focus_slider_vbox.addWidget(self.auto_focus_group)
        cmd_layout.addRow(QLabel("Change focus:"))
        cmd_layout.addRow(focus_slider_vbox)
        cmd_layout.addRow(QLabel("Set focus to infinity?"), self.infinity_focus_box)

        # create drop-down menu for aperture
        self.aperture_menu = ApertureMenu()
        self.aperture_menu.setToolTip("Switch between the different f-numbers of the camera")
        self.aperture_menu.addItems(aperture_range)
        self.aperture_menu.setPrevValue()
        cmd_layout.addRow(QLabel("Set aperture to:"), self.aperture_menu)
        cmd_layout.addRow(QLabel("Set aperture to maximum?"), self.max_aperture_box)

        # create entry fields for each of the blob parameters
        hp_layout = QHBoxLayout()
        self.make_staticHP = QCheckBox("Make new static hot pixel map")
        self.make_staticHP.setToolTip("Re-make the static hot pixel map - this will overwrite the current one")
        # default is not to make a new static hot pixel map (assuming one has 
        # already been made and tested)
        self.make_staticHP.setChecked(False) 
        self.prev_makeHP = 0
        self.use_staticHP = QCheckBox("Use static hot pixel map")
        self.use_staticHP.setToolTip("Use the current static hot pixel map - this is recommended")
        self.prev_useHP = 1
        # default is to always use static hot pixel map
        self.use_staticHP.setChecked(True)
        hp_layout.addWidget(self.make_staticHP, alignment = Qt.AlignCenter)
        hp_layout.addWidget(self.use_staticHP, alignment = Qt.AlignCenter)
        cmd_layout.addRow(hp_layout)

        # different blob parameters...
        self.new_spike_limit = QLineEdit()
        self.new_spike_limit.setToolTip("How aggressive the dynamic hot pixel finder is - smaller is more")
        self.new_spike_limit.setText("3.0")
        self.prev_spike_limit = float(self.new_spike_limit.text())
        cmd_layout.addRow(QLabel("Spike limit:"), self.new_spike_limit)

        self.new_dynamic_hot_pixels = QComboBox()
        self.new_dynamic_hot_pixels.setToolTip("Turn the dynamic hot pixel finder on or off")
        self.new_dynamic_hot_pixels.addItems(["On", "Off"])
        self.prev_dynamic_hot_pixels = 1
        cmd_layout.addRow(QLabel("Dynamic hot pixels:"), self.new_dynamic_hot_pixels)

        self.new_r_smooth = QLineEdit()
        self.new_r_smooth.setToolTip("Image smooth filter radius (pixels)")
        self.new_r_smooth.setText("2.0")
        self.prev_r_smooth = float(self.new_r_smooth.text())
        cmd_layout.addRow(QLabel("Image smooth filter radius:"), self.new_r_smooth)

        self.new_high_pass_filter = QComboBox()
        self.new_high_pass_filter.setToolTip("Turn the high pass filter for the image on or off")
        self.new_high_pass_filter.addItems(["Off", "On"])
        self.prev_high_pass_filter = 0 
        cmd_layout.addRow(QLabel("High pass filter:"), self.new_high_pass_filter)

        self.new_r_high_pass_filter = QLineEdit()
        self.new_r_high_pass_filter.setToolTip("Radius for high pass filtering (pixel)")
        self.new_r_high_pass_filter.setText("10")
        self.prev_r_high_pass_filter = float(self.new_r_high_pass_filter.text())
        cmd_layout.addRow(QLabel("Image high pass filter radius:"), self.new_r_high_pass_filter)

        self.new_centroid_search_border = QLineEdit()
        self.new_centroid_search_border.setToolTip("Distance from image edge from which to start star search (pixels)")
        self.new_centroid_search_border.setText("1.0")
        self.prev_centroid_value = float(self.new_centroid_search_border.text())
        cmd_layout.addRow(QLabel("Centroid search border:"), self.new_centroid_search_border)

        self.new_filter_return_image = QComboBox()
        self.new_filter_return_image.setToolTip("Return the filtered image or the unfiltered image to the user")
        self.new_filter_return_image.addItems(["False", "True"])
        self.prev_filter_return_image = 0
        cmd_layout.addRow(QLabel("Filter returned image?:"), self.new_filter_return_image)

        self.new_n_sigma = QLineEdit()
        self.new_n_sigma.setToolTip("This number times noise, plus the mean, establishes the raw pixel value " \
                                    "threshold for blobs")
        self.new_n_sigma.setText("2.0")
        self.prev_n_sigma = float(self.new_n_sigma.text())
        cmd_layout.addRow(QLabel("Blob threshold = n*sigma + mean:"), self.new_n_sigma)

        self.new_unique_star_spacing = QLineEdit()
        self.new_unique_star_spacing.setToolTip("Minimum pixel distance to distinguish two different stars")
        self.new_unique_star_spacing.setText("15")
        self.prev_unique_star_spacing = float(self.new_unique_star_spacing.text())
        cmd_layout.addRow(QLabel("Spacing between unique stars:"), self.new_unique_star_spacing)

        # button to send commands when user clicks it
        self.cmd_button = QPushButton("Send Commands")
        self.cmd_button.setToolTip("Send your commands to Star Camera")
        self.cmd_button.clicked.connect(self.commandButtonClicked)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setToolTip("Pause reception of Star Camera data")
        self.pause_button.clicked.connect(self.pauseButtonClicked)
        cmd_layout.addRow(self.cmd_button)
        cmd_layout.addRow(self.pause_button)
        # add commanding layout to layout of main left box on GUI window
        self.commanding_group_box.setLayout(cmd_layout)
        self.commanding_group_box.setMinimumWidth(600) 

        # create section for displaying photos (and add a tab for instructions)
        self.photo_tab = QTabWidget()
        self.photo_tab.setMinimumWidth(750)
        instructions = QLabel(alignment = Qt.AlignTop)
        instructions.setIndent(10)
        text = "Enter your commands to control the Star Camera. The 'logodds' parameter controls how many false " \
               "positives Astrometry allows (the lower the number, the more false positives allowed). We suggest " \
               "keeping this parameter at the default value unless you are absolutely sure of changing it. For " \
               "changing the exposure, only enter integer values between 1 millisecond and 1 second. The camera will " \
               "adjust the exposure to a decimal value, which will be displayed, but only enter commands as " \
               "integers. To change the focus to a certain count, specify the position on the 'Set focus to:' " \
               "scrollbar. You can also jump to infinity with the drop-down menu, but keep in mind that this command " \
               "takes precedence (i.e. if you issue a slider command and a set focus to infinity command, the " \
               "infinity command will be executed). By default, the camera begins in auto-focusing mode to determine " \
               "the optimal focus position given an observing session's particular conditions and then switches to " \
               "manual focusing mode, where the user can make changes and send them with the slider. If the camera " \
               "has been running before the user connects, it will have already performed auto-focusing, so the GUI " \
               "will update upon reception of the first batch of telemetry to reflect this. To re-enter " \
               "auto-focusing, check the box and specify the range of focus positions you would like to check with " \
               "the start and stop fields. Specify the step size and number of pictures to take at each focus " \
               "position as well. Increasing the number of photos will increase how long the auto-focusing process " \
               "takes. If desired, the default values may be left as is. If an auto-focusing process is aborted " \
               "mid-way (unchecking the auto-focusing flag while it is still going), the focus position will stay at " \
               "the most recent one. To change the aperture to one of the camera's f-numbers, select one from the " \
               "drop-down menu. 2.8 is maximum aperture (fully open) and 32.0 is minimum aperture (fully closed). If " \
               "you would like to set the focus to infinity or the aperture to maximum, select true in the drop-down " \
               "menu(s). For changing the blob-finding parameters, enter the desired values in the proper entry " \
               "field. If you are taking dark images and wish to re-make the static hot pixel mask, check the box, " \
               "though this is not recommended (one has been made and tested previously). To turn this static hot " \
               "pixel map on and off, check the 'use' button. These checkboxes will update to the current Star " \
               "Camera settings on every iteration the telemetry is received from the camera. Once the commands you " \
               "wish to send are entered, press the 'Send Commands' button. Left click on the graphics to export " \
               "data and save as files.\n\n*WARNING: attempting to export the image as a CSV or HDF5 will result in " \
               "an error pop-up; PyQtGraph raises an exception for trying to export their ImageItem()'s, since they " \
               "are not PlotItem()'s.\n\n**Notes about the auto-focusing curve: if you connect to the camera in the " \
               "middle of an auto-focusing process, your curve will only receive and show data from that point on. " \
               "Likewise, if you start another auto-focusing process, the existing auto-focusing curve will be  " \
               "erased, so be sure to export that data beforehand if you require it. The reception of data during " \
               "auto-focusing will be a few seconds slower." 
        instructions.setFont(QFont("Helvetica", 10, QFont.Light))
        instructions.setText(text)
        instructions.setWordWrap(True)
        self.photo_tab.addTab(instructions, "&Instructions")

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
        self.photo_tab.addTab(self.image_widget, "&Images")

        # lists to append telemetry to upon arrival
        self.time, self.alt, self.az, self.ra, self.dec, self.fr, self.ir, self.ps = [], [], [], [], [], [], [], []
        self.auto_focus, self.flux = [], []
        # create pyqtgraph plot widgets
        self.alt_graph_widget = pg.PlotWidget()
        self.az_graph_widget = pg.PlotWidget()
        self.ra_graph_widget = pg.PlotWidget()
        self.dec_graph_widget = pg.PlotWidget()
        self.fr_graph_widget = pg.PlotWidget()
        self.ps_graph_widget = pg.PlotWidget()
        self.ir_graph_widget = pg.PlotWidget()
        self.af_graph_tab = QTabWidget()
        self.af_graph_tab.setStyleSheet("QTabWidget::pane { border: 0; }")
        self.af_graph_layout = QVBoxLayout()
        self.af_graph_widget = pg.PlotWidget()
        self.af_polyfit = QPushButton("Polynomial Regression")
        self.af_polyfit.setStyleSheet("QPushButton { \
                                       background-color: green; \
                                       border-style: outset; \
                                       border-width: 2px; \
                                       border-color: beige;}")
        self.af_polyfit.clicked.connect(self.polynomialRegression)
        # for regression of auto-focusing data
        self.coefficients = []
        self.polynomial = np.poly1d(self.coefficients)
        self.af_polyfit.setToolTip("Perform a polynomial regression on the auto-focusing data")
        self.af_graph_layout.addWidget(self.af_graph_widget)
        self.af_graph_layout.addWidget(self.af_polyfit)
        self.af_graph_tab.setLayout(self.af_graph_layout)
        # add grids
        self.alt_graph_widget.showGrid(x = True, y = True)
        self.az_graph_widget.showGrid(x = True, y = True)
        self.ra_graph_widget.showGrid (x = True, y = True)
        self.dec_graph_widget.showGrid(x = True, y = True)
        self.fr_graph_widget.showGrid(x = True, y = True)
        self.ps_graph_widget.showGrid(x = True, y = True)
        self.ir_graph_widget.showGrid(x = True, y = True)
        self.af_graph_widget.showGrid(x = True, y = True)
        # add all tabs/graphs to the GUI photo section
        self.photo_tab.addTab(self.alt_graph_widget, "&Altitude")
        self.photo_tab.addTab(self.az_graph_widget, "&Azimuth")
        self.photo_tab.addTab(self.ra_graph_widget, "&RA")
        self.photo_tab.addTab(self.dec_graph_widget, "&DEC")
        self.photo_tab.addTab(self.fr_graph_widget, "&FR")
        self.photo_tab.addTab(self.ps_graph_widget, "&PS")
        self.photo_tab.addTab(self.ir_graph_widget, "&IR")
        self.photo_tab.addTab(self.af_graph_tab, "&Auto-Focus")

        # create the top section of the GUI
        top_layout = QVBoxLayout()

        # place for entering IP address of Star Camera computer
        self.ip_input = QLineEdit()
        self.port_input = QLineEdit()
        font = self.ip_input.font()
        font.setPointSize(10)
        self.ip_input.setFont(font)
        self.port_input.setFont(font)
        ip_layout = QHBoxLayout()
        ip_sublayout = QHBoxLayout()
        ip_label = QLabel()
        ip_label.setFont(QFont("Helvetica", 10, QFont.DemiBold))
        ip_label.setText("Enter the Star Camera IP address:")
        id_label = QLabel()
        id_label.setFont(QFont("Helvetica", 10, QFont.DemiBold))
        id_label.setText("Enter the server port of the camera to connect to:")
        ip_sublayout.addWidget(ip_label)
        ip_sublayout.addWidget(self.ip_input)
        spacer = QSpacerItem(40, 20, QSizePolicy.Preferred, QSizePolicy.Expanding)
        ip_sublayout.addItem(spacer)
        ip_sublayout.addWidget(id_label)
        ip_sublayout.addWidget(self.port_input)
        ip_layout.addLayout(ip_sublayout)
        self.ip_button = QPushButton("Start")
        self.ip_button.clicked.connect(self.startButtonClicked)
        self.ip_button.setDefault(True)
        self.ip_button.setFont(QFont("Helvetica", 10, QFont.DemiBold))
        ip_layout.addWidget(self.ip_button)

        # add style customization widgets to this top layout
        top_layout.addWidget(color_label)
        top_layout.addWidget(self.color_box)
        top_layout.addLayout(ip_layout)

        # add main portions of GUI to the main GUI layout
        main_layout = QGridLayout()
        main_layout.addWidget(self.commanding_group_box, 1, 0)
        main_layout.addWidget(self.telemetry_group_box, 1, 1)
        main_layout.addWidget(self.photo_tab, 1, 2)
        main_layout.addLayout(top_layout, 0, 0, 1, 3)
        main_layout.setRowStretch(1, 1)
        main_layout.setRowStretch(2, 1)
        main_layout.setColumnStretch(2, 2)

        # attach this main layout to the actual GUI window
        self.setLayout(main_layout)
        self.setWindowTitle("Star Camera")
        self.changeStyle("Fusion")

    """ 
    Change the GUI operating system style. 
    Inputs: string for the corresponding style.
    Outputs: None.
    """
    def changeStyle(self, style):
        QApplication.setStyle(QStyleFactory.create(style))
        self.changePalette()

    """ Change the GUI color palette. """
    def changePalette(self):
        regression_pen = pg.mkPen(color = "#ADFF2F", width = 3)
        self.regression = self.af_graph_widget.plot(self.auto_focus, self.polynomial(self.auto_focus), 
                                                    pen = regression_pen, symbol = "+", symbolSize = 9, 
                                                    symbolBrush = ("#ADFF2F"))
        if self.color_box.currentText() == "Light":
            QApplication.setPalette(self.original_palette)
            # background color for all telemetry graphs in this color scheme
            self.image_widget.setBackground("#ffffff")
            self.alt_graph_widget.setBackground("#ffffff")
            self.az_graph_widget.setBackground("#ffffff")
            self.ra_graph_widget.setBackground("#ffffff")
            self.dec_graph_widget.setBackground("#ffffff")
            self.fr_graph_widget.setBackground("#ffffff")
            self.ps_graph_widget.setBackground("#ffffff")
            self.ir_graph_widget.setBackground("#ffffff")
            self.af_graph_widget.setBackground("#ffffff")
            # titles of graphs
            title_style = {"color": "#524f4f", "font-size": "30pt"}
            self.alt_graph_widget.setTitle("Observed  Altitude [deg]", **title_style)
            self.az_graph_widget.setTitle("Observed Azimuth [deg]", **title_style)
            self.ra_graph_widget.setTitle("Observed Right Ascension [deg]", **title_style)
            self.dec_graph_widget.setTitle("Observed  Declination [deg]", **title_style)
            self.fr_graph_widget.setTitle("Observed Field Rotation [deg]", **title_style)
            self.ps_graph_widget.setTitle("Observed Pixel Scale [arcsec/px]", **title_style)
            self.ir_graph_widget.setTitle("Observed Image Rotation [deg]", **title_style)
            self.af_graph_widget.setTitle("Auto-focusing curve", **title_style)
            # axes labels for graphs
            label_style = {"color": "#524f4f", "font-size": "10pt"}
            self.alt_graph_widget.setLabel("left", "Altitude [deg]", **label_style)
            self.alt_graph_widget.setLabel("right", "Altitude [deg]", **label_style)
            self.alt_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.az_graph_widget.setLabel("left", "Azimuth [deg]", **label_style)
            self.az_graph_widget.setLabel("right", "Azimuth [deg]", **label_style)
            self.az_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.ra_graph_widget.setLabel("left", "RA [deg]", **label_style)
            self.ra_graph_widget.setLabel("right", "RA [deg]", **label_style)
            self.ra_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.dec_graph_widget.setLabel("left", "DEC [deg]", **label_style)
            self.dec_graph_widget.setLabel("right", "DEC [deg]", **label_style)
            self.dec_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.fr_graph_widget.setLabel("left", "FR [deg]", **label_style)
            self.fr_graph_widget.setLabel("right", "FR [deg]", **label_style)
            self.fr_graph_widget.setLabel("bottom", "Raw time (seconds)", **label_style)
            self.ps_graph_widget.setLabel("left", "PS [arcsec/px]", **label_style)
            self.ps_graph_widget.setLabel("right", "PS [arcsec/px]", **label_style)
            self.ps_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.ir_graph_widget.setLabel("left", "IR [deg]", **label_style)
            self.ir_graph_widget.setLabel("right", "IR [deg]", **label_style)
            self.ir_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.af_graph_widget.setLabel("left", "Flux [raw pixel value]", **label_style)
            self.af_graph_widget.setLabel("right", "Flux [raw pixel value]", **label_style)
            self.af_graph_widget.setLabel("bottom", "Focus position [encoder counts]", **label_style)
            # create a reference to the line of each graph for updating telemetry as it arrives
            pen = pg.mkPen(color = "#524f4f", width = 3)
            self.altitude_line = self.alt_graph_widget.plot(self.time, self.alt, pen = pen, symbol = "o", 
                                                            symbolSize = 9, symbolBrush = ("#524f4f"))
            self.azimuth_line = self.az_graph_widget.plot(self.time, self.az, pen = pen, symbol = "o", 
                                                          symbolSize = 9, symbolBrush = ("#524f4f"))
            self.ra_line = self.ra_graph_widget.plot(self.time, self.ra, pen = pen, symbol = "o", 
                                                     symbolSize = 9, symbolBrush = ("#524f4f"))
            self.dec_line = self.dec_graph_widget.plot(self.time, self.dec, pen = pen, symbol = "o", 
                                                       symbolSize = 9, symbolBrush = ("#524f4f"))
            self.fr_line = self.fr_graph_widget.plot(self.time, self.fr, pen = pen, symbol = "o", 
                                                     symbolSize = 9, symbolBrush = ("#524f4f"))
            self.ps_line = self.ps_graph_widget.plot(self.time, self.ps, pen = pen, symbol = "o", 
                                                     symbolSize = 9, symbolBrush = ("#524f4f")) 
            self.ir_line = self.ir_graph_widget.plot(self.time, self.ir, pen = pen, symbol = "o", 
                                                     symbolSize = 9, symbolBrush = ("#524f4f"))
            self.af_line = self.af_graph_widget.plot(self.auto_focus, self.flux, pen = pen, symbol = "o", 
                                                     symbolSize = 9, symbolBrush = ("#524f4f"))
        elif self.color_box.currentText() == "Dark":
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
            self.af_graph_widget.setBackground("#434343")
            # titles of graphs
            title_style = {"color": "#FFF", "font-size": "30pt"}
            self.alt_graph_widget.setTitle("Observed  Altitude [deg]", **title_style)
            self.az_graph_widget.setTitle("Observed Azimuth [deg]", **title_style)
            self.ra_graph_widget.setTitle("Observed Right Ascension [deg]", **title_style)
            self.dec_graph_widget.setTitle("Observed  Declination [deg]", **title_style)
            self.fr_graph_widget.setTitle("Observed Field Rotation [deg]", **title_style)
            self.ps_graph_widget.setTitle("Observed Pixel Scale [arcsec/px]", **title_style)
            self.ir_graph_widget.setTitle("Observed Image Rotation [deg]", **title_style)
            self.af_graph_widget.setTitle("Auto-focusing curve", **title_style)
            # axes labels for graphs
            label_style = {"color": "#FFF", "font-size": "10pt"}
            self.alt_graph_widget.setLabel("left", "Altitude [deg]", **label_style)
            self.alt_graph_widget.setLabel("right", "Altitude [deg]", **label_style)
            self.alt_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.az_graph_widget.setLabel("left", "Azimuth [deg]", **label_style)
            self.az_graph_widget.setLabel("right", "Azimuth [deg]", **label_style)
            self.az_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.ra_graph_widget.setLabel("left", "RA [deg]", **label_style)
            self.ra_graph_widget.setLabel("right", "RA [deg]", **label_style)
            self.ra_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.dec_graph_widget.setLabel("left", "DEC [deg]", **label_style)
            self.dec_graph_widget.setLabel("right", "DEC [deg]", **label_style)
            self.dec_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.fr_graph_widget.setLabel("left", "FR [deg]", **label_style)
            self.fr_graph_widget.setLabel("right", "FR [deg]", **label_style)
            self.fr_graph_widget.setLabel("bottom", "Raw time (seconds)", **label_style)
            self.ps_graph_widget.setLabel("left", "PS [arcsec/px]", **label_style)
            self.ps_graph_widget.setLabel("right", "PS [arcsec/px]", **label_style)
            self.ps_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.ir_graph_widget.setLabel("left", "IR [deg]", **label_style)
            self.ir_graph_widget.setLabel("right", "IR [deg]", **label_style)
            self.ir_graph_widget.setLabel("bottom", "Raw time [seconds]", **label_style)
            self.af_graph_widget.setLabel("left", "Flux [raw pixel value]", **label_style)
            self.af_graph_widget.setLabel("right", "Flux [raw pixel value]", **label_style)
            self.af_graph_widget.setLabel("bottom", "Focus position [encoder counts]", **label_style)
            # create a reference to the line of each graph for updating telemetry as it arrives
            pen = pg.mkPen(color = "w", width = 3)
            self.altitude_line = self.alt_graph_widget.plot(self.time, self.alt, pen = pen, symbol = "o", 
                                                            symbolsize = 8, symbolBrush = ("w"))
            self.azimuth_line = self.az_graph_widget.plot(self.time, self.az, pen = pen, symbol = "o", 
                                                          symbolSize = 8, symbolBrush = ("w"))
            self.ra_line = self.ra_graph_widget.plot(self.time, self.ra, pen = pen, symbol = "o", symbolSize = 8, 
                                                     symbolBrush = ("w"))
            self.dec_line = self.dec_graph_widget.plot(self.time, self.dec, pen = pen, symbol = "o", symbolSize = 8, 
                                                       symbolBrush = ("w"))
            self.fr_line = self.fr_graph_widget.plot(self.time, self.fr, pen = pen, symbol = "o", symbolSize = 8, 
                                                     symbolBrush = ("w"))
            self.ps_line = self.ps_graph_widget.plot(self.time, self.ps, pen = pen, symbol = "o", symbolSize = 8, 
                                                     symbolBrush = ("w")) 
            self.ir_line = self.ir_graph_widget.plot(self.time, self.ir, pen = pen, symbol = "o", symbolSize = 8, 
                                                     symbolBrush = ("w"))
            self.af_line = self.af_graph_widget.plot(self.auto_focus, self.flux, pen = pen, symbol = "o", 
                                                     symbolSize = 8, symbolBrush = ("w"))
            QApplication.setPalette(self.dark_palette)

    """ 
    Activate connections when IP address is input and start button is clicked. 
    Inputs: self.
    Outputs: None.
    """
    def startButtonClicked(self):
        try:
            ipaddress.ip_address(self.ip_input.text())
            # after IP address is entered and 'start' button is clicked, 
            # establish socket with the StarCamera
            try:
                self.socket_package = listening_final.establishStarCamSocket(self.ip_input.text(), 
                                                                             int(self.port_input.text()))
                self.main_socket = self.socket_package[0]
                self.StarCam_IP = self.socket_package[1]
                self.StarCam_PORT = self.socket_package[2]
                # emit this socket to the commanding and telemetry threads
                self.socket_transport.emit(self.socket_package)
                # start the telemetry thread
                self.GUItelemetry.start()
                self.timing_thread.start()
                # turn off the ability to re-enter the IP address in case the 
                # 'enter' button is pressed again
                self.ip_button.setEnabled(False)
            except socket.error:
                msg = QMessageBox()
                msg.setWindowTitle("Star Camera")
                msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Could not establish a connection with Star Camera based on this IP address or port. " \
                            "Please enter another or make sure the camera is on and running.")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
        except ValueError:
            msg = QMessageBox()
            msg.setWindowTitle("Star Camera")
            msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Invalid IP address or port. Please enter another.")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()

    """ 
    Toggle between enabled and disabled for the auto-focusing region of the GUI.
    Inputs: state of auto-focusing.
    Outputs: None.
    """
    def toggleAutoFocusBox(self, state):
        self.start_focus_pos.setEnabled(state == Qt.Checked)
        self.end_focus_pos.setEnabled(state == Qt.Checked)
        self.focus_step.setEnabled(state == Qt.Checked)
        self.photos_per_focus.setEnabled(state == Qt.Checked)

    """ 
    Display the telemetry and camera settings on the GUI. 
    Inputs: Raw Star Camera data.
    Outputs: None.
    """
    def displayTelemetryAndCameraSettings(self, data):
        # unpack the telemetry and camera settings
        unpacked_data = struct.unpack_from("d d d d d d d d d d d d d ii ii ii ii d d ii ii ii ii ii ii ii fi ii", data)

        # telemetry data parsing (always update for display, no matter what, since user is 
        # not interacting with this panel)
        self.time_box.setText(time.asctime(time.gmtime(unpacked_data[1])))
        self.ra_box.setText(str(unpacked_data[6]))
        self.dec_box.setText(str(unpacked_data[7]))
        self.fr_box.setText(str(unpacked_data[8]))
        self.az_box.setText(str(unpacked_data[12]))
        self.alt_box.setText(str(unpacked_data[11]))
        self.ir_box.setText(str(unpacked_data[10]))
        self.ps_box.setText(str(unpacked_data[9]))
        self.auto_focus_state = unpacked_data[24]
        # only add to auto-focusing data if we are in an auto-focusing process
        if (unpacked_data[24]) and (self.focus_slider.previous_value != unpacked_data[14]):
            self.auto_focus.append(unpacked_data[14])
            self.flux.append(unpacked_data[29])
        # if every single telemetry data point is 0, esp. pixel scale, that is before first solution of the run
        # (i.e. when camera is running for first time and auto-focusing by default)
        elif (unpacked_data[6] != 0 and unpacked_data[7] != 0 and unpacked_data[8] != 0 and unpacked_data[9] != 0 and
              unpacked_data[10] != 0 and unpacked_data[11] != 0 and unpacked_data[12] != 0):
            self.time.append(unpacked_data[1])
            self.ra.append(unpacked_data[6])
            self.dec.append(unpacked_data[7])
            self.fr.append(unpacked_data[8])
            self.az.append(unpacked_data[12])
            self.alt.append(unpacked_data[11])
            self.ir.append(unpacked_data[10])
            self.ps.append(unpacked_data[9])

        # if newly received logodds value is different from previous value, update logodds field
        # (and do the same for all following fields for camera settings)
        if (self.prev_logodds != unpacked_data[2]):
            self.logodds.setText("{:.2e}".format(unpacked_data[2]))
            self.prev_logodds = unpacked_data[2]

        if (self.latitude_box_prev_value != unpacked_data[3]):
            self.latitude_box.setText(str(unpacked_data[3]))
            self.latitude_box_prev_value = unpacked_data[3]

        if (self.longitude_box_prev_value != unpacked_data[4]):
            self.longitude_box.setText(str(unpacked_data[4]))
            self.longitude_box_prev_value = unpacked_data[4]

        if (self.height_box_prev_value != unpacked_data[5]):
            self.height_box.setText(str(unpacked_data[5]))
            self.height_box_prev_value = unpacked_data[5]

        if (self.prev_timelimit != int(unpacked_data[0])):
            self.timelimit.setValue(unpacked_data[0])
            self.prev_timelimit = unpacked_data[0]

        # reset telemetry timing thread/clock
        self.timing_thread.count = 0
        self.progress.setValue(0)
        self.progress_bar_label.setText("Waiting %.0f seconds for telemetry:" % 0)

        # display new focus information on commanding window
        self.focus_slider.setMinimum(unpacked_data[18])
        self.focus_slider.setMaximum(unpacked_data[19])
        self.start_focus_pos.setRange(unpacked_data[18] + 25, unpacked_data[19] - 25)
        self.end_focus_pos.setRange(unpacked_data[18] + 25, unpacked_data[19] - 25)

        if (self.focus_slider.previous_value != unpacked_data[14]):
            self.focus_slider.setValue(unpacked_data[14])
            self.focus_slider.updatePrevValue()

        if (self.prev_auto_focus != unpacked_data[24]):
            self.prev_auto_focus = unpacked_data[24]
            if (unpacked_data[24] == 1):
                self.auto_focus_box.setChecked(True)
            else:
                self.auto_focus_box.setChecked(False)

        if (self.prev_start_focus != unpacked_data[25]):
            self.prev_start_focus = unpacked_data[25]
            self.start_focus_pos.setValue(unpacked_data[25])

        if (self.prev_end_focus != unpacked_data[26]):
            self.prev_end_focus = unpacked_data[26]
            self.end_focus_pos.setValue(unpacked_data[26])

        if (self.prev_focus_step != unpacked_data[27]):
            self.prev_focus_step = unpacked_data[27]
            self.focus_step.setValue(unpacked_data[27])

        if (self.prev_photos_per_focus != unpacked_data[28]):
            self.prev_photos_per_focus = unpacked_data[28]
            self.photos_per_focus.setValue(unpacked_data[28])

        if (self.infinity_focus_box_prev_value != unpacked_data[15]):
            self.infinity_focus_box_prev_value = unpacked_data[15]
            if (unpacked_data[15] == 1):
                self.infinity_focus_box.setCurrentText("True")
            else:
                self.infinity_focus_box.setCurrentText("False")

        if (self.aperture_menu.previous_value != str(unpacked_data[20]/10)):
            self.aperture_menu.setCurrentText(str(unpacked_data[20]/10))
            self.aperture_menu.updatePrevValue()

        if (self.max_aperture_box_prev_value != unpacked_data[17]):
            self.max_aperture_box_prev_value = unpacked_data[17]
            if (unpacked_data[17] == 1):
                self.max_aperture_box.setCurrentText("True")
            else:
                self.max_aperture_box.setCurrentText("False")

        if (self.exposure_box_prev_value != unpacked_data[21]):
            self.exposure_box.setText(str(unpacked_data[21]))
            self.exposure_box_prev_value = unpacked_data[21]

        if (self.prev_spike_limit != unpacked_data[30]):
            self.new_spike_limit.setText(str(unpacked_data[30]))
            self.prev_spike_limit = unpacked_data[30]

        if (self.prev_dynamic_hot_pixels != unpacked_data[31]):
            self.prev_dynamic_hot_pixels = unpacked_data[31]
            if (unpacked_data[31] == 1):
                self.new_dynamic_hot_pixels.setCurrentText("On")
            else:
                self.new_dynamic_hot_pixels.setCurrentText("Off")

        if (self.prev_r_smooth != unpacked_data[32]):
            self.new_r_smooth.setText(str(unpacked_data[32]))
            self.prev_r_smooth = unpacked_data[32]

        if (self.prev_high_pass_filter != unpacked_data[33]):
            self.prev_high_pass_filter = unpacked_data[33]
            if (unpacked_data[33] == 1):
                self.new_high_pass_filter.setCurrentText("On")
            else:
                self.new_high_pass_filter.setCurrentText("Off")

        if (self.prev_r_high_pass_filter != unpacked_data[34]):
            self.new_r_high_pass_filter.setText(str(unpacked_data[34]))
            self.prev_r_high_pass_filter = unpacked_data[34]

        if (self.prev_centroid_value != unpacked_data[35]):
            self.new_centroid_search_border.setText(str(unpacked_data[35]))
            self.prev_centroid_value = unpacked_data[35]

        if (self.prev_filter_return_image != unpacked_data[36]):
            self.prev_filter_return_image = unpacked_data[36]
            if (unpacked_data[36] == 1):
                self.new_filter_return_image.setCurrentText("True")
            else:
                self.new_filter_return_image.setCurrentText("False")
        
        if (self.prev_n_sigma != unpacked_data[37]):
            self.new_n_sigma.setText(str(unpacked_data[37]))
            self.prev_n_sigma = unpacked_data[37]

        if (self.prev_unique_star_spacing != unpacked_data[38]):
            self.new_unique_star_spacing.setText(str(unpacked_data[38]))
            self.prev_unique_star_spacing = unpacked_data[38]

        if (self.prev_makeHP != bool(unpacked_data[39])):
            self.make_staticHP.setChecked(bool(unpacked_data[39]))
            self.prev_makeHP = unpacked_data[39]

        if (self.prev_useHP != bool(unpacked_data[40])):
            self.use_staticHP.setChecked(bool(unpacked_data[40]))
            self.prev_useHP = unpacked_data[40]

    """ 
    Update StarCamera image data. 
    Inputs: Raw image bytes to display.
    Outputs: None.
    """
    def updateImageData(self, image_bytes):
        # convert bytearray to numpy array for manipulation
        image_bytes = np.array(image_bytes) 
        image_bytes = np.reshape(image_bytes, (CAMERA_HEIGHT, CAMERA_WIDTH))
        # reverse array along vertical direction (flip y coordinates)
        image_bytes = image_bytes[::-1, ::-1]
        image_bytes = image_bytes[::, ::-1]
        self.img_item.setImage(image_bytes)

    """ 
    Update telemetry plot data on GUI. 
    Inputs: self.
    Outputs: None.
    """
    def updatePlotData(self):
        if (not self.auto_focus_state):
            print("New data points, so updating graphs...")
            # update each telemetry plot with new time and respective data points (if not auto-focusing)
            self.altitude_line.setData(self.time, self.alt) 
            self.azimuth_line.setData(self.time, self.az)
            self.ra_line.setData(self.time, self.ra)
            self.dec_line.setData(self.time, self.dec)
            self.fr_line.setData(self.time, self.fr)
            self.ps_line.setData(self.time, self.ps)
            self.ir_line.setData(self.time, self.ir)
        else:
            self.af_line.setData(self.auto_focus, self.flux)

    """ 
    Perform a regression of user-specified degree on the auto-focusing data. 
    Inputs: self.
    Outputs: None.
    """
    def polynomialRegression(self):  
        if not self.flux:
            msg = QMessageBox()
            msg.setWindowTitle("Star Camera")
            msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("No auto-focusing data to perform a regression on.")
            msg.exec_()
        else:
            degree = self.getDegree()
            # if user pressed cancel
            if not degree:
                return
            elif len(self.flux) < degree + 1:
                msg = QMessageBox()
                msg.setWindowTitle("Star Camera")
                msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
                msg.setStandardButtons(QMessageBox.Ok)
                msg.setIcon(QMessageBox.Warning)
                msg.setText("Not enough auto-focusing data to perform a %dth degree regression on. " \
                            "Try re-running auto-focusing with a smaller step size or decreasing " \
                            "the degree of the regression." % degree)
                msg.exec_()
            else:
                regression_pen = pg.mkPen(color = "#ADFF2F", width = 3)
                threshold = (np.max(self.flux) + np.min(self.flux))/2.0
                self.coefficients = np.polyfit(np.array(self.auto_focus)[self.flux > threshold], 
                                               np.array(self.flux)[self.flux > threshold], degree)
                self.polynomial = np.poly1d(self.coefficients)
                self.regression = self.af_graph_widget.plot(self.auto_focus, self.polynomial(self.auto_focus), 
                                                            pen = regression_pen, symbol = "+", symbolSize = 9, 
                                                            symbolBrush = ("#524f4f"))
                self.regression.setData(self.auto_focus, self.polynomial(self.auto_focus))

    """ 
    Get user's desired degree for polynomial regression. 
    Inputs: self.
    Outputs: None.
    """
    def getDegree(self):
        number, pressed = QInputDialog.getInt(self, "Auto-focusing", "Enter the degree of the regression to perform")
        if pressed:
            return number
        else:
            return 0

    """ 
    Update the telemetry timer as its internal clock updates. 
    Inputs: value to update timer & progress bar with.
    Outputs: None.
    """
    def onCountChanged(self, value):
        # update the progress bar upon Counter increment
        self.progress.setValue(value)
        self.progress_bar_label.setText("Waiting for telemetry: %.0f seconds" % value)
    
    """ 
    Display warning if certain commands are dubious. 
    Inputs: self, the name of the command, and the value associated with the command if applicable.
    Outputs: None. Displays a pop-up window.
    """
    def displayWarning(self, command_name, command_value):
        if command_name == "logodds":
            msg = QMessageBox()
            text = "Your desired logodds value is out of the range 1e6 to 1e9, the recommended range for " \
                   "prompt solution times and protection from false positives. Would you like to proceed with this " \
                   "command?"
            reply = msg.question(self, "Confirm Commands", text, QMessageBox.Yes, QMessageBox.No)

            if reply == QMessageBox.Yes:
                return 1
            else:
                return 0
        
        if command_name == "latitude":
            QMessageBox().critical(self, "Command Error", "Invalid latitude", QMessageBox.Ok)
        
        if command_name == "longitude":
            QMessageBox().critical(self, "Command Error", "Invalid longitude", QMessageBox.Ok)
        
        if command_name == "height":
            if command_value > 8850:
                msg = "You're above the highest point on Earth! Get down from there!"
                QMessageBox().critical(self, "Command Error", msg, QMessageBox.Ok)
            elif command_value < -10000:
                msg = "You're near the lowest point on Earth!"
                QMessageBox().critical(self, "Command Error", msg, QMessageBox.Ok)
        
        if command_name == "exposure":
            msg = "An exposure beyond 1000 milliseconds may lead to star smearing in the image. "\
                  "Would you like to proceed with this command?"
            reply = QMessageBox().question(self, "Confirm Commands", msg, QMessageBox.Yes, QMessageBox.No)
            if reply == QMessageBox.Yes:
                return 1
            else:
                return 0
        
        if command_name == "focus_range":
            msg = "Based on the start and stop focus positions you specified, the auto-focusing will only " \
                  "check one focus position. Would you like to continue?"
            reply = QMessageBox().question(self, "Confirm Commands", msg, QMessageBox.Yes, QMessageBox.No)
            if reply == QMessageBox.Yes:
                return 1
            else:
                return 0
        
        if command_name == "auto-focusing":
            msg = "The distance between your specified start position and end position for auto-focusing is " \
                  "not divisible by your step size. The camera will increment by your step size until the " \
                  "difference between its current position and the end focus position is less than your step " \
                  "size, in which case it will jump automatically to the end position. Continue?"
            reply = QMessageBox().question(self, "Confirm Commands", msg, QMessageBox.Yes, QMessageBox.No)
            if reply == QMessageBox.Yes:
                return 1
            else:
                return 0
        
        if command_name == "end_focus":
            msg = "Your end focus position is less than your start focus position. Re-enter your commands."
            QMessageBox().critical(self, "Command Error", msg, QMessageBox.Ok)
        
        if command_name == "r_smooth":
            msg = "Your boxcar image filter radius is greater than your high pass filter radius. Proceed with " \
                  "this command?"
            reply = QMessageBox().question(self, "Command Error", msg, QMessageBox.Yes, QMessageBox.No)
            if reply == QMessageBox.Yes:
                return 1
            else:
                return 0

    """ 
    Package the commands when the 'Send Commands' button is clicked on the GUI.
    Inputs: self.
    Outputs: None; returns if the button is clicked when the GUI is not conected to the camera
    or a command is a bad value. 
    """
    def commandButtonClicked(self):
        if not self.GUItelemetry.isRunning():
            msg = QMessageBox()
            msg.setWindowTitle("Star Camera")
            msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Connect to the Star Camera first before trying to send commands.")
            msg.exec_()
            return

        # logodds parameter
        logodds = float(self.logodds.text())
        if (logodds > 10**9) or (logodds < 10**6):
            still_send = self.displayWarning("logodds", logodds)
            if not still_send:
                self.logodds.setText("{:.2e}".format(self.prev_logodds))
                return

        # latitude (deg) and longitude (deg)
        latitude = float(self.latitude_box.text())
        if (latitude > 90) or (latitude < -90):
            self.displayWarning("latitude", latitude)
            self.latitude_box.setText(str(self.latitude_box_prev_value))
            return

        longitude = float(self.longitude_box.text())
        if (longitude > 180) or (longitude < -180):
            self.displayWarning("longitude", longitude)
            self.longitude_box.setText(str(self.longitude_box_prev_value))
            return

        # height above WGS84 ellipsoid
        height = float(self.height_box.text())
        if (height > 8850) or (height < -10000):
            self.displayWarning("height", height)
            self.height_box.setText(str(self.height_box_prev_value))
            return

        # exposure parameter
        exposure = float(self.exposure_box.text())
        if exposure > 1000:
            still_send = self.displayWarning("exposure", exposure)
            if not still_send:
                self.exposure_box.setText(str(self.exposure_box_prev_value))
                return

        # Astrometry solving timeout
        timelimit = int(self.timelimit.value())

        # get focus information from GUI and process it as command
        set_focus_to_amount = self.focus_slider.value()

        if self.auto_focus_box.isChecked():
            auto_focus_bool = 1
        else:
            auto_focus_bool = 0

        start_focus = int(self.start_focus_pos.value())
        end_focus = int(self.end_focus_pos.value())
        if auto_focus_bool:
            if start_focus == end_focus:
                still_send = self.displayWarning("focus_range", 0)
                if not still_send:
                    self.start_focus_pos.setValue(self.prev_start_focus)
                    self.end_focus_pos.setValue(self.prev_end_focus)
                    self.focus_step.setValue(self.prev_focus_step)
                    return
            elif end_focus < start_focus:
                self.displayWarning("end_focus", 0)
                self.start_focus_pos.setValue(self.prev_start_focus)
                self.end_focus_pos.setValue(self.prev_end_focus)
                self.focus_step.setValue(self.prev_focus_step)
                return

        step_size = int(self.focus_step.value())
        if ((end_focus - start_focus) % step_size != 0) and auto_focus_bool:
            still_send = self.displayWarning("auto-focusing", step_size)
            if not still_send:
                self.start_focus_pos.setValue(self.prev_start_focus)
                self.end_focus_pos.setValue(self.prev_end_focus)
                self.focus_step.setValue(self.prev_focus_step)
                return

        photos_per_focus = int(self.photos_per_focus.value())

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

        if (high_pass_filter_bool and r_smooth_value > r_high_pass_filter_value):
            still_send = self.displayWarning("r_smooth", 0)
            if not still_send:
                self.new_high_pass_filter.setCurrentText(str(self.prev_high_pass_filter))
                self.new_r_high_pass_filter.setText(str(self.prev_r_high_pass_filter))
                self.new_r_smooth.setText(str(self.prev_r_smooth))
                return
        
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

        # package commands to send to camera
        cmds_for_camera = struct.pack('ddddddfiiiiiiiiiifffffffff', logodds, latitude, longitude, height, exposure, 
                                       timelimit, set_focus_to_amount, auto_focus_bool, start_focus, end_focus, 
                                       step_size, photos_per_focus, infinity_focus_bool, set_aperture_steps, 
                                       max_aperture_bool, make_HP_bool, use_HP_bool, spike_limit_value, 
                                       dynamic_hot_pixels_bool, r_smooth_value, high_pass_filter_bool, 
                                       r_high_pass_filter_value, centroid_search_border_value, filter_return_image_bool,
                                       n_sigma_value, star_spacing_value)
        # send these commands to things listening to the send_commands_signal
        self.send_commands_signal.emit(cmds_for_camera)

        # if this is the first iteration of the new auto-focusing process
        if (auto_focus_bool):
            self.auto_focus = []
            self.flux = []
            self.coefficients = []
            self.af_line.setData(self.auto_focus, self.flux)
            self.regression.setData(self.auto_focus, self.polynomial(self.coefficients))

        # update previous value attributes of the focus and aperture sliders
        self.focus_slider.updatePrevValue()
        self.aperture_menu.updatePrevValue() 

    """ 
    Pause reception of data from Star Camera. 
    Inputs: self.
    Outputs: None.
    """
    def pauseButtonClicked(self):
        print("Pausing reception of Star Camera data")
        self.GUItelemetry.requestInterruption()
        self.ip_button.setEnabled(True)
        self.main_socket.close()
        msg = QMessageBox()
        msg.setWindowTitle("Star Camera")
        msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setIcon(QMessageBox.Information)
        msg.setText("Pausing telemetry reception. Press the start button in the upper righthand corner to resume.")
        msg.exec_()

    """
    Reset the IP address entry field for the Star Camera so user can re-connect.
    """
    def resetConnection(self):
        msg = QMessageBox()
        msg.setWindowTitle("Star Camera")
        msg.setWindowIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"))
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setIcon(QMessageBox.Warning)
        msg.setText("Camera is disconnected. IP address input will open in a few seconds.")
        msg.exec_()
        self.main_socket.shutdown(socket.SHUT_RDWR)
        self.main_socket.close()
        time.sleep(3)
        self.ip_input.setText("")
        self.port_input.setText("")
        self.ip_button.setEnabled(True)

    """
    Override the closeEvent() method of the GUI window, built on the QDialog class.
    Inputs: self, the event (clicking the X button).
    Outputs: None. Closes the window if the user confirms or keeps it open.
    """
    def closeEvent(self, event):
        quit_msg = "Are you sure you want to exit the Star Camera application?"
        quit_window = QMessageBox()
        reply = quit_window.question(self, "Confirm Exit", quit_msg, QMessageBox.Yes, QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    gallery = GUI()

    tray_icon = QSystemTrayIcon(QIcon(script_dir + os.path.sep + "SO_icon.png"), app)
    tray_icon.show()
    menu = QMenu()
    exit_action = menu.addAction("Exit")

    tray_icon.setContextMenu(menu)
    gallery.show()
    sys.exit(app.exec_())