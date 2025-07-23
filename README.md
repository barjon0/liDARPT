# liDARPT
A python implementation of an event-based MILP for the line-based Dial-A-Ride Problem with Transfers (liDARPT). We include benchmark instances and results.

## Description
The code is implemented for python 3.10 and requires a CPLEX installation, preferably 22.10 or higher. For more detailed information on the implementation, see my masters thesis https://www.informatik.uni-wuerzburg.de/fileadmin/10030100/2025/masterarbeit_Jonas_Barth.pdf

## Installation
Fork this repository from GitHub and make sure python 3.10 or higher is installed. Install CPLEX Developer Edition 22.10 or higher and add the installations' python API to your path.  
Install dependencies from requirements.txt and run the file IOHandler.py from src/scripts, set path to the configuration file as parameter.  
For an example of the configuration file see ../input/config.json. Most importantly requires a path to request and network file.

## Input Files
The models accept request files as .csv files.

**Request File**

This file details the requests' basic properties.

The first row constains:

    id, arrivalTime, startTime, pickUp, dropOff, amount

The remaining rows denote, for all requests, the following:

    index, register time of request, earliest time for pick-up, idx of pick-up stop, idx of drop-off stop, number of passengers

The time values are in 24-hour format, i. e., 08:01:00. All other values are integers.

**Network File**

This file details the bus network in a .json format, consisting of stops, lines and buses.

- stops: list of objects with: 
  - id: integer  
  - coordinates: list of floats of length 2 

- lines: list of objects with: 
  - id: integer
  - stops: list of integers (stop-ids)
  - depot: list of floats of length 2 (coordinate)
  - startTime: 24-hour format (earliest start time of buses)
  - endTime: 24-hour format (latest end of buses) 
  - (optional:) capacity: integer (capacity of passengers for buses)

- buses: list of objects with 
  - id: integer
  - line: integer(id of line)

Examples for these files can be found in the input folder.

## Support
E-Mail jonas.barth@stud-mail.uni-wuerzburg.de

## License

<a rel="license" href="http://creativecommons.org/licenses/by-nc-sa/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-nc-sa/4.0/88x31.png" /></a><br />

This work is licensed under [CC BY-NC-SA 4.0 ](https://creativecommons.org/licenses/by-nc-sa/4.0/).