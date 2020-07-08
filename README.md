<img src="https://avatars0.githubusercontent.com/u/13680500?s=280&v=4" width="150">

GUI
===
Python source code for the Star Camera GUI. Includes the main file (`StarCameraGUI_v3.py`) and an intermediary file containing the functions for receiving TCP data from the Star Camera computer (`listening_final.py`). The application is included in the software release (download the installation package) so the source code itself does not have to be downloaded.

How to use
---
1. Connect to the Star Camera by entering its known IP address and clicking the Start button. If you enter an invalid IP address, a warning will pop up. If you enter a valid IP address, but one that is not associated with the camera computer, another warning will pop up. This warning might take a bit (and the GUI might become nonresponsive for that time) since it will be trying to open a connection with another device.
2. Once connected, a livestream of data will be received, the speed of which is limited by how fast the Star Camera itself is able to solve for the pointing. The telemetry, which includes Greenich Mean Time, right ascension (degrees), declination (degrees), field rotation (degrees), pixel scale (arcseconds per pixel), image rotation (degrees), altitude (degrees), and azimuth (degrees). The current camera settings will also be received so that another user's activity on the camera can be seen. The latest Star Camera image will be displayed in the Image tab, as well as graphs of all the telemetry and the latest auto-focusing curve.
3. The command entry fields are pre-populated with default values, some of which have been determined to be the ideal ones in a range of values (see the Instructions tab). You can change any of these as you see fit. The auto-focusing command section is only enabled when the auto-focusing checkbox is marked. To send your commands, press the Send Commands button; a warning will pop up if any of the commands are invalid or dubious. To stop the reception of data, press the Pause button. This will cause the telemetry timer to continue counting until it reaches its limit. It will be reset once you connect back to the camera, which you can do by pressing the Start button once again. The telemetry will be written to a backup file called data.txt, which will come with the installation. The image display and graphs are built on PyQtGraph's widgets [PyQtGraph_reference](www.pyqtgraph.org "PyQtGraph Homepage") for fast performance. Left-clicking on them provides a number of customization and export options, which are discussed further in the Instructions tab. The auto-focusing curve also has the ability to run a polynomial regression on the data once all of it is received. The auto-focusing procedure on the Star Camera does a quadratic regression, but this can be used to verify and/or test other degree polynomials. This will *not* change the final auto-focusing result on the camera side; if you want to change the position of the focus after auto-focusing, use the focus slider. 
