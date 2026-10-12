// ping-pong: MPU-6050 on the paddle (header SDA/SCL, address 0x68).
//
// Python calls imu_check() to confirm the sensor, then imu_read() for samples
// "ax,ay,az,gx,gy,gz" in g and deg/s (default ranges: ±2 g, ±250 deg/s).

#include <Wire.h>
#include "Arduino_RouterBridge.h"

const uint8_t ADDR = 0x68;
const uint8_t REG_ACCEL_XOUT_H = 0x3B;
const uint8_t REG_PWR_MGMT_1 = 0x6B;
const uint8_t REG_WHO_AM_I = 0x75;

bool found = false;

void write_reg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

// Point at reg, then request n bytes
void request(uint8_t reg, uint8_t n) {
    Wire.beginTransmission(ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom(ADDR, n);
}

String imu_check() {
    if (!found) return "not found at 0x68";
    request(REG_WHO_AM_I, 1);
    return "found, whoami=0x" + String(Wire.read(), HEX);
}

String imu_read() {
    if (!found) return "";
    request(REG_ACCEL_XOUT_H, 14);
    int16_t v[7];  // ax, ay, az, temp, gx, gy, gz
    for (int i = 0; i < 7; i++) {
        uint8_t hi = Wire.read();
        uint8_t lo = Wire.read();
        v[i] = (int16_t)((hi << 8) | lo);
    }
    String s;
    for (int i = 0; i < 3; i++) s += String(v[i] / 16384.0, 3) + ",";
    for (int i = 4; i < 7; i++) s += String(v[i] / 131.0, 2) + (i < 6 ? "," : "");
    return s;
}

void setup() {
    Wire.begin();
    Wire.beginTransmission(ADDR);
    found = Wire.endTransmission() == 0;
    if (found) write_reg(REG_PWR_MGMT_1, 0);  // wake from sleep

    Bridge.begin();
    Bridge.provide("imu_check", imu_check);
    Bridge.provide("imu_read", imu_read);
}

void loop() {}
