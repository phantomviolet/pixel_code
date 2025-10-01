// main.cpp
#include <Arduino.h>

enum Mode { MODE_NORMAL, MODE_CORNER };
static Mode currentMode = MODE_NORMAL;
static uint32_t lastHbMs = 0;
static int speedCapKmh = 0;

static const uint32_t HEARTBEAT_TIMEOUT_MS = 800;  // HB 끊기면 fail-safe 제동

// --- 액추에이터(서보/스로틀) 자리: 지금은 스텁 ---
void applyCmd(const String& c) {
  // TODO: motor_control.cpp에서 실제 서보 각도/스로틀 제어
  // 예: BRAKE -> 서보 150도, SAFE -> 90도 등
}

void emergencyBrake() {
  // TODO: 즉시 강제 제동
  // 현재는 메시지만 출력
  Serial.println("EVENT BRAKE");
}

// --- 유틸 ---
void sendAck(const char* what, const String& arg="") {
  if (arg.length()) Serial.printf("ACK %s %s\n", what, arg.c_str());
  else              Serial.printf("ACK %s\n", what);
}

void parseLine(const String& line) {
  if (line.startsWith("MODE ")) {
    String m = line.substring(5);
    m.trim();
    if (m == "NORMAL") { currentMode = MODE_NORMAL; sendAck("MODE", "NORMAL"); }
    else if (m == "CORNER") { currentMode = MODE_CORNER; sendAck("MODE", "CORNER"); }
  } else if (line.startsWith("CMD ")) {
    String c = line.substring(4); c.trim();
    applyCmd(c);
    sendAck("CMD", c);
  } else if (line.startsWith("SPD_CAP ")) {
    speedCapKmh = line.substring(8).toInt();
    sendAck("SPD_CAP", String(speedCapKmh));
  } else if (line == "HB") {
    lastHbMs = millis();
    sendAck("HB");
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}
  lastHbMs = millis();
  Serial.println("ESP32 ready");
}

void loop() {
  // 1) 시리얼 라인 파싱
  static String buf;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      buf.trim();
      if (buf.length()) parseLine(buf);
      buf = "";
    } else {
      buf += ch;
    }
  }

  // 2) HB 타임아웃 → fail-safe
  if (millis() - lastHbMs > HEARTBEAT_TIMEOUT_MS) {
    emergencyBrake();
    lastHbMs = millis(); // 반복 폭주 방지
  }

  // 3) 간단 텔레메트리 (1초마다 더미 속도/거리 송신)
  static uint32_t t = 0;
  if (millis() - t > 1000) {
    t = millis();
    // TODO: sensors.cpp에서 실제 값 읽어 채우기
    Serial.println("SPEED 0.0");
    Serial.println("DIST 9999");
  }
}