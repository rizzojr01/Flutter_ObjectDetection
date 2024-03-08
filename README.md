
Code originally cloned from : https://github.com/jcrisp88/flutter-webrtc_python-aiortc-opencv

## Setup Server Environment
- Install python==3.11
- Create a virtual env using the py 3.11 and install the requirements from `server/requirements.txt`
- create a .env file using `.env.example` as a template
- start the server using `python main.py`, the server should start in the URL `http://localhost:8080`
- navigate to the URL in the browser and make sure the video checkbox is selected and drop down value is set to `Detection`
# Reference
![image](https://github.com/rizzojr01/Flutter_ObjectDetection/assets/76396808/3be0b6b6-b521-4c6e-b826-031a9b019fd1)
- Now start streaming the video by clicking the start button. The detected objects should be written to the data stream and should be visible in the console.
![image](https://github.com/rizzojr01/Flutter_ObjectDetection/assets/76396808/c968ea1c-77b5-477e-a4cc-38a50c501bd8)


## Steps to run
- Change IP address in flutter/lib/src/p2pVideo.dart to server's IP and compile app to phone
- Run on the server main.py
- Choose the Detect option within the app and tap start
