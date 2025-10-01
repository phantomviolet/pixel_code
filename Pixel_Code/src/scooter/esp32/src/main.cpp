#include <Arduino.h>
#include "motor_control.h"

enum Mode { MODE_NORMAL, MODE_CORNER };
static Mode currentMode = MODE_NORMAL;

static uint32_t lastHbMs = 0;
static bool hbArmed = false;
static const uint32_t HEARTBEAT_TIMEOUT_MS = 1500;

static void sendAck(const char* what, const String& arg="") {
  if (arg.length()) Serial.printf("ACK %s %s\n", what, arg.c_str());
  else              Serial.printf("ACK %s\n", what);
}

static void emergencyBrake() { mc_set_brake_brake(); Serial.println("EVENT BRAKE"); }

static void applyCmd(const String& c) {
  if (c == "SAFE")      mc_set_brake_safe();
  else if (c == "SLOW") mc_set_brake_slow();
  else if (c == "BRAKE")mc_set_brake_brake();
}

static void parseLine(const String& line) {
  if (line.startsWith("MODE ")) {
    String m = line.substring(5); m.trim();
    currentMode = (m == "CORNER") ? MODE_CORNER : MODE_NORMAL;
    sendAck("MODE", m);
  } else if (line.startsWith("CMD ")) {
    String c = line.substring(4); c.trim();
    applyCmd(c);                 // ★ CORNER에서도 명령 반영
    sendAck("CMD", c);
  } else if (line.startsWith("SPD_CAP ")) {
    // 속도상한은 현재 정보 전달만. (추후 Hall 연동 시 사용)
    sendAck("SPD_CAP", line.substring(8));
  } else if (line == "HB") {
    lastHbMs = millis(); hbArmed = true; sendAck("HB");
  }
}

void setup() {
  Serial.begin(115200);
  delay(100);
  mc_init(5); // 서보 신호 핀 (배선에 맞게 변경 가능)
  lastHbMs = millis();
  Serial.println("ESP32 ready (RPi-LiDAR control)");
}

void loop() {
  static String buf;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') { buf.trim(); if (buf.length()) parseLine(buf); buf = ""; }
    else buf += ch;
  }
  if (hbArmed && (millis() - lastHbMs > HEARTBEAT_TIMEOUT_MS)) {
    emergencyBrake(); lastHbMs = millis();
  }
}