# EMFI Glitching using an Ender 3 S1 Pro and Faulty Cat

This is my current set up for doing EMFI glitching attacks using the faulty cat and my ender 3. The device uses the 3D printer to move the faulty cat probe along the chip and then tries to inject faults into it. It has a handy dashboard to allow you to see some graphs and statistics and has a feature to try to evaluate which location is the most optimal location based on number of successful glitches, number of crashes, and other parameters. Most of this code is based on the code from this github/article which was the whole insperation for this build.

https://rossmarks.uk/blog/cheap-emfi-mapping/

definitely check out the article above since its a great read and has been a huge help. 

# How to use
just run the emfi_gui.py file and then set all of you parameters in the dashboard as described below. If you get an error saying that the program cannot open the serial port, you might have to run `sudo chmod 666 your_serial_port`. For me, this looks like running `sudo chmod 666 dev/ttyUSB0` when I plug in the printer. 
# Dashboard
![alt text](https://github.com/Jewber11/EMFI_Glitching/blob/main/EMFI_Dashboard.png "EMFI Software Dashboard")

The dashboard features many nice features like being able to connect to the printer and set the baud rate as well as set all of the parameters you would want for glitching. The general steps to start gliching are:

1. connect to printer and set baud rate (top right)
2. set the probe tip to the bottom left corner of the chip you want to probe and set it as the origin
3. move the probe to the top left of the chip and confirm it
4. calculate the grid
5. start the scan
6. evaluate the output

## Dashboard Outputs
![alt text](https://github.com/Jewber11/EMFI_Glitching/blob/main/EMFI_simulated.png "simulated EMFI glitching test")

The outputs on the dashboard include a real-time 3d location on the top graph and then a real-time glitch graph on the bottom which shoes the percentage of successful glitches at a given location. The bottom left also shows how many EMFI pulses have been sent and how many locations have been scanned. 

Once the whole chip has been scanned, the program will output a heat map per z-axis step that looks like this:

![alt text](https://github.com/Jewber11/EMFI_Glitching/blob/main/EMFI_simulated_heatmap.png "Simulate glitch heatmap")

# TODO 
- implement target serial recieving
- implement glitch detection when using faulty cat instead of simulation
- add a way to automatically go to the optimal location determined by the scan and just glitch there
