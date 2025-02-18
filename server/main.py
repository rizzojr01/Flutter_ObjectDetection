import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid

# os.add_dll_directory('C:/Users/thoma/anaconda3/envs/py38/DLLs') # For aiortc installed in editable mode (need to manually install opus & vpx), and when python cannot detect DLLs (opus, vpx)

import cv2
import boto3
from aiohttp import web
from av import VideoFrame
import aiohttp_cors
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
from server_utils.plot import non_max_suppression, plot_images, output_to_target
import torch
import numpy as np

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()

from botocore.credentials import Credentials
from server_utils.kinesis.utils import put_record_to_kinesis, format_detection_result
from config import (
    AWS_ACCESS_KEY,
    AWS_SECRET_KEY,
    AWS_REGION,
    AWS_DATA_STREAM_NAME,
)

credentials = Credentials(access_key=AWS_ACCESS_KEY, secret_key=AWS_SECRET_KEY)

session = boto3.Session(
    aws_access_key_id=credentials.access_key,
    aws_secret_access_key=credentials.secret_key,
    region_name=AWS_REGION,
)
kinesis_client = session.client("kinesis")


class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, track, transform, datachannel):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform
        self.model = torch.hub.load("ultralytics/yolov5", "yolov5s")
        self.model.eval()

        if torch.cuda.is_available():
            self.model.cuda()
        else:
            print("Cuda Not Available")

    async def recv(self):
        frame = await self.track.recv()
        img = frame.to_ndarray(format="bgr24")
        img_yuv = frame.to_ndarray(format="yuv420p")
        height, width, _ = img.shape
        blocksize = int(np.ceil(height * 0.05))
        Nblocks = 10
        timestamp = 0
        margin = int(blocksize * 0.25)  # only average values inside margin
        hexa_digit = ""
        for i in range(Nblocks):
            block = img_yuv[
                margin : blocksize - margin,
                i * blocksize + margin : blocksize * (i + 1) - margin,
            ]
            digit = np.round(np.mean(block[:, :]) / 32)
            hexa_digit += str(int(digit))
            timestamp += 8**i * digit
        print("Hexadecimal: ", hexa_digit)
        print("Estimated Timestamp: ", timestamp)
        # cv2.imwrite("saved_frames/{}.jpg".format(timestamp), img)

        if self.transform == "cartoon":

            # prepare color
            img_color = cv2.pyrDown(cv2.pyrDown(img))
            for _ in range(6):
                img_color = cv2.bilateralFilter(img_color, 9, 9, 7)
            img_color = cv2.pyrUp(cv2.pyrUp(img_color))

            # prepare edges
            img_edges = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            img_edges = cv2.adaptiveThreshold(
                cv2.medianBlur(img_edges, 7),
                255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY,
                9,
                2,
            )
            img_edges = cv2.cvtColor(img_edges, cv2.COLOR_GRAY2RGB)

            # combine color and edges
            img = cv2.bitwise_and(img_color, img_edges)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == "edges":
            # perform edge detection
            img = cv2.cvtColor(cv2.Canny(img, 100, 200), cv2.COLOR_GRAY2BGR)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == "Detection":
            img = cv2.resize(img, (640, 640))
            img_tensor = (
                torch.tensor(img).unsqueeze(0).permute(0, 3, 1, 2).float() / 255.0
            )
            # Check if CUDA is available and use the appropriate device
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            img_tensor = img_tensor.to(device)
            self.model.to(device)

            with torch.no_grad():
                results = self.model(img_tensor)
            results = non_max_suppression(
                results, conf_thres=0.25, iou_thres=0.5, multi_label=True
            )

            if len(results) > 0 and results[0] is not None:
                detected_objects = results[0]
                for *box, conf, cls_id in detected_objects:
                    detected_object = self.model.names[int(cls_id)]
                    print(detected_object)
                    record = format_detection_result(detected_object)
                    put_record_to_kinesis(kinesis_client, record, AWS_DATA_STREAM_NAME)
            img_plotted = plot_images(
                img_tensor, output_to_target([results[0].detach().cpu()])
            )
            new_frame = VideoFrame.from_ndarray(img_plotted, format="rgb24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            print(frame.pts)

            global data_channel
            if data_channel is not None:
                data_channel.send("test_message")

            return new_frame
        else:
            return frame


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    # prepare local media
    player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    recorder = MediaBlackhole()

    # data_channel = pc.createDataChannel('data')
    global data_channel
    data_channel = None

    @pc.on("datachannel")
    def on_datachannel(channel):
        print("data_channel assigned")
        global data_channel
        data_channel = channel
        # @channel.on("message")
        # def on_message(message):
        # if isinstance(message, str) and message.startswith("ping"):
        # channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        if track.kind == "audio":
            pc.addTrack(player.audio)
            recorder.addTrack(track)
        elif track.kind == "video":
            pc.addTrack(
                VideoTransformTrack(
                    relay.subscribe(track),
                    transform=params["video_transform"],
                    datachannel=data_channel,
                )
            )

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


app = web.Application()
cors = aiohttp_cors.setup(app)
app.on_shutdown.append(on_shutdown)
app.router.add_get("/", index)
app.router.add_get("/client.js", javascript)
app.router.add_post("/offer", offer)

for route in list(app.router.routes()):
    cors.add(
        route,
        {
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*",
            )
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )
