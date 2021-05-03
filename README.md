# pulse-block

A block for counting pulses on a Raspberry Pi GPIO pin.

# Features
- counts pulses as fast as a few hundred per second
- provides pulses per second, pulses per minute, and pulses per hour
- provides a running pulse count that can be reset via a dedicated gpio pin
- allows for use of a multiplier value to be appled to the pulse counts
- rudimentary software-based switch debouncing
- count data published via mqtt or http
- integrates well with other balena blocks, such as Connector and Dashboard

# Usage

## docker-compose file
To use this image, create a container in your `docker-compose.yml` file as shown below:

```
version: '2'

services:
  pulse:
    image: balenablocks/pulse
    restart: always
    privileged: true
    labels:
      io.balena.features.supervisor-api: '1'
    expose:
      - '7575'
```

Note that the container must be privileged in order to access the GPIO pins, as well as include the balena supervisor-api label to access the device's api features.

## Data
The counter data is available as json either as an mqtt payload or via the built-in  HTTP server. To use mqtt provide an address for the `MQTT_ADDRESS` service variable. If no mqtt address is set, the  HTTP server will be available on port 7575. To force the HTTP server to be active along with mqtt, set the `ALWAYS_USE_HTTPSERVER` service variable to `True`.

The JSON will be in the following format:
`{"uuid": "a74be18a3fdc0b3bfb510e2cf84d6008", "gpio": 37, "pulse_per_second": 3, "pulse_per_minute": 180, "pulse_per_hour": 3145, "pulse_count": 3150, "pps_mult": 3, "ppm_mult": 180, "pph_mult": 3145}` 

The values ending in `_mult` are pulse counts multiplied by the optional `PULSE_MULTIPLIER` service variable. For instance, say you are counting the pulses per minute from a geiger counter and you'd like to also measure micro-Sieverts per hour (uSv/hr). You simply multiply the pulses_per_minute by a ratio specific to your geiger counter tube. (For the popular J305 tube, that ratio is 0.00812037037037) Simply enter this value as the `PULSE_MULTIPLIER` and each time the pulse_per_second, pulse_per_minute and pulse_per_hour is measured, those values times the multiplier will also be calculated. If no multiplier is provided, it defaults to a multiplier of 1.

## Pulses, debouncing, and accuracy
The pulse counter is most accurate when counting pulses from an electronic source such as another computer or device providing a pwm (pulse width modulation) or square wave signal. When counting pulses from a mechanical contact such as a physical switch, multiple unwanted pulses are often generated. These pulses can be minimized or eliminated in hardware through a properly designed "R-C Circuit" consisting of one or more resistors and capacitors. Alternatively, debouncing can be achieved through software methods. This block includes rudimentary software debouncing that should be sufficient for mechanically-generated pulses that are less (slower) than three pulses per second (3 Hz). This is accomplished by delaying the pulse count for a specified number of milliseconds (1000th of a second) after the rising edge of a pulse is detected. A good starting value is 75 milliseconds, and then slowly increasing the value by 50 until you find one that works. (This debouncing method requires smaller values than others.) You may not find a value that avoids miscounting pulses in which case you may need to figure out why your switch is so noisy and improve it somehow. To define the debounce time, set the `BOUNCE_TIME` service variable. Setting the value to `0` or deleting it removes any debouncing (the default and recommended value for counting electronic pulses.)

The default setup for the specified pulse pin is to be "floating" which is ideal for connecting to electronic devices that provide a pulsed output. To invoke one of the internal pull resistors, set the service variable `PULL_UP_DOWN` to `UP` or `DOWN`. If you are using a purely mechanical switch, you should set this value.

_NOTE_: As with most embedded Linux devices, pulse counting may not be accurate or real-time due to the OS, hardware, software or other processes running on the device. If you need strict real-time accuracy without missing even one pulse, you should use a microcontroller instead. This block is not intended for critical pulse counting applications.

## Pulse count reset
You can cause the running pulse count, `pulse_count` to reset to zero by sending a logic high pulse to the pin set by device variable `GPIO_RESET_PIN` which has a debounce value set to 200 ms, so a pushbutton switch should suffice.

## Service/device variables

| Variable | Description | Default value |
| -------- | ----------- | ------------- |
| `GPIO_PIN` | Sets the pin to use for counting incoming pulses, using BOARD numbering | 37 |
| `PULL_UP_DOWN` | Sets the selected gpio pin's internal pull up or pull down resistor. Set to either `NONE`, `UP` or `DOWN` | `NONE` (floating)|
| `GPIO_RESET_PIN` | Sets the pin used to reset the running pulse count. Normally pulled down and debounced 200 ms | 38|
| `PULSE_MULTIPLIER` | Multiplies the pulses per second, minute, and hour by this factor as pps_mult, ppm_mult and pph_mult respectively | 1 |
| `BOUNCE_TIME` | Number of milliseconds to wait before counting a pulse, used to debounce noisy mechanical switches | 0 |
| `MQTT_ADDRESS` | Provide the address of an MQTT broker for the block to publish data to. If this variable is not set and a container on the device is named mqtt, it will publish to that instead. Either disables the internal HTTP server unless `ALWAYS_USE_HTTPSERVER` is set to `True` | none |
| `ALWAYS_USE_HTTPSERVER` | Set to True to enable the internal HTTP server even when it is automatically disabled due to the detection of mqtt | 0 |


## How it works
This block utilizes the "raspberry-gpio-python" module, commonly known as [RPi.GPIO](https://sourceforge.net/projects/raspberry-gpio-python/). Specifically, the event_detected() function is used in a while loop that counts the pulses. A separate thread runs each second to aggregate the pulses counted in that second and add them to a running queue so that the pulses per minute and pulses per hour can be calculated. When activated, a minimal HTTP server runs in its own thread using a simple socket to respond to client requests.

## Use with other blocks
The pulse block works well with our [connector block](https://github.com/balenablocks/connector) and [dashboard block](https://github.com/balenablocks/dashboard). Connect them together to quickly create dashboards for your pulse data.

We also have an [LED Display](https://github.com/balenalabs-incubator/led-sensor-display) project that complements this block by allowing you to view the pulse data on a four digit seven segment LED.
