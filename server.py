import RPi.GPIO as GPIO
import time
import datetime
import os
from balena import Balena
import sys
import paho.mqtt.client as mqtt
import json
import threading
import signal
import socket

pulse_per_second= 0
pulse_count = 0
pulse_output = {
    "uuid": os.environ.get('BALENA_DEVICE_UUID'),
    "gpio": 0,
    "pulse_per_second": 0,
    "pulse_per_minute": 0,
    "pulse_per_hour": 0,
    "pulse_count": 0,
    "pps_mult": 0,
    "ppm_mult": 0,
    "pph_mult": 0
}
env_vars = {
    "pulse_multiplier": 1,
    "gpio_pin": 37,
    "bounce_time": 200,
    "mqtt_address": "none",
    "gpio_reset_pin": 38,
    "enable_webserver": 0,
    "pull_up_down": "down"
}
sum_queue = []
pulse_multiplier = 0
client = mqtt.Client()

# Use the sdk to get services
def mqtt_detect():
    print("Using API to detect services...")
    balena = Balena()
    auth_token = os.environ.get('BALENA_API_KEY')
    balena.auth.login_with_token(auth_token)
    device_id = os.environ.get('BALENA_DEVICE_UUID')
    device = balena.models.device.get_with_service_details(device_id, False)
    for service in device['current_services']:
        if service == "mqtt":
            print("Found a service on this device named 'mqtt'")
            return True
    return False

# Simple webserver
def background_web(server_socket):
    global pulse_output

    while True:
        # Wait for client connections
        client_connection, client_address = server_socket.accept()

        # Get the client request
        request = client_connection.recv(1024).decode()
        print(request)

        # Send HTTP response
        response = 'HTTP/1.0 200 OK\n\n'+ json.dumps(pulse_output)
        print(pulse_output)
        client_connection.sendall(response.encode())
        client_connection.close()

class ProgramKilled(Exception):
    """
    An instance of this custom exception class will be thrown every time we get an SIGTERM or SIGINT
    """
    pass

# Raise the custom exception whenever SIGINT or SIGTERM is triggered
def signal_handler(signum, frame):
    raise ProgramKilled

# This method fires on edge detection from a reset button
def on_reset(channel):
    global pulse_count
    print("pulse reset detected")
    pulse_count = 0

# This function serves as the callback triggered on every run of our IntervalThread
def action() :
    global pulse_per_second, sum_queue, client, env_vars, pulse_output
    pulse_per_minute = 0
    pulse_per_hour = 0
    pulse_multiplier = env_vars["pulse_multiplier"]
    sum_queue.append(pulse_per_second)
    if len(sum_queue) > 1:
        pulse_per_minute = sum(sum_queue[-60:])
        pulse_per_hour = sum(sum_queue[-3600:])
    if len(sum_queue) > 3600:
        sum_queue.pop(0)
    pulse_output["gpio"] = env_vars["gpio_pin"]
    pulse_output["pulse_per_second"] = pulse_per_second
    pulse_output["pulse_per_minute"] = pulse_per_minute
    pulse_output["pulse_per_hour"] = pulse_per_hour
    pulse_output["pulse_count"] = pulse_count
    pulse_output["pps_mult"] = pulse_per_second * pulse_multiplier
    pulse_output["ppm_mult"] = pulse_per_minute * pulse_multiplier
    pulse_output["pph_mult"] = pulse_per_hour * pulse_multiplier
    #print(pulse_output)
    if env_vars["mqtt_address"] != "none":
        client.publish('pulse_data', json.dumps(pulse_output))
    pulse_per_second = 0

# See https://stackoverflow.com/questions/2697039/python-equivalent-of-setinterval
class IntervalThread(threading.Thread) :
    def __init__(self,interval,action, *args, **kwargs) :
        super(IntervalThread, self).__init__()
        self.interval=interval
        self.action=action
        self.stopEvent=threading.Event()
        self.start()

    def run(self) :
        nextTime=time.time()+self.interval
        while not self.stopEvent.wait(nextTime-time.time()) :
            nextTime+=self.interval
            self.action()

    def cancel(self) :
        self.stopEvent.set()

def main():

    global pulse_per_second, pulse_count, env_vars, client

    # device variables
    env_vars["pulse_multiplier"] = float(os.getenv('PULSE_MULTIPLIER', '1'))
    env_vars["gpio_pin"] = os.getenv('GPIO_PIN', 37)
    env_vars["bounce_time"]  = os.getenv('BOUNCE_TIME', 0)
    env_vars["mqtt_address"] = os.getenv('MQTT_ADDRESS', 'none')
    env_vars["gpio_reset_pin"] = os.getenv('GPIO_RESET_PIN', 38)
    env_vars["enable_webserver"] = os.getenv('ALWAYS_USE_WEBSERVER', 0)
    env_vars["pull_up_down"] = os.getenv('PULL_UP_DOWN', 'DOWN')

    GPIO.setmode(GPIO.BOARD)
    gpio_pin = int(env_vars["gpio_pin"])

    # Set the pin for the incoming pulse
    if env_vars["pull_up_down"] == "UP":
        GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        test_cond = GPIO.LOW
    else:
        GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        test_cond = GPIO.HIGH

    if env_vars["bounce_time"] == 0:
        bounce_time = 0
    else:
        if str(env_vars["bounce_time"]).isnumeric():
            bounce_time = int(env_vars["bounce_time"])/1000
            print("Bounce time set to {0} second(s)".format(bounce_time))
        else:
            bounce_time = 0

    # Set the pin for pulse count reset
    GPIO.setup(int(env_vars["gpio_reset_pin"]), GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(int(env_vars["gpio_reset_pin"]), GPIO.FALLING, callback=on_reset, bouncetime=200)

    if mqtt_detect() and env_vars["mqtt_address"] == "none":
        env_vars["mqtt_address"] = "mqtt"

    if env_vars["mqtt_address"] != "none":
        print("Starting mqtt client, publishing to {0}:1883".format(env_vars["mqtt_address"]))
        try:
             client.connect(env_vars["mqtt_address"], 1883, 60)
        except Exception as e:
            print("Error connecting to mqtt. ({0})".format(str(e)))
            env_vars["mqtt_address"] = "none"
            env_vars["enable_webserver"] = "True"
        else:
            client.loop_start()
    else:
        env_vars["enable_webserver"] = "True"

    if env_vars["enable_webserver"] == "True":
        SERVER_HOST = '0.0.0.0'
        SERVER_PORT = 7575

        # Create socket
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((SERVER_HOST, SERVER_PORT))
        server_socket.listen(1)
        print("Web server listening on port {0}...".format(SERVER_PORT))

        t = threading.Thread(target=background_web, args=(server_socket,))
        t.start()

    # Handle SIGINT and SIFTERM with the help of the callback function
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    # start action every 1s
    inter=IntervalThread(1,action)

    # See https://www.g-loaded.eu/2016/11/24/how-to-terminate-running-python-threads-using-signals/
    while True:
        try:
            GPIO.wait_for_edge(gpio_pin, GPIO.RISING)
            if bounce_time > 0:
                time.sleep(bounce_time)
                if GPIO.input(gpio_pin) == test_cond:
                    pulse_per_second = pulse_per_second + 1
                    pulse_count = pulse_count + 1
            else:
                pulse_per_second = pulse_per_second + 1
                pulse_count = pulse_count + 1
        except ProgramKilled:
            print("Program killed: running cleanup code")
            inter.cancel()
            break

if __name__ == "__main__":
    main()
